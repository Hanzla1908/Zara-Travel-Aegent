"""Insight context builder.

Produces a compact, validated text summary of a DataFrame's statistics for
sending to Claude.  Raw rows are never included.  The output is capped at
roughly 3 000 characters so API calls stay predictable.
"""

from __future__ import annotations

import math
import textwrap
from typing import Any

import numpy as np
import pandas as pd

from app.analytics.column_intelligence import ColumnIntel


# ── Public entry point ────────────────────────────────────────────────────────

def build_context(
    df: pd.DataFrame,
    intel: ColumnIntel,
    full_df: pd.DataFrame | None = None,
    max_chars: int = 3_200,
) -> str:
    """Return a compact, human-readable stats context for a Claude prompt.

    Parameters
    ----------
    df:       The (possibly filtered) DataFrame to summarise.
    intel:    ColumnIntel classification for the original dataset.
    full_df:  The unfiltered DataFrame, used to note when a filter is active.
    max_chars: Soft character budget for the returned string.
    """
    parts: list[str] = []

    # ── Shape & filter state ──────────────────────────────────────────────
    n_rows, n_cols = df.shape
    shape_line = f"Shape: {n_rows:,} rows × {n_cols} columns"
    if full_df is not None and len(full_df) != n_rows:
        pct = n_rows / len(full_df) * 100
        shape_line += f" (filtered — {pct:.0f}% of {len(full_df):,} total rows)"
    parts.append(shape_line)

    # ── Date range ────────────────────────────────────────────────────────
    if intel.primary_date and intel.primary_date in df.columns:
        date_summary = _date_summary(df[intel.primary_date])
        if date_summary:
            parts.append(f"Date range ({intel.primary_date}): {date_summary}")

    # ── Numeric column stats ──────────────────────────────────────────────
    all_num = _dedup([*intel.kpi_cols, *intel.mean_cols, *intel.dist_cols])
    num_in_df = [c for c in all_num if c in df.columns]
    if num_in_df:
        parts.append("\nNUMERIC COLUMNS")
        for col in num_in_df[:8]:
            line = _numeric_summary(df[col], col)
            if line:
                parts.append(f"  {line}")

    # ── Categorical top values ────────────────────────────────────────────
    cat_in_df = [c for c in intel.cat_cols if c in df.columns]
    if cat_in_df:
        parts.append("\nCATEGORICAL COLUMNS")
        for col in cat_in_df[:5]:
            line = _cat_summary(df[col], col)
            if line:
                parts.append(f"  {line}")

    # ── Category × numeric aggregations ──────────────────────────────────
    if cat_in_df and num_in_df:
        agg_block = _category_agg(df, intel, cat_in_df, num_in_df)
        if agg_block:
            parts.append("\nCATEGORY PERFORMANCE")
            parts.extend(f"  {ln}" for ln in agg_block)

    # ── Correlation highlights ────────────────────────────────────────────
    corr_lines = _top_correlations(df, num_in_df)
    if corr_lines:
        parts.append("\nCORRELATION HIGHLIGHTS")
        parts.extend(f"  {ln}" for ln in corr_lines)

    # ── Quality flags ─────────────────────────────────────────────────────
    quality_lines = _quality_flags(df, intel)
    if quality_lines:
        parts.append("\nDATA QUALITY FLAGS")
        parts.extend(f"  {ln}" for ln in quality_lines)

    text = "\n".join(parts)

    # Trim to budget without cutting mid-line
    if len(text) > max_chars:
        lines = text.split("\n")
        kept: list[str] = []
        total = 0
        for ln in lines:
            if total + len(ln) + 1 > max_chars:
                kept.append("  … (additional columns omitted for brevity)")
                break
            kept.append(ln)
            total += len(ln) + 1
        text = "\n".join(kept)

    return text


# ── Section helpers ───────────────────────────────────────────────────────────

def _date_summary(series: pd.Series) -> str:
    try:
        dt = pd.to_datetime(series, errors="coerce").dropna()
        if dt.empty:
            return ""
        span = (dt.max() - dt.min()).days
        return f"{dt.min().date()} → {dt.max().date()} ({span:,} days)"
    except Exception:
        return ""


def _numeric_summary(series: pd.Series, col: str) -> str:
    try:
        arr = pd.to_numeric(series, errors="coerce").dropna()
        if len(arr) < 2:
            return ""
        label = _humanise(col)
        mn, mx = _fmt(arr.min()), _fmt(arr.max())
        mean, med = _fmt(arr.mean()), _fmt(arr.median())
        std = _fmt(arr.std())
        skew = round(float(arr.skew()), 2)
        skew_note = ""
        if abs(skew) > 1:
            skew_note = f", skew={skew:+.1f} ({'right' if skew > 0 else 'left'}-skewed)"
        null_pct = series.isna().mean() * 100
        null_note = f", {null_pct:.0f}% missing" if null_pct >= 5 else ""
        return f"{label}: min={mn}, max={mx}, mean={mean}, median={med}, std={std}{skew_note}{null_note}"
    except Exception:
        return ""


