"""Query Executor — safe analytical query execution from validated QueryPlan objects.

No arbitrary code is ever executed.  Every operation is an explicit Python call
against an allowlisted API.  All column references are validated by the planner
before this module sees them.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from app.analytics.query_planner import (
    QueryPlan, FilterSpec, MetricSpec, ALLOWED_AGGS,
)
import app.analytics.chart_factory as cf


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class ExecutionResult:
    df: pd.DataFrame | None   = None   # tabular result for display
    chart: go.Figure | None   = None   # Plotly figure (optional)
    summary_text: str         = ""     # compact text for Claude's explain prompt
    error: str                = ""     # non-empty on failure
    operation: str            = ""
    intent: str               = ""
    row_count: int            = 0      # rows in the original filtered df


# ── Public entry point ────────────────────────────────────────────────────────

def execute(plan: QueryPlan, df: pd.DataFrame) -> ExecutionResult:
    """Execute a validated QueryPlan.  Returns ExecutionResult."""
    try:
        filtered = _apply_filters(df, plan.filters)
        row_count = len(filtered)

        _ops = {
            "groupby_agg":  _groupby_agg,
            "time_series":  _time_series,
            "top_n":        _top_n,
            "distribution": _distribution,
            "correlation":  _correlation,
            "describe":     _describe,
            "cross_tab":    _cross_tab,
            "filter_agg":   _filter_agg,
        }
        fn = _ops.get(plan.operation)
        if fn is None:
            return ExecutionResult(error=f"Unsupported operation: {plan.operation}")

        result = fn(filtered, plan)
        result.operation = plan.operation
        result.intent    = plan.intent
        result.row_count = row_count
        return result

    except Exception as exc:
        return ExecutionResult(
            error=f"Execution error: {exc}",
            operation=plan.operation,
            intent=plan.intent,
        )


# ── Filter application ────────────────────────────────────────────────────────

def _apply_filters(df: pd.DataFrame, filters: list[FilterSpec]) -> pd.DataFrame:
    if not filters:
        return df

    mask = pd.Series(True, index=df.index)
    for f in filters:
        if f.column not in df.columns:
            continue
        col = df[f.column]
        try:
            if f.op in ("gt", "lt", "gte", "lte"):
                num_col = pd.to_numeric(col, errors="coerce")
                val = float(f.value)
                ops_map = {"gt": num_col.__gt__, "lt": num_col.__lt__,
                           "gte": num_col.__ge__, "lte": num_col.__le__}
                mask &= ops_map[f.op](val).fillna(False)
            elif f.op == "eq":
                mask &= (col == f.value)
            elif f.op == "ne":
                mask &= (col != f.value)
            elif f.op == "isin":
                vals = f.value if isinstance(f.value, list) else [f.value]
                mask &= col.isin(vals)
            elif f.op == "not_isin":
                vals = f.value if isinstance(f.value, list) else [f.value]
                mask &= ~col.isin(vals)
        except Exception:
            continue

    return df[mask]


# ── Operation handlers ────────────────────────────────────────────────────────

def _groupby_agg(df: pd.DataFrame, plan: QueryPlan) -> ExecutionResult:
    if not plan.group_by:
        return ExecutionResult(error="groupby_agg needs at least one group_by column.")
    if not plan.metrics:
        return ExecutionResult(error="groupby_agg needs at least one metric.")

    valid_groups = [c for c in plan.group_by if c in df.columns]
    if not valid_groups:
        return ExecutionResult(error="No valid group_by columns found in dataset.")

    agg_dict: dict[str, list[str]] = {}
    for m in plan.metrics:
        if m.column in df.columns:
            agg_dict.setdefault(m.column, []).append(m.agg)

    if not agg_dict:
        return ExecutionResult(error="No valid metric columns found in dataset.")

    result = df.groupby(valid_groups, observed=True).agg(agg_dict)

    # Flatten multi-level columns
    if isinstance(result.columns, pd.MultiIndex):
        result.columns = [
            f"{c}_{a}" if len(agg_dict.get(c, [])) > 1 else c
            for c, a in result.columns
        ]
    result = result.reset_index()

    result = _apply_sort(result, plan)
    result = result.head(plan.limit)

    num_cols = [c for c in result.columns if c not in valid_groups
                and pd.to_numeric(result[c], errors="coerce").notna().any()]
    chart = _make_chart(result, plan, valid_groups[0], num_cols[0] if num_cols else None)
    return ExecutionResult(df=result, chart=chart, summary_text=_summarise(result, plan.intent))


def _time_series(df: pd.DataFrame, plan: QueryPlan) -> ExecutionResult:
    date_col = plan.date_column
    if not date_col or date_col not in df.columns:
        return ExecutionResult(error=f"Date column '{date_col}' not found.")
    if not plan.metrics:
        return ExecutionResult(error="time_series needs at least one metric.")
    period = plan.period or "ME"

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            dates = pd.to_datetime(df[date_col], errors="coerce", format="mixed")
        except Exception:
            dates = pd.to_datetime(df[date_col], errors="coerce")

    if dates.isna().all():
        return ExecutionResult(error=f"'{date_col}' has no parsable dates.")

    work = df.copy()
    work["__dt__"] = dates
    work = work.dropna(subset=["__dt__"]).set_index("__dt__")

    agg_map: dict[str, str] = {}
    for m in plan.metrics:
        if m.column in work.columns:
            agg_map[m.column] = m.agg

    if not agg_map:
        return ExecutionResult(error="No valid metric columns for time_series.")

    result = (
        work[list(agg_map.keys())]
        .resample(period)
        .agg(agg_map)
        .dropna(how="all")
        .reset_index()
        .rename(columns={"__dt__": date_col})
    )

    metric_cols = list(agg_map.keys())
    if len(metric_cols) >= 2:
        fig = cf.time_series_multi(result, date_col, metric_cols)
    else:
        fig = cf.time_series(result, date_col, metric_cols[0], agg=agg_map[metric_cols[0]])

    display = result.tail(plan.limit).reset_index(drop=True)
    return ExecutionResult(df=display, chart=fig, summary_text=_summarise(result.tail(20), plan.intent))


def _top_n(df: pd.DataFrame, plan: QueryPlan) -> ExecutionResult:
    # If group_by + metrics — delegate to groupby_agg
    if plan.group_by and plan.metrics:
        return _groupby_agg(df, plan)

    # Otherwise sort the raw df
    sort_col = (plan.sort.column if plan.sort else None) or \
               (plan.metrics[0].column if plan.metrics else None) or \
               (plan.columns[0] if plan.columns else None)

    if not sort_col or sort_col not in df.columns:
        return ExecutionResult(error=f"Sort column not found for top_n.")

    ascending = plan.sort.ascending if plan.sort else False

    work = df.copy()
    try:
        work[sort_col] = pd.to_numeric(work[sort_col], errors="coerce")
    except Exception:
        pass

    sorted_df = work.sort_values(sort_col, ascending=ascending, na_position="last")

    show = list(dict.fromkeys(
        [c for c in plan.group_by + plan.columns + [sort_col] if c in sorted_df.columns]
    )) or list(sorted_df.columns[:6])

    result = sorted_df[show].head(plan.limit).reset_index(drop=True)
    chart = _make_chart(result, plan, show[0] if len(show) > 1 else None,
                        sort_col if sort_col in show else None)
    return ExecutionResult(df=result, chart=chart, summary_text=_summarise(result, plan.intent))


def _distribution(df: pd.DataFrame, plan: QueryPlan) -> ExecutionResult:
    cols = plan.columns or (plan.group_by[:1] if plan.group_by else [])
    if not cols or cols[0] not in df.columns:
        return ExecutionResult(error="distribution needs a valid column.")
    col = cols[0]

    numeric = pd.to_numeric(df[col], errors="coerce")
    if numeric.notna().sum() > df[col].isna().sum():
        # Numeric — histogram + describe
        fig = cf.histogram(df, col)
        desc = numeric.dropna().describe().round(3)
        result = desc.reset_index().rename(columns={"index": "statistic", col: "value"})
    else:
        # Categorical — value counts
        vc = df[col].value_counts().head(plan.limit).reset_index()
        vc.columns = [col, "count"]
        result = vc
        fig = cf.bar_ranked(result, col, "count", top_n=plan.limit, orientation="v")

    return ExecutionResult(df=result, chart=fig, summary_text=_summarise(result, plan.intent))


def _correlation(df: pd.DataFrame, plan: QueryPlan) -> ExecutionResult:
    cols = plan.columns
    if not cols:
        cols = [c for c in df.columns
                if pd.to_numeric(df[c], errors="coerce").notna().sum() > len(df) * 0.5][:10]
    valid = [c for c in cols if c in df.columns]
    if len(valid) < 2:
        return ExecutionResult(error="Need ≥ 2 numeric columns for correlation.")

    work = df[valid].apply(pd.to_numeric, errors="coerce")
    corr = work.corr().round(3)
    fig = cf.correlation_heatmap(df, valid)

    # Build a ranked pairs table for display
    pairs: list[dict] = []
    seen: set[frozenset] = set()
    stacked = corr.abs().stack().sort_values(ascending=False)
    for (a, b), val in stacked.items():
        pair = frozenset([a, b])
        if a == b or pair in seen or val < 0.05:
            continue
        seen.add(pair)
        direction = "positive" if corr.loc[a, b] > 0 else "negative"
        pairs.append({"column_A": a, "column_B": b, "correlation": round(corr.loc[a, b], 3), "direction": direction})

    result = pd.DataFrame(pairs) if pairs else corr.reset_index()
    return ExecutionResult(df=result, chart=fig, summary_text=_summarise(result.head(10), plan.intent))


def _describe(df: pd.DataFrame, plan: QueryPlan) -> ExecutionResult:
    cols = plan.columns
    if not cols:
        cols = [c for c in df.columns
                if pd.to_numeric(df[c], errors="coerce").notna().sum() > len(df) * 0.4][:8]
    valid = [c for c in cols if c in df.columns]
    if not valid:
        return ExecutionResult(error="No numeric columns to describe.")

    desc = (
        df[valid]
        .apply(pd.to_numeric, errors="coerce")
        .describe()
        .T
        .round(3)
        .reset_index()
        .rename(columns={"index": "column"})
    )
    return ExecutionResult(df=desc, chart=None, summary_text=_summarise(desc, plan.intent))


def _cross_tab(df: pd.DataFrame, plan: QueryPlan) -> ExecutionResult:
    if len(plan.group_by) < 2:
        return ExecutionResult(error="cross_tab needs exactly 2 group_by columns.")
    col1, col2 = plan.group_by[0], plan.group_by[1]
    for c in (col1, col2):
        if c not in df.columns:
            return ExecutionResult(error=f"Column '{c}' not found.")

    if plan.metrics:
        m = plan.metrics[0]
        if m.column not in df.columns:
            return ExecutionResult(error=f"Metric column '{m.column}' not found.")
        agg_fn = m.agg if m.agg in ALLOWED_AGGS else "sum"
        pivot = df.pivot_table(
            index=col1, columns=col2, values=m.column,
            aggfunc=agg_fn, fill_value=0,
        )
    else:
        pivot = pd.crosstab(df[col1], df[col2])

    result = pivot.reset_index()

    try:
        val_cols = [c for c in result.columns if c != col1]
        z = result.set_index(col1)[val_cols]
        fig = go.Figure(data=go.Heatmap(
            z=z.values.tolist(),
            x=[str(c) for c in z.columns],
            y=[str(r) for r in z.index],
            colorscale="Blues",
            text=z.values.tolist(),
            texttemplate="%{text:,.0f}",
            textfont={"size": 10},
        ))
        fig.update_layout(
            height=max(280, len(z.index) * 30 + 100),
            margin=dict(l=10, r=10, t=24, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
    except Exception:
        fig = None

    return ExecutionResult(df=result, chart=fig, summary_text=_summarise(result, plan.intent))


def _filter_agg(df: pd.DataFrame, plan: QueryPlan) -> ExecutionResult:
    if plan.metrics:
        row: dict[str, Any] = {}
        for m in plan.metrics:
            if m.column not in df.columns:
                continue
            s = pd.to_numeric(df[m.column], errors="coerce").dropna()
            fn_map = {
                "sum": s.sum, "mean": s.mean, "count": lambda: float(len(df)),
                "min": s.min, "max": s.max, "std": s.std,
                "median": s.median, "nunique": s.nunique,
            }
            fn = fn_map.get(m.agg, s.sum)
            try:
                row[f"{m.column} ({m.agg})"] = round(float(fn()), 4)
            except Exception:
                row[f"{m.column} ({m.agg})"] = None
        result = pd.DataFrame([row])
        return ExecutionResult(df=result, chart=None, summary_text=_summarise(result, plan.intent))

    # No metrics — show filtered rows
    cols_to_show = plan.columns or list(df.columns[:6])
    result = df[[c for c in cols_to_show if c in df.columns]].head(plan.limit).reset_index(drop=True)
    summary = f"Filtered to {len(df):,} rows.\n" + _summarise(result.head(5), plan.intent)
    return ExecutionResult(df=result, chart=None, summary_text=summary)


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _make_chart(
    df: pd.DataFrame,
    plan: QueryPlan,
    cat_col: str | None,
    val_col: str | None,
) -> go.Figure | None:
    if df is None or df.empty or not cat_col or not val_col:
        return None
    try:
        hint = plan.chart_hint
        if hint == "pie":
            return cf.donut(df, cat_col, val_col, top_n=min(8, plan.limit))
        if hint == "scatter":
            num_cols = [c for c in df.columns
                        if c != cat_col and pd.to_numeric(df[c], errors="coerce").notna().any()]
            if len(num_cols) >= 2:
                return cf.scatter_trend(df, num_cols[0], num_cols[1])
        if hint == "box":
            return cf.box_plot(df, val_col, group_col=cat_col)
        # default: bar
        return cf.bar_ranked(df, cat_col, val_col, top_n=plan.limit)
    except Exception:
        return None


# ── Sort helper ───────────────────────────────────────────────────────────────

def _apply_sort(df: pd.DataFrame, plan: QueryPlan) -> pd.DataFrame:
    if plan.sort and plan.sort.column:
        col = plan.sort.column
        if col in df.columns:
            return df.sort_values(col, ascending=plan.sort.ascending, na_position="last")
        # Try to find the column after aggregation (e.g. "revenue" → "revenue_sum")
        candidates = [c for c in df.columns if c.startswith(col.split("_")[0])]
        if candidates:
            return df.sort_values(candidates[0], ascending=plan.sort.ascending, na_position="last")
    return df


# ── Summary text ──────────────────────────────────────────────────────────────

def _summarise(df: pd.DataFrame, intent: str = "", max_rows: int = 20) -> str:
    if df is None or df.empty:
        return "No results."
    sample = df.head(max_rows)
    return (
        f"Intent: {intent}\n\n"
        f"Result ({len(df)} rows shown):\n"
        f"{sample.to_string(index=False, max_rows=max_rows)}"
    )
