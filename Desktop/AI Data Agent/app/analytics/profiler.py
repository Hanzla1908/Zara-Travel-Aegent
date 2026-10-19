"""Deep dataset profiler.

Produces a three-level profile:

  profile["summary"]   – dataset-level counts and type breakdown
  profile["columns"]   – per-column statistics and quality issues
  profile["quality"]   – aggregated quality checks with severity + a 0-100 score

The profiler is read-only: it never modifies the DataFrame it receives.

Performance
-----------
For DataFrames with more than SAMPLE_THRESHOLD rows the profiler uses a
random sample for per-column statistics (value counts, string lengths, issue
detection) while computing null/duplicate counts on the full dataset.  Shape
metrics (rows, columns, missing cells, duplicate rows) are always exact.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

SAMPLE_THRESHOLD = 50_000   # rows above which per-column stats use a sample
SAMPLE_SIZE      = 50_000   # sample size used when threshold is exceeded


# ── Public entry point ───────────────────────────────────────────────────────

def profile(df: pd.DataFrame) -> dict[str, Any]:
    """Return the full profile dict for *df*.  *df* is never mutated."""
    # For large DataFrames, sample once and reuse for all per-column stats.
    # Null counts and duplicate detection always run on the full frame.
    if len(df) > SAMPLE_THRESHOLD:
        sample_df = df.sample(n=SAMPLE_SIZE, random_state=42)
    else:
        sample_df = df

    col_profiles = {col: _profile_column(df[col], sample_df[col]) for col in df.columns}
    quality      = _quality_checks(df, col_profiles)
    summary      = _summary(df, col_profiles)
    return {"summary": summary, "columns": col_profiles, "quality": quality}


# ── Summary ──────────────────────────────────────────────────────────────────

def _summary(df: pd.DataFrame, col_profiles: dict) -> dict[str, Any]:
    total_cells   = df.shape[0] * df.shape[1]
    missing_cells = int(df.isna().sum().sum())
    dup_rows      = int(df.duplicated().sum())
    mem_bytes     = int(df.memory_usage(deep=True).sum())

    by_category: dict[str, list[str]] = {
        "numeric": [], "datetime": [], "boolean": [], "categorical": [], "other": []
    }
    for col, cp in col_profiles.items():
        by_category.setdefault(cp["dtype_category"], []).append(col)

    return {
        "rows":               df.shape[0],
        "columns":            df.shape[1],
        "total_cells":        total_cells,
        "missing_cells":      missing_cells,
        "missing_pct":        round(missing_cells / total_cells * 100, 2) if total_cells else 0,
        "duplicate_rows":     dup_rows,
        "duplicate_pct":      round(dup_rows / df.shape[0] * 100, 2) if df.shape[0] else 0,
        "memory_kb":          round(mem_bytes / 1024, 1),
        "memory_mb":          round(mem_bytes / 1024 / 1024, 2),
        "numeric_columns":    by_category["numeric"],
        "datetime_columns":   by_category["datetime"],
        "boolean_columns":    by_category["boolean"],
        "categorical_columns":by_category["categorical"],
        "other_columns":      by_category["other"],
    }


# ── Per-column ───────────────────────────────────────────────────────────────

def _profile_column(series: pd.Series, sample: pd.Series | None = None) -> dict[str, Any]:
    """Profile a single column.

    *series* is the full column (used for exact null/unique counts).
    *sample* is an optional sampled series for expensive stat operations;
    when None, *series* is used for everything.
    """
    if sample is None:
        sample = series

    n          = len(series)
    null_count = int(series.isna().sum())
    null_pct   = round(null_count / n * 100, 2) if n else 0.0
    non_null   = series.dropna()
    non_null_s = sample.dropna()

    # unique_count is computed on the full column so it stays exact
    unique_count = int(non_null.nunique())
    unique_pct   = round(unique_count / len(non_null) * 100, 2) if len(non_null) else 0.0

    category    = _dtype_category(series)
    sample_vals = _sample_values(non_null)
    issues      = _column_issues(series, non_null_s, category, null_pct, unique_pct)

    base: dict[str, Any] = {
        "dtype":          str(series.dtype),
        "dtype_category": category,
        "null_count":     null_count,
        "null_pct":       null_pct,
        "unique_count":   unique_count,
        "unique_pct":     unique_pct,
        "sample_values":  sample_vals,
        "issues":         issues,
    }

    if category == "numeric":
        base.update(_numeric_stats(non_null_s))
    elif category == "categorical":
        base.update(_categorical_stats(non_null_s))
    elif category == "datetime":
        base.update(_datetime_stats(non_null_s))
    elif category == "boolean":
        base.update(_boolean_stats(non_null_s))

    return base


def _dtype_category(series: pd.Series) -> str:
    kind = series.dtype.kind
    if kind in ("i", "u", "f"):
        return "numeric"
    if kind == "M":
        return "datetime"
    if kind == "b":
        return "boolean"
    # pandas nullable integer / float
    if hasattr(series.dtype, "numpy_dtype"):
        nk = series.dtype.numpy_dtype.kind
        if nk in ("i", "u", "f"):
            return "numeric"
    name = str(series.dtype).lower()
    if "int" in name or "float" in name or "decimal" in name:
        return "numeric"
    if "datetime" in name or "timestamp" in name:
        return "datetime"
    if "bool" in name:
        return "boolean"
    return "categorical"


def _sample_values(non_null: pd.Series, n: int = 5) -> list[str]:
    try:
        unique_vals = non_null.drop_duplicates().head(n)
        return [str(v) for v in unique_vals]
    except Exception:
        return []


def _numeric_stats(non_null: pd.Series) -> dict[str, Any]:
    try:
        arr = pd.to_numeric(non_null, errors="coerce").dropna()
        if arr.empty:
            return {}
        q25, q75 = float(arr.quantile(0.25)), float(arr.quantile(0.75))
        return {
            "min":       _safe_float(arr.min()),
            "max":       _safe_float(arr.max()),
            "mean":      _safe_float(arr.mean()),
            "median":    _safe_float(arr.median()),
            "std":       _safe_float(arr.std()),
            "q25":       q25,
            "q75":       q75,
            "iqr":       round(q75 - q25, 4),
            "zero_count":int((arr == 0).sum()),
            "neg_count": int((arr < 0).sum()),
        }
    except Exception:
        return {}


def _categorical_stats(non_null: pd.Series) -> dict[str, Any]:
    try:
        vc = non_null.astype(str).value_counts().head(10)
        lengths = non_null.astype(str).str.len()
        has_spaces = bool((non_null.astype(str).str.strip() != non_null.astype(str)).any())
        return {
            "top_values":     vc.to_dict(),
            "avg_str_length": round(float(lengths.mean()), 1) if not lengths.empty else 0.0,
            "min_str_length": int(lengths.min()) if not lengths.empty else 0,
            "max_str_length": int(lengths.max()) if not lengths.empty else 0,
            "has_leading_trailing_spaces": has_spaces,
        }
    except Exception:
        return {}


def _datetime_stats(non_null: pd.Series) -> dict[str, Any]:
    try:
        dt = pd.to_datetime(non_null, errors="coerce").dropna()
        if dt.empty:
            return {}
        delta = dt.max() - dt.min()
        return {
            "min_date":       str(dt.min().date()),
            "max_date":       str(dt.max().date()),
            "date_range_days":delta.days,
        }
    except Exception:
        return {}


def _boolean_stats(non_null: pd.Series) -> dict[str, Any]:
    try:
        vc = non_null.value_counts()
        return {"value_counts": vc.to_dict()}
    except Exception:
        return {}


# ── Per-column issue detection ───────────────────────────────────────────────

def _column_issues(
    series: pd.Series,
    non_null: pd.Series,
    category: str,
    null_pct: float,
    unique_pct: float,
) -> list[str]:
    issues: list[str] = []
    n = len(non_null)

    if len(series) == series.isna().sum():
        issues.append("all_null")
        return issues  # nothing else worth checking

    if n > 0 and non_null.nunique() == 1:
        issues.append("constant")

    if null_pct >= 50:
        issues.append("high_null_severe")
    elif null_pct >= 20:
        issues.append("high_null")

    if category == "categorical" and n > 10 and unique_pct >= 95:
        issues.append("high_cardinality")

    # Detect numbers stored as strings
    if category == "categorical" and n >= 5:
        try:
            numeric_ratio = pd.to_numeric(non_null, errors="coerce").notna().mean()
            if numeric_ratio >= 0.9:
                issues.append("numeric_as_string")
        except Exception:
            pass

    # Detect dates stored as strings
    if category == "categorical" and n >= 5 and "numeric_as_string" not in issues:
        try:
            import warnings as _w
            with _w.catch_warnings():
                _w.simplefilter("ignore")
                date_ratio = pd.to_datetime(non_null, errors="coerce", format="mixed").notna().mean()
            if date_ratio >= 0.9:
                issues.append("datetime_as_string")
        except Exception:
            pass

    # Leading/trailing whitespace
    if category == "categorical" and n > 0:
        try:
            if (non_null.astype(str).str.strip() != non_null.astype(str)).any():
                issues.append("leading_trailing_spaces")
        except Exception:
            pass

    return issues


# ── Quality checks (dataset level) ──────────────────────────────────────────

_SEVERITY = {"error": 0, "warning": 1, "info": 2}


def _quality_checks(df: pd.DataFrame, col_profiles: dict) -> dict[str, Any]:
    checks: list[dict] = []

    # Duplicate rows
    dup = int(df.duplicated().sum())
    if dup > 0:
        dup_pct = dup / len(df) * 100
        checks.append({
            "name":        "Duplicate rows",
            "severity":    "warning" if dup_pct > 1 else "info",
            "description": f"{dup:,} duplicate row(s) found ({dup_pct:.1f}% of dataset).",
            "columns":     [],
            "count":       dup,
        })

    # All-null columns
    all_null = [c for c, cp in col_profiles.items() if "all_null" in cp["issues"]]
    if all_null:
        checks.append({
            "name":        "All-null columns",
            "severity":    "error",
            "description": f"{len(all_null)} column(s) contain no data at all.",
            "columns":     all_null,
            "count":       len(all_null),
        })

    # Constant columns
    constant = [c for c, cp in col_profiles.items() if "constant" in cp["issues"]]
    if constant:
        checks.append({
            "name":        "Constant columns",
            "severity":    "warning",
            "description": f"{len(constant)} column(s) have only one unique value.",
            "columns":     constant,
            "count":       len(constant),
        })

    # Severely high-null columns (≥50%)
    high_null_severe = [c for c, cp in col_profiles.items() if "high_null_severe" in cp["issues"]]
    if high_null_severe:
        checks.append({
            "name":        "Severely incomplete columns (≥50% missing)",
            "severity":    "warning",
            "description": f"{len(high_null_severe)} column(s) are missing ≥50% of values.",
            "columns":     high_null_severe,
            "count":       len(high_null_severe),
        })

    # Moderately high-null (20–49%)
    high_null = [c for c, cp in col_profiles.items() if "high_null" in cp["issues"]]
    if high_null:
        checks.append({
            "name":        "Incomplete columns (20–49% missing)",
            "severity":    "info",
            "description": f"{len(high_null)} column(s) are missing 20–49% of values.",
            "columns":     high_null,
            "count":       len(high_null),
        })

    # Numbers stored as strings
    num_as_str = [c for c, cp in col_profiles.items() if "numeric_as_string" in cp["issues"]]
    if num_as_str:
        checks.append({
            "name":        "Numeric values stored as text",
            "severity":    "warning",
            "description": (
                f"{len(num_as_str)} column(s) appear numeric but have a text dtype. "
                "This will prevent aggregations and charts from working correctly."
            ),
            "columns":     num_as_str,
            "count":       len(num_as_str),
        })

    # Dates stored as strings
    dt_as_str = [c for c, cp in col_profiles.items() if "datetime_as_string" in cp["issues"]]
    if dt_as_str:
        checks.append({
            "name":        "Date/time values stored as text",
            "severity":    "info",
            "description": (
                f"{len(dt_as_str)} column(s) appear to contain dates but have a text dtype. "
                "Convert them to datetime for time-series analysis."
            ),
            "columns":     dt_as_str,
            "count":       len(dt_as_str),
        })

    # High-cardinality text
    high_card = [c for c, cp in col_profiles.items() if "high_cardinality" in cp["issues"]]
    if high_card:
        checks.append({
            "name":        "High-cardinality text columns",
            "severity":    "info",
            "description": (
                f"{len(high_card)} text column(s) have ≥95% unique values — "
                "likely ID or free-text fields. Aggregations on them won't be meaningful."
            ),
            "columns":     high_card,
            "count":       len(high_card),
        })

    # Leading/trailing whitespace
    spaces = [c for c, cp in col_profiles.items() if "leading_trailing_spaces" in cp["issues"]]
    if spaces:
        checks.append({
            "name":        "Leading/trailing whitespace",
            "severity":    "info",
            "description": (
                f"{len(spaces)} column(s) have values with leading or trailing spaces, "
                "which can cause incorrect group-by or join results."
            ),
            "columns":     spaces,
            "count":       len(spaces),
        })

    # Sort: errors first, then warnings, then info
    checks.sort(key=lambda c: _SEVERITY.get(c["severity"], 99))

    score = _quality_score(col_profiles, dup, len(df))
    return {"score": score, "checks": checks}


def _quality_score(col_profiles: dict, dup_rows: int, total_rows: int) -> int:
    score = 100
    n_cols = len(col_profiles)

    for cp in col_profiles.values():
        issues = cp["issues"]
        if "all_null" in issues:
            score -= 10
        if "constant" in issues:
            score -= 3
        if "high_null_severe" in issues:
            score -= 5
        elif "high_null" in issues:
            score -= 2
        if "numeric_as_string" in issues:
            score -= 3
        if "datetime_as_string" in issues:
            score -= 1

    if total_rows > 0:
        dup_pct = dup_rows / total_rows * 100
        if dup_pct > 5:
            score -= 8
        elif dup_pct > 1:
            score -= 4
        elif dup_pct > 0:
            score -= 2

    return max(0, min(100, score))


# ── Utility ──────────────────────────────────────────────────────────────────

def _safe_float(v) -> float | None:
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else round(f, 6)
    except (TypeError, ValueError):
        return None