def _cat_summary(series: pd.Series, col: str) -> str:
    try:
        label = _humanise(col)
        n_unique = series.nunique()
        vc = series.astype(str).value_counts().head(5)
        top = ", ".join(f"{v}({c:,})" for v, c in vc.items())
        null_pct = series.isna().mean() * 100
        null_note = f", {null_pct:.0f}% missing" if null_pct >= 5 else ""
        return f"{label}: {n_unique} unique — top: {top}{null_note}"
    except Exception:
        return ""


def _category_agg(
    df: pd.DataFrame,
    intel: ColumnIntel,
    cat_cols: list[str],
    num_cols: list[str],
) -> list[str]:
    lines: list[str] = []
    primary_cat = intel.primary_category
    if not primary_cat or primary_cat not in df.columns:
        primary_cat = cat_cols[0]

    primary_num = num_cols[0]
    agg_fn = "mean" if primary_num in intel.mean_cols else "sum"

    try:
        grp = (
            df.groupby(primary_cat, observed=True)[primary_num]
            .agg(agg_fn)
            .dropna()
            .sort_values(ascending=False)
        )
        if grp.empty or len(grp) < 2:
            return []

        label_cat = _humanise(primary_cat)
        label_num = _humanise(primary_num)
        fn_label = "mean" if agg_fn == "mean" else "total"

        top3 = grp.head(3)
        bot3 = grp.tail(3).sort_values(ascending=True)

        top_str = ", ".join(f"{k}({_fmt(v)})" for k, v in top3.items())
        bot_str = ", ".join(f"{k}({_fmt(v)})" for k, v in bot3.items())
        lines.append(f"{label_cat} by {fn_label} {label_num}:")
        lines.append(f"  Top: {top_str}")
        lines.append(f"  Bottom: {bot_str}")
        lines.append(f"  Range: {_fmt(grp.min())} – {_fmt(grp.max())}, ratio {_fmt(grp.max() / grp.min()) if grp.min() != 0 else 'N/A'}×")
    except Exception:
        pass

    return lines


def _top_correlations(df: pd.DataFrame, num_cols: list[str]) -> list[str]:
    cols = [c for c in num_cols[:10] if c in df.columns]
    if len(cols) < 3:
        return []
    try:
        work = df[cols].apply(pd.to_numeric, errors="coerce")
        valid = [c for c in work.columns if work[c].std() > 0]
        if len(valid) < 2:
            return []
        corr = work[valid].corr().abs()
        np.fill_diagonal(corr.values, 0)
        stacked = corr.stack().sort_values(ascending=False)
        seen: set[frozenset] = set()
        lines: list[str] = []
        for (a, b), val in stacked.items():
            pair = frozenset([a, b])
            if pair in seen or val < 0.1:
                continue
            seen.add(pair)
            direction = "positive" if work[valid].corr().loc[a, b] > 0 else "negative"  # type: ignore[arg-type]
            lines.append(f"{_humanise(str(a))} ↔ {_humanise(str(b))}: r={val:.2f} ({direction})")
            if len(lines) >= 4:
                break
        return lines
    except Exception:
        return []


def _quality_flags(df: pd.DataFrame, intel: ColumnIntel) -> list[str]:
    flags: list[str] = []

    # Missing values
    missing = df.isna().mean()
    high_missing = missing[missing >= 0.10].sort_values(ascending=False)
    for col, pct in high_missing.head(4).items():
        flags.append(f"{_humanise(str(col))}: {pct*100:.0f}% missing")

    # Constant columns
    for col in df.columns:
        try:
            if df[col].nunique() == 1:
                flags.append(f"{_humanise(col)}: constant (all same value)")
        except Exception:
            pass

    # Duplicates
    dup = int(df.duplicated().sum())
    if dup > 0:
        flags.append(f"{dup:,} duplicate rows ({dup/len(df)*100:.1f}%)")

    # String-typed numerics
    if intel.numeric_as_string:
        for col in intel.numeric_as_string[:3]:
            flags.append(f"{_humanise(col)}: numbers stored as text (needs conversion)")

    # String-typed dates
    if intel.datetime_as_string:
        for col in intel.datetime_as_string[:3]:
            flags.append(f"{_humanise(col)}: dates stored as text (needs conversion)")

    return flags[:8]


# ── Formatting helpers ────────────────────────────────────────────────────────

def _humanise(col: str) -> str:
    return col.replace("_", " ").replace("-", " ").title()


def _fmt(v: Any) -> str:
    if v is None:
        return "N/A"
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return "N/A"
        if abs(f) >= 1_000_000:
            return f"{f/1_000_000:.2f}M"
        if abs(f) >= 1_000:
            return f"{f:,.0f}"
        if abs(f) >= 100:
            return f"{f:.1f}"
        if abs(f) >= 1:
            return f"{f:.2f}"
        return f"{f:.4f}"
    except (TypeError, ValueError):
        return str(v)


def _dedup(lst: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in lst:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
