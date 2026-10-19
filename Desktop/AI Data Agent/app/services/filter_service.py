"""Filter service — pure logic for dashboard filters.

Streamlit-free.  The sidebar writes to session state; the dashboard reads it.
All public helpers accept a plain dict so they are easy to unit-test without
a running Streamlit session.
"""

from __future__ import annotations

import datetime
import warnings
from typing import Any

import numpy as np
import pandas as pd

from app.analytics.column_intelligence import ColumnIntel


# ── Session-state key conventions ────────────────────────────────────────────

_DATE_KEY   = "_filter_date_range"
_CAT_PREFIX = "_filter_cat_"
_NUM_PREFIX = "_filter_num_"


def key_date()           -> str: return _DATE_KEY
def key_cat(col: str)    -> str: return f"{_CAT_PREFIX}{col}"
def key_num(col: str)    -> str: return f"{_NUM_PREFIX}{col}"

def all_filter_keys(state: dict) -> list[str]:
    return [k for k in state if k.startswith(("_filter_date", _CAT_PREFIX, _NUM_PREFIX))]


# ── Filter options (sidebar needs these to render widgets) ────────────────────

def build_options(df: pd.DataFrame, intel: ColumnIntel) -> dict:
    """
    Return a description of every available filter widget.

    {
      "date":         None | {"col": str, "min": date, "max": date},
      "categoricals": [{"col": str, "values": [str, ...]}, ...],
      "numerics":     [{"col": str, "min": float, "max": float, "step": float}, ...],
    }
    """
    opts: dict[str, Any] = {"date": None, "categoricals": [], "numerics": []}

    # ── Date ──────────────────────────────────────────────────────────────
    if intel.primary_date and intel.primary_date in df.columns:
        dt = _to_datetime(df[intel.primary_date])
        valid = dt.dropna()
        if len(valid) > 1 and valid.min() != valid.max():
            opts["date"] = {
                "col":  intel.primary_date,
                "min":  valid.min().date(),
                "max":  valid.max().date(),
            }

    # ── Categoricals ──────────────────────────────────────────────────────
    for col in intel.cat_cols:
        if col not in df.columns:
            continue
        vals = sorted(df[col].dropna().astype(str).unique().tolist())
        if 2 <= len(vals) <= 50:
            opts["categoricals"].append({"col": col, "values": vals})

    # ── Numerics ──────────────────────────────────────────────────────────
    # Prefer mean_cols (rate/score columns make better filter axes than raw KPI totals),
    # then dist_cols, then kpi_cols if nothing else is available.
    candidate_num_cols = intel.mean_cols + intel.dist_cols + intel.kpi_cols
    seen: set[str] = set()
    for col in candidate_num_cols:
        if col not in df.columns or col in seen:
            continue
        seen.add(col)
        arr = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(arr) < 5 or arr.min() == arr.max():
            continue
        lo, hi = float(arr.min()), float(arr.max())
        rng = hi - lo
        step = max(rng / 200, 0.01)
        # Round step nicely; always keep as float so slider types match lo/hi
        if rng > 10000: step = float(round(step / 10) * 10)
        elif rng > 1000: step = float(round(step))
        elif rng > 100: step = round(step, 1)
        else: step = round(step, 2)
        step = max(step, 0.01)

        opts["numerics"].append({
            "col":  col,
            "min":  lo,
            "max":  hi,
            "step": step,
        })
        if len(opts["numerics"]) >= 4:  # cap at 4 numeric sliders
            break

    return opts


# ── Apply all active filters ──────────────────────────────────────────────────

def apply_filters(
    df: pd.DataFrame,
    intel: ColumnIntel,
    state: dict,
    opts: dict | None = None,
) -> pd.DataFrame:
    """Return a filtered copy.  If nothing is active, returns df unchanged."""
    if opts is None:
        opts = build_options(df, intel)

    mask = pd.Series(True, index=df.index)

    # ── Date ──────────────────────────────────────────────────────────────
    date_info = opts.get("date")
    date_range = state.get(key_date())
    if (
        date_info
        and date_range
        and isinstance(date_range, (tuple, list))
        and len(date_range) == 2
    ):
        start, end = date_range
        start = _as_date(start)
        end   = _as_date(end)
        dt = _to_datetime(df[date_info["col"]])
        date_mask = dt.dt.date.between(start, end)
        mask &= date_mask.fillna(False)

    # ── Categoricals ──────────────────────────────────────────────────────
    for info in opts.get("categoricals", []):
        col = info["col"]
        if col not in df.columns:
            continue
        selected = state.get(key_cat(col))
        if selected:   # empty list = "all" = no filter
            mask &= df[col].astype(str).isin([str(s) for s in selected])

    # ── Numerics ──────────────────────────────────────────────────────────
    for info in opts.get("numerics", []):
        col = info["col"]
        if col not in df.columns:
            continue
        range_val = state.get(key_num(col))
        if range_val and isinstance(range_val, (tuple, list)) and len(range_val) == 2:
            lo, hi = float(range_val[0]), float(range_val[1])
            full_lo, full_hi = info["min"], info["max"]
            if lo > full_lo or hi < full_hi:
                num_series = pd.to_numeric(df[col], errors="coerce")
                mask &= num_series.between(lo, hi).fillna(False)

    if mask.all():
        return df

    return df[mask].reset_index(drop=True)


# ── Dirty check (is any filter active?) ──────────────────────────────────────

def active_count(state: dict, opts: dict) -> int:
    """Return how many filters are currently narrowing the data."""
    n = 0

    date_info = opts.get("date")
    date_range = state.get(key_date())
    if date_info and date_range and isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        start, end = _as_date(date_range[0]), _as_date(date_range[1])
        if start > date_info["min"] or end < date_info["max"]:
            n += 1

    for info in opts.get("categoricals", []):
        if state.get(key_cat(info["col"])):
            n += 1

    for info in opts.get("numerics", []):
        rv = state.get(key_num(info["col"]))
        if rv and isinstance(rv, (tuple, list)) and len(rv) == 2:
            lo, hi = float(rv[0]), float(rv[1])
            if lo > info["min"] or hi < info["max"]:
                n += 1

    return n


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_datetime(series: pd.Series) -> pd.Series:
    if series.dtype.kind == "M":
        return series
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            return pd.to_datetime(series, errors="coerce", format="mixed")
        except Exception:
            return pd.to_datetime(series, errors="coerce")


def _as_date(v: Any) -> datetime.date:
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    return pd.Timestamp(v).date()
