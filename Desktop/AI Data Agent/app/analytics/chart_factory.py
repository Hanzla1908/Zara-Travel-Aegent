"""Chart factory — themed Plotly figure builders.

Every public function returns a `go.Figure` or `None` when the data doesn't
warrant a chart (too few rows, single-value column, etc.).  The caller is
responsible for `st.plotly_chart(fig, use_container_width=True)`.

Design rules
------------
- White background, Inter font, light grid
- Consistent 15-colour qualitative palette
- No chart title inside the figure — caller wraps in a section header
- Tooltips always enabled
- No mode-bar (clean embed look)
"""

from __future__ import annotations

import warnings
from typing import Sequence

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np


# ── Palette ──────────────────────────────────────────────────────────────────

QUAL_COLORS = [
    "#2563eb", "#7c3aed", "#10b981", "#f59e0b", "#ef4444",
    "#0891b2", "#be185d", "#059669", "#d97706", "#dc2626",
    "#6366f1", "#8b5cf6", "#14b8a6", "#f97316", "#f43f5e",
]

_FONT = "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
_TEXT_COLOR = "#1a2332"
_MUTED_COLOR = "#64748b"
_GRID_COLOR = "#f0f4f8"
_LINE_COLOR = "#e2e8f0"


# ── Theme helper ─────────────────────────────────────────────────────────────

def _theme(fig: go.Figure, height: int = 340) -> go.Figure:
    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family=_FONT, color=_TEXT_COLOR, size=12),
        margin=dict(t=12, b=48, l=12, r=12),
        height=height,
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            font=dict(size=11, color=_MUTED_COLOR),
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
        ),
        colorway=QUAL_COLORS,
        hoverlabel=dict(
            bgcolor="white",
            bordercolor="#e2e8f0",
            font_size=12,
            font_family=_FONT,
            font_color=_TEXT_COLOR,
        ),
    )
    fig.update_xaxes(
        gridcolor=_GRID_COLOR,
        linecolor=_LINE_COLOR,
        tickfont=dict(size=11, color=_MUTED_COLOR),
        title_font=dict(size=12, color=_MUTED_COLOR),
        showgrid=False,
        zeroline=False,
    )
    fig.update_yaxes(
        gridcolor=_GRID_COLOR,
        linecolor="rgba(0,0,0,0)",
        tickfont=dict(size=11, color=_MUTED_COLOR),
        title_font=dict(size=12, color=_MUTED_COLOR),
        showgrid=True,
        zeroline=False,
    )
    return fig


def _no_chart() -> None:
    return None


def _get_numeric(df: pd.DataFrame, col: str) -> pd.Series:
    """Return col as numeric, coercing silently."""
    return pd.to_numeric(df[col], errors="coerce")


def _get_datetime(df: pd.DataFrame, col: str) -> pd.Series:
    """Return col as datetime, coercing silently."""
    s = df[col]
    if s.dtype.kind == "M":
        return s
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            return pd.to_datetime(s, errors="coerce", format="mixed")
        except Exception:
            return pd.to_datetime(s, errors="coerce")


# ── Granularity helper ────────────────────────────────────────────────────────

def _granularity(date_range_days: int) -> str:
    if date_range_days <= 90:
        return "D"
    if date_range_days <= 730:
        return "W"
    if date_range_days <= 3650:
        return "MS"
    return "QS"


def _freq_label(freq: str) -> str:
    return {"D": "Day", "W": "Week", "MS": "Month", "QS": "Quarter"}.get(freq, freq)


# ── Time series ───────────────────────────────────────────────────────────────

