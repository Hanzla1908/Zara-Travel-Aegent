"""Column Intelligence — auto-classify every column in a DataFrame.

Rules
-----
- A date column is one whose dtype is datetime, or a string column where ≥85% of
  non-null values parse as dates.
- A numeric KPI column has non-trivial variance and is not an ID column.
- A category column has object/bool dtype, cardinality < 50 *and* < 60% unique ratio.
- An ID column is integer with ≥98% unique ratio (row count > 20) or a name that
  ends with _id / _key / _pk / _no.
- All detections are read-only; the original DataFrame is never modified.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


# ── Name-hint vocabularies ───────────────────────────────────────────────────

_DATE_NAME_HINTS = re.compile(
    r"(date|time|day|month|year|week|quarter|timestamp|created|updated|"
    r"modified|period|dt|ts|at|_on)$",
    re.IGNORECASE,
)
_SUM_KPI_HINTS = re.compile(
    r"(revenue|sales|amount|price|cost|total|value|income|profit|loss|"
    r"spend|spending|budget|qty|quantity|count|orders|units|transactions|"
    r"visits|views|clicks|sessions|installs|downloads|signups|conversions|"
    r"users|customers|subscribers|leads|calls|events|impressions|reach)",
    re.IGNORECASE,
)
_MEAN_KPI_HINTS = re.compile(
    r"(score|rate|ratio|pct|percent|percentage|avg|average|mean|index|"
    r"rating rating|nps|csat|grade|temperature|weight|height|age|salary|"
    r"duration|latency|speed|accuracy|error|loss)",
    re.IGNORECASE,
)
_CAT_NAME_HINTS = re.compile(
    r"(category|type|status|region|country|state|city|gender|channel|"
    r"department|group|segment|tier|level|class|label|tag|source|medium|"
    r"platform|device|brand|product|name|code|flag|mode|stage|phase)",
    re.IGNORECASE,
)
_ID_NAME_HINTS = re.compile(
    r"(^id$|_id$|_key$|_pk$|_no$|_num$|_code$|^uuid|^guid)",
    re.IGNORECASE,
)


# ── Output dataclass ─────────────────────────────────────────────────────────

@dataclass
class ColumnIntel:
    # Time
    date_cols: list[str] = field(default_factory=list)
    primary_date: str | None = None

    # Numeric
    kpi_cols: list[str] = field(default_factory=list)       # good for sum/agg KPIs
    mean_cols: list[str] = field(default_factory=list)      # good for mean/rate KPIs
    dist_cols: list[str] = field(default_factory=list)      # good for distribution charts
    id_cols: list[str] = field(default_factory=list)        # skip for analysis

    # Categorical
    cat_cols: list[str] = field(default_factory=list)       # low-cardinality group-by
    high_card_cols: list[str] = field(default_factory=list) # too many values
    primary_category: str | None = None

    # Conversion suggestions (names only, no actual conversion)
    numeric_as_string: list[str] = field(default_factory=list)
    datetime_as_string: list[str] = field(default_factory=list)

    # Metadata
    n_rows: int = 0
    has_time_data: bool = False
    has_categories: bool = False
    has_numerics: bool = False


# ── Public entry point ───────────────────────────────────────────────────────

def analyze(df: pd.DataFrame) -> ColumnIntel:
    """Classify every column and return a ColumnIntel.  df is never mutated."""
    intel = ColumnIntel(n_rows=len(df))

    for col in df.columns:
        s = df[col]
        _classify_column(col, s, intel, len(df))

    _elect_primaries(intel)

    intel.has_time_data  = bool(intel.date_cols)
    intel.has_categories = bool(intel.cat_cols)
    intel.has_numerics   = bool(intel.kpi_cols or intel.mean_cols or intel.dist_cols)

    return intel


# ── Column classifier ────────────────────────────────────────────────────────

def _classify_column(name: str, s: pd.Series, intel: ColumnIntel, n: int) -> None:
    non_null = s.dropna()
    if len(non_null) == 0:
        return  # all-null — skip

    kind = s.dtype.kind
    dtype_str = str(s.dtype).lower()

    # ── Datetime dtype → confirmed date ──
    if kind == "M" or "datetime" in dtype_str or "timestamp" in dtype_str:
        intel.date_cols.append(name)
        return

    # ── Boolean ──
    if kind == "b" or "bool" in dtype_str:
        intel.cat_cols.append(name)
        return

    # ── Numeric dtype ──
    if kind in ("i", "u", "f") or _is_nullable_numeric(s):
        if _is_id_column(name, non_null, n):
            intel.id_cols.append(name)
        elif _has_trivial_variance(non_null):
            pass  # constant — skip
        else:
            _classify_numeric(name, non_null, intel)
        return

    # ── Object/string dtype ──
    if kind == "O" or "object" in dtype_str or "string" in dtype_str:
        # Try date
        if _looks_like_date(name, non_null):
            intel.datetime_as_string.append(name)
            intel.date_cols.append(name)
            return
        # Try numeric
        if _looks_like_numeric(non_null):
            intel.numeric_as_string.append(name)
            _classify_numeric(name, pd.to_numeric(non_null, errors="coerce").dropna(), intel)
            return
        # Categorical / high-cardinality
        n_unique = int(non_null.nunique())
        unique_ratio = n_unique / len(non_null)
        if n_unique <= 1:
            pass  # constant
        elif _is_id_column(name, non_null, n):
            intel.id_cols.append(name)
        elif n_unique <= min(50, max(2, n * 0.6)) and unique_ratio < 0.9:
            intel.cat_cols.append(name)
        else:
            intel.high_card_cols.append(name)


def _classify_numeric(name: str, non_null: pd.Series, intel: ColumnIntel) -> None:
    if _MEAN_KPI_HINTS.search(name):
        intel.mean_cols.append(name)
    elif _SUM_KPI_HINTS.search(name):
        intel.kpi_cols.append(name)
    else:
        # Heuristic: if values span orders of magnitude, treat as KPI sum
        try:
            arr = pd.to_numeric(non_null, errors="coerce").dropna()
            if len(arr) > 0 and arr.max() / (arr[arr > 0].min() + 1e-9) > 10:
                intel.kpi_cols.append(name)
            else:
                intel.dist_cols.append(name)
        except Exception:
            intel.dist_cols.append(name)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_nullable_numeric(s: pd.Series) -> bool:
    dtype_str = str(s.dtype).lower()
    return any(t in dtype_str for t in ("int", "float", "decimal", "uint"))


def _is_id_column(name: str, non_null: pd.Series, n: int) -> bool:
    if _ID_NAME_HINTS.search(name):
        return True
    if n < 20:
        return False
    unique_ratio = non_null.nunique() / len(non_null)
    if unique_ratio >= 0.98:
        # also check it's integer-like
        kind = non_null.dtype.kind
        if kind in ("i", "u") or "int" in str(non_null.dtype).lower():
            return True
    return False


def _has_trivial_variance(non_null: pd.Series) -> bool:
    try:
        arr = pd.to_numeric(non_null, errors="coerce").dropna()
        return len(arr) > 0 and float(arr.std()) == 0.0
    except Exception:
        return False


def _looks_like_date(name: str, non_null: pd.Series) -> bool:
    name_hint = bool(_DATE_NAME_HINTS.search(name))
    sample = non_null.head(200).astype(str)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            ratio = pd.to_datetime(sample, errors="coerce", format="mixed").notna().mean()
        except Exception:
            ratio = 0.0
    return ratio >= 0.85 or (name_hint and ratio >= 0.5)


def _looks_like_numeric(non_null: pd.Series) -> bool:
    sample = non_null.head(200)
    ratio = pd.to_numeric(sample, errors="coerce").notna().mean()
    return ratio >= 0.9


# ── Primary election ─────────────────────────────────────────────────────────

def _elect_primaries(intel: ColumnIntel) -> None:
    # Best date: prefer names with 'date' or 'time', else first
    intel.primary_date = _pick_primary(
        intel.date_cols,
        lambda n: (
            3 if re.search(r"(date|time)", n, re.I) else
            2 if re.search(r"(created|updated|timestamp)", n, re.I) else
            1
        ),
    )

    # Best category: prefer name-hinted cols, lower cardinality
    intel.primary_category = _pick_primary(
        intel.cat_cols,
        lambda n: 2 if _CAT_NAME_HINTS.search(n) else 1,
    )


def _pick_primary(cols: list[str], score_fn) -> str | None:
    if not cols:
        return None
    return max(cols, key=score_fn)


# ── Summariser (human-readable) ──────────────────────────────────────────────

def describe(intel: ColumnIntel) -> str:
    parts: list[str] = []
    if intel.date_cols:
        parts.append(f"{len(intel.date_cols)} date column(s)")
    total_num = len(intel.kpi_cols) + len(intel.mean_cols) + len(intel.dist_cols)
    if total_num:
        parts.append(f"{total_num} numeric column(s)")
    if intel.cat_cols:
        parts.append(f"{len(intel.cat_cols)} categorical column(s)")
    if intel.id_cols:
        parts.append(f"{len(intel.id_cols)} ID column(s) skipped")
    return " · ".join(parts) if parts else "no analysable columns detected"