def time_series(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
    agg: str = "auto",
    color_col: str | None = None,
    height: int = 320,
) -> go.Figure | None:
    """Line chart of value_col aggregated over time."""
    if df is None or len(df) < 4:
        return None

    dates = _get_datetime(df, date_col)
    values = _get_numeric(df, value_col)
    mask = dates.notna() & values.notna()
    if mask.sum() < 4:
        return None

    work = df[mask].copy()
    work["__date"] = dates[mask]
    work["__val"] = values[mask]

    date_range = int((work["__date"].max() - work["__date"].min()).days)
    freq = _granularity(date_range)

    if agg == "auto":
        agg = "sum"

    if color_col and color_col in work.columns and work[color_col].nunique() <= 10:
        grouped = (
            work.groupby([pd.Grouper(key="__date", freq=freq), color_col])["__val"]
            .agg(agg)
            .reset_index()
        )
        grouped.columns = [date_col, color_col, value_col]
        fig = px.line(
            grouped,
            x=date_col,
            y=value_col,
            color=color_col,
            color_discrete_sequence=QUAL_COLORS,
            markers=len(grouped) <= 60,
        )
    else:
        grouped = (
            work.groupby(pd.Grouper(key="__date", freq=freq))["__val"]
            .agg(agg)
            .reset_index()
        )
        grouped.columns = [date_col, value_col]
        fig = px.line(
            grouped,
            x=date_col,
            y=value_col,
            color_discrete_sequence=[QUAL_COLORS[0]],
            markers=len(grouped) <= 60,
        )
        # fill area
        fig.update_traces(fill="tozeroy", fillcolor="rgba(37,99,235,0.07)", line_width=2)

    fig.update_traces(
        hovertemplate=f"<b>%{{x}}</b><br>{value_col}: %{{y:,.2f}}<extra></extra>"
    )
    return _theme(fig, height)


def time_series_multi(
    df: pd.DataFrame,
    date_col: str,
    value_cols: Sequence[str],
    agg: str = "sum",
    height: int = 320,
) -> go.Figure | None:
    """Line chart with multiple value columns overlaid."""
    cols = [c for c in value_cols if c in df.columns]
    if len(cols) < 2:
        return None
    dates = _get_datetime(df, date_col)
    mask = dates.notna()
    if mask.sum() < 4:
        return None

    work = df[mask].copy()
    work["__date"] = dates[mask]

    date_range = int((work["__date"].max() - work["__date"].min()).days)
    freq = _granularity(date_range)

    grouped = work.groupby(pd.Grouper(key="__date", freq=freq))[cols].agg(agg).reset_index()
    grouped.rename(columns={"__date": date_col}, inplace=True)

    long = grouped.melt(id_vars=date_col, value_vars=cols, var_name="Metric", value_name="Value")
    fig = px.line(
        long,
        x=date_col,
        y="Value",
        color="Metric",
        color_discrete_sequence=QUAL_COLORS,
        markers=len(grouped) <= 60,
    )
    fig.update_traces(hovertemplate="<b>%{x}</b><br>%{fullData.name}: %{y:,.2f}<extra></extra>")
    return _theme(fig, height)


# ── Distribution charts ───────────────────────────────────────────────────────

def histogram(
    df: pd.DataFrame,
    col: str,
    nbins: int = 30,
    height: int = 280,
) -> go.Figure | None:
    values = _get_numeric(df, col).dropna()
    if len(values) < 5 or values.nunique() < 4:
        return None

    fig = px.histogram(
        values,
        nbins=nbins,
        color_discrete_sequence=[QUAL_COLORS[0]],
    )
    fig.update_traces(
        marker_line_width=0,
        opacity=0.85,
        hovertemplate="<b>%{x}</b><br>Count: %{y}<extra></extra>",
    )
    fig.update_layout(xaxis_title=col, yaxis_title="Count", showlegend=False)
    return _theme(fig, height)


def box_plot(
    df: pd.DataFrame,
    value_col: str,
    group_col: str | None = None,
    height: int = 280,
) -> go.Figure | None:
    values = _get_numeric(df, value_col).dropna()
    if len(values) < 5:
        return None

    if group_col and group_col in df.columns:
        n_groups = df[group_col].nunique()
        if 2 <= n_groups <= 15:
            work = df[[group_col, value_col]].copy()
            work[value_col] = _get_numeric(work, value_col)
            work = work.dropna(subset=[value_col])
            fig = px.box(
                work,
                x=group_col,
                y=value_col,
                color=group_col,
                color_discrete_sequence=QUAL_COLORS,
            )
            fig.update_layout(showlegend=False)
            return _theme(fig, height)

    fig = go.Figure(go.Box(
        y=values,
        marker_color=QUAL_COLORS[0],
        line_color=QUAL_COLORS[0],
        fillcolor="rgba(37,99,235,0.12)",
        name=value_col,
        hoverinfo="y",
        boxmean="sd",
    ))
    fig.update_layout(yaxis_title=value_col, showlegend=False)
    return _theme(fig, height)


# ── Category charts ───────────────────────────────────────────────────────────

def bar_ranked(
    df: pd.DataFrame,
    cat_col: str,
    value_col: str,
    agg: str = "sum",
    top_n: int = 15,
    orientation: str = "h",
    height: int = 300,
) -> go.Figure | None:
    """Horizontal (or vertical) bar — top-N categories by aggregated value."""
    if cat_col not in df.columns or value_col not in df.columns:
        return None
    work = df[[cat_col, value_col]].copy()
    work[value_col] = _get_numeric(work, value_col)
    work = work.dropna(subset=[value_col])
    n_cats = work[cat_col].nunique()
    if n_cats < 2 or n_cats > 200:
        return None

    grouped = (
        work.groupby(cat_col, observed=True)[value_col]
        .agg(agg)
        .sort_values(ascending=(orientation == "h"))
        .tail(top_n)
        .reset_index()
    )

    fig = px.bar(
        grouped,
        x=value_col if orientation == "h" else cat_col,
        y=cat_col if orientation == "h" else value_col,
        orientation=orientation,
        color_discrete_sequence=[QUAL_COLORS[0]],
    )
    fig.update_traces(
        marker_line_width=0,
        hovertemplate=f"<b>%{{{'y' if orientation=='h' else 'x'}}}</b><br>{value_col}: %{{{'x' if orientation=='h' else 'y'}:,.2f}}<extra></extra>",
    )
    if orientation == "h":
        # Clamp label length for readability
        grouped[cat_col] = grouped[cat_col].astype(str).str[:30]
        fig.update_yaxes(ticktext=grouped[cat_col], tickvals=grouped[cat_col])
    fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="")
    estimated_height = max(height, min(40 * min(n_cats, top_n), 600))
    return _theme(fig, estimated_height)


def donut(
    df: pd.DataFrame,
    cat_col: str,
    value_col: str | None = None,
    top_n: int = 8,
    height: int = 300,
) -> go.Figure | None:
    """Donut / pie chart — works for low-cardinality columns."""
    if cat_col not in df.columns:
        return None
    n_cats = df[cat_col].nunique()
    if n_cats < 2 or n_cats > top_n + 2:
        return None

    if value_col and value_col in df.columns:
        work = df[[cat_col, value_col]].copy()
        work[value_col] = _get_numeric(work, value_col)
        work = work.dropna(subset=[value_col])
        grouped = work.groupby(cat_col, observed=True)[value_col].sum().nlargest(top_n).reset_index()
        values_series = grouped[value_col]
        labels_series = grouped[cat_col].astype(str)
    else:
        vc = df[cat_col].value_counts().head(top_n)
        labels_series = vc.index.astype(str)
        values_series = vc.values

    fig = go.Figure(go.Pie(
        labels=labels_series,
        values=values_series,
        hole=0.55,
        marker=dict(colors=QUAL_COLORS[:top_n], line=dict(color="white", width=2)),
        textinfo="percent+label",
        textfont=dict(size=11),
        hovertemplate="<b>%{label}</b><br>Value: %{value:,.0f}<br>Share: %{percent}<extra></extra>",
    ))
    return _theme(fig, height)


def grouped_bar(
    df: pd.DataFrame,
    cat_col: str,
    value_cols: Sequence[str],
    top_n: int = 10,
    height: int = 320,
) -> go.Figure | None:
    """Grouped bar chart for multiple value columns across categories."""
    cols = [c for c in value_cols if c in df.columns]
    if len(cols) < 2 or cat_col not in df.columns:
        return None
    n_cats = df[cat_col].nunique()
    if n_cats < 2 or n_cats > 50:
        return None

    work = df[[cat_col] + cols].copy()
    for c in cols:
        work[c] = _get_numeric(work, c)
    grouped = work.groupby(cat_col, observed=True)[cols].sum().reset_index()
    # Sort by first metric, take top_n
    grouped = grouped.sort_values(cols[0], ascending=False).head(top_n)
    long = grouped.melt(id_vars=cat_col, value_vars=cols, var_name="Metric", value_name="Value")

    fig = px.bar(
        long,
        x=cat_col,
        y="Value",
        color="Metric",
        barmode="group",
        color_discrete_sequence=QUAL_COLORS,
    )
    fig.update_traces(marker_line_width=0)
    fig.update_layout(xaxis_title="", yaxis_title="")
    return _theme(fig, height)


# ── Correlation charts ────────────────────────────────────────────────────────

def correlation_heatmap(
    df: pd.DataFrame,
    num_cols: Sequence[str],
    height: int = 360,
) -> go.Figure | None:
    """Correlation matrix heatmap."""
    cols = [c for c in num_cols if c in df.columns]
    if len(cols) < 3:
        return None

    num_df = df[cols].apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")
    num_df = num_df[[c for c in num_df.columns if num_df[c].std() > 0]]
    if num_df.shape[1] < 3:
        return None

    corr = num_df.corr().round(2)
    # truncate long names
    short_names = [str(c)[:18] for c in corr.columns]

    fig = px.imshow(
        corr.values,
        x=short_names,
        y=short_names,
        color_continuous_scale="RdBu_r",
        range_color=[-1, 1],
        text_auto=True,
        aspect="auto",
    )
    fig.update_traces(
        texttemplate="%{z:.2f}",
        textfont=dict(size=10),
        hovertemplate="<b>%{x}</b> vs <b>%{y}</b><br>r = %{z:.2f}<extra></extra>",
    )
    fig.update_layout(
        coloraxis_colorbar=dict(
            tickfont=dict(size=10, color=_MUTED_COLOR),
            title_font=dict(size=11, color=_MUTED_COLOR),
            thickness=12,
            len=0.8,
        )
    )
    return _theme(fig, height)


def scatter_trend(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    color_col: str | None = None,
    height: int = 300,
) -> go.Figure | None:
    """Scatter with optional OLS trend line."""
    if x_col not in df.columns or y_col not in df.columns:
        return None
    work = df[[x_col, y_col] + ([color_col] if color_col and color_col in df.columns else [])].copy()
    work[x_col] = _get_numeric(work, x_col)
    work[y_col] = _get_numeric(work, y_col)
    work = work.dropna(subset=[x_col, y_col])
    if len(work) < 10:
        return None

    kwargs: dict = dict(
        x=x_col,
        y=y_col,
        opacity=0.65,
        trendline="ols",
        trendline_color_override="#ef4444",
    )
    if color_col and color_col in work.columns and work[color_col].nunique() <= 10:
        kwargs["color"] = color_col
        kwargs["color_discrete_sequence"] = QUAL_COLORS
    else:
        kwargs["color_discrete_sequence"] = [QUAL_COLORS[0]]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            fig = px.scatter(work, **kwargs)
        except Exception:
            fig = px.scatter(work, x=x_col, y=y_col, opacity=0.65,
                             color_discrete_sequence=[QUAL_COLORS[0]])

    fig.update_traces(
        marker=dict(size=6, line=dict(width=0)),
        hovertemplate=f"<b>{x_col}</b>: %{{x:,.2f}}<br><b>{y_col}</b>: %{{y:,.2f}}<extra></extra>",
        selector=dict(mode="markers"),
    )
    return _theme(fig, height)


# ── Summary table ─────────────────────────────────────────────────────────────

def summary_stats(df: pd.DataFrame, num_cols: Sequence[str]) -> pd.DataFrame | None:
    """Compact describe() for numeric columns."""
    cols = [c for c in num_cols if c in df.columns]
    if not cols:
        return None
    result = (
        df[cols]
        .apply(pd.to_numeric, errors="coerce")
        .describe(percentiles=[0.25, 0.5, 0.75])
        .T
        .round(2)
    )
    result.index.name = "Column"
    result.columns = ["Count", "Mean", "Std", "Min", "25%", "50%", "75%", "Max"]
    return result
