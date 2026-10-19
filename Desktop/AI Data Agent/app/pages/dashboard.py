"""Dynamic Dashboard — auto-generated from uploaded data.

Filters live in the sidebar (rendered by sidebar.py).  This page reads filter
state from session_state, applies them via filter_service, and builds charts
from the resulting filtered DataFrame.  Every chart, KPI card and table
updates consistently whenever a filter changes.

Layout
------
  Intel banner        — detected column types
  Active-filter pill  — "X filters active · N of M rows"
  KPI cards row
  Time trends         — only when a date column is found
  Category analysis   — only when cat + numeric columns are found
  Distributions       — histogram grid for numeric columns
  Correlations        — heatmap + scatter, only when ≥3 numeric cols
  Summary table       — descriptive statistics (expandable)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from app.analytics.column_intelligence import analyze, describe, ColumnIntel
from app.analytics.kpi_engine import compute_kpis
from app.services.filter_service import (
    build_options, apply_filters, active_count, all_filter_keys,
)
import app.analytics.chart_factory as cf
from app.components.icons import icon as svg_icon
from app.components.cards import page_header, section_title, empty_state


# ── Page entry point ─────────────────────────────────────────────────────────

def render() -> None:
    page_header(
        "Dashboard",
        "Auto-generated charts and KPIs — use the Filters panel in the sidebar to slice the data.",
    )

    df: pd.DataFrame | None = st.session_state.get("df")
    if df is None or df.empty:
        empty_state(
            svg_icon("bar-chart-2", 48, "#cbd5e1"),
            "No dataset loaded",
            "Upload a CSV or Excel file in the sidebar to generate an automatic dashboard.",
        )
        return

    intel = _get_intel(df)

    if not intel.has_numerics and not intel.has_time_data and not intel.has_categories:
        st.info("No analysable columns were detected. Try uploading a file with numeric or categorical data.")
        return

    # ── Apply sidebar filters ────────────────────────────────────────────
    opts          = build_options(df, intel)
    filtered_df   = apply_filters(df, intel, st.session_state, opts)
    n_active      = active_count(st.session_state, opts)
    is_filtered   = len(filtered_df) < len(df)

    # ── Intel banner ─────────────────────────────────────────────────────
    _render_intel_banner(intel, filtered_df, df, n_active, is_filtered)

    # ── KPI cards ────────────────────────────────────────────────────────
    _render_kpi_section(filtered_df, intel, df)

    # ── Chart sections ────────────────────────────────────────────────────
    if intel.has_time_data:
        _render_time_section(filtered_df, intel)

    if intel.has_categories and intel.has_numerics:
        _render_category_section(filtered_df, intel)

    if intel.has_numerics:
        _render_distribution_section(filtered_df, intel)

    all_num = intel.kpi_cols + intel.mean_cols + intel.dist_cols
    if len(all_num) >= 3:
        _render_correlation_section(filtered_df, intel)

    _render_summary_table(filtered_df, intel)


# ── Column intelligence (cached per-df instance) ──────────────────────────────

def _get_intel(df: pd.DataFrame) -> ColumnIntel:
    key = f"_intel_{id(df)}"
    if key not in st.session_state:
        st.session_state[key] = analyze(df)
    return st.session_state[key]


# ── Intel + filter status banner ─────────────────────────────────────────────

def _render_intel_banner(
    intel: ColumnIntel,
    filtered_df: pd.DataFrame,
    df: pd.DataFrame,
    n_active: int,
    is_filtered: bool,
) -> None:
    parts: list[str] = []
    if intel.date_cols:
        parts.append(svg_icon("calendar", 13, "#64748b") + f' <strong>{len(intel.date_cols)}</strong> date col{"s" if len(intel.date_cols)>1 else ""}')
    total_num = len(intel.kpi_cols) + len(intel.mean_cols) + len(intel.dist_cols)
    if total_num:
        parts.append(svg_icon("bar-chart-2", 13, "#64748b") + f' <strong>{total_num}</strong> numeric col{"s" if total_num>1 else ""}')
    if intel.cat_cols:
        parts.append(svg_icon("tag", 13, "#64748b") + f' <strong>{len(intel.cat_cols)}</strong> categorical col{"s" if len(intel.cat_cols)>1 else ""}')
    if intel.id_cols:
        parts.append(svg_icon("key", 13, "#64748b") + f' <strong>{len(intel.id_cols)}</strong> ID col{"s" if len(intel.id_cols)>1 else ""} skipped')

    if is_filtered:
        pct = len(filtered_df) / len(df) * 100
        filter_badge = (
            f'<span style="background:#2563eb;color:#fff;border-radius:6px;'
            f'padding:2px 8px;font-size:11px;font-weight:700;margin-left:4px;">'
            f'{len(filtered_df):,} / {len(df):,} rows ({pct:.0f}%)</span>'
        )
    else:
        filter_badge = (
            f'<span style="background:#f0f4f8;color:#64748b;border-radius:6px;'
            f'padding:2px 8px;font-size:11px;margin-left:4px;">'
            f'{len(df):,} rows</span>'
        )

    badge_html = " &nbsp;·&nbsp; ".join(parts)
    st.markdown(
        f"""<div style="background:#f0f4f8;border-radius:8px;padding:10px 16px;
                        font-size:13px;color:#1a2332;margin-bottom:16px;
                        display:flex;align-items:center;flex-wrap:wrap;gap:6px;">
              <span>{badge_html}</span>
              {filter_badge}
            </div>""",
        unsafe_allow_html=True,
    )

    if intel.datetime_as_string:
        st.info(
            f"**{', '.join(intel.datetime_as_string[:3])}** look like dates stored as text. "
            "Convert them in Data Explorer for richer time-series charts."
        )


# ── KPI cards ─────────────────────────────────────────────────────────────────

def _render_kpi_section(
    filtered_df: pd.DataFrame,
    intel: ColumnIntel,
    full_df: pd.DataFrame,
) -> None:
    cards = compute_kpis(filtered_df, intel, full_df, max_cards=5)
    if not cards:
        return

    cols = st.columns(len(cards))
    for card, col in zip(cards, cols):
        with col:
            delta_color = "#10b981" if card.delta_positive else "#ef4444"
            delta_html = (
                f'<div style="font-size:12px;color:{delta_color};margin-top:4px;">'
                f'{card.delta}</div>'
                if card.delta else ""
            )
            st.markdown(
                f"""<div class="metric-card" style="position:relative;">
                  <div style="font-size:22px;line-height:1;margin-bottom:2px;">{card.icon}</div>
                  <div style="font-size:11px;color:#64748b;font-weight:500;text-transform:uppercase;
                              letter-spacing:0.04em;margin-bottom:6px;">{card.label}</div>
                  <div style="font-size:24px;font-weight:700;color:#1a2332;line-height:1.1;">
                    {card.value}
                  </div>
                  {delta_html}
                  <div style="font-size:10px;color:#94a3b8;margin-top:6px;">{card.sublabel}</div>
                </div>""",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)


# ── Time trends ───────────────────────────────────────────────────────────────

def _render_time_section(df: pd.DataFrame, intel: ColumnIntel) -> bool:
    date_col = intel.primary_date
    if not date_col or date_col not in df.columns:
        return False

    all_num = intel.kpi_cols + intel.mean_cols + intel.dist_cols
    num_in_df = [c for c in all_num if c in df.columns]
    if not num_in_df:
        return False

    section_title("Time Trends")

    if len(num_in_df) > 3:
        selected_cols = st.multiselect(
            "Metrics to chart",
            options=num_in_df,
            default=num_in_df[:2],
            key="_dash_time_cols",
        )
        if not selected_cols:
            selected_cols = num_in_df[:1]
    else:
        selected_cols = num_in_df

    if len(selected_cols) >= 2:
        fig = cf.time_series_multi(df, date_col, selected_cols)
    else:
        col = selected_cols[0] if selected_cols else num_in_df[0]
        agg = "mean" if col in intel.mean_cols else "sum"
        fig = cf.time_series(df, date_col, col, agg=agg)

    if fig is None:
        st.info("Not enough time-series data to draw a trend chart (need ≥ 4 data points).")
        return False

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    if intel.primary_category and len(selected_cols) == 1:
        cat = intel.primary_category
        n_unique = df[cat].nunique()
        if 2 <= n_unique <= 8:
            with st.expander(f"Show breakdown by {cat}"):
                fig2 = cf.time_series(
                    df, date_col, selected_cols[0],
                    agg="mean" if selected_cols[0] in intel.mean_cols else "sum",
                    color_col=cat,
                    height=260,
                )
                if fig2:
                    st.plotly_chart(fig2, use_container_width=True,
                                    config={"displayModeBar": False})
    return True


# ── Category analysis ─────────────────────────────────────────────────────────

def _render_category_section(df: pd.DataFrame, intel: ColumnIntel) -> bool:
    cat_cols = [c for c in intel.cat_cols if c in df.columns]
    all_num  = intel.kpi_cols + intel.mean_cols + intel.dist_cols
    num_cols = [c for c in all_num if c in df.columns]
    if not cat_cols or not num_cols:
        return False

    section_title("Category Analysis")

    primary_cat = intel.primary_category or cat_cols[0]
    primary_num = num_cols[0]
    agg = "mean" if primary_num in intel.mean_cols else "sum"

    c1, c2 = st.columns([3, 2])
    with c1:
        st.caption(f"**{primary_cat.replace('_',' ').title()}** — top by {primary_num}")
        fig = cf.bar_ranked(df, primary_cat, primary_num, agg=agg, top_n=15, orientation="h")
        if fig:
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Not enough category variation for a bar chart.")

    with c2:
        st.caption(f"**{primary_cat.replace('_',' ').title()}** — composition")
        fig2 = cf.donut(df, primary_cat, primary_num if agg == "sum" else None, top_n=8)
        if fig2 is None:
            fig2 = cf.donut(df, primary_cat, top_n=8)
        if fig2:
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    if len(num_cols) >= 2 and df[primary_cat].nunique() <= 20:
        with st.expander("Compare metrics by category"):
            fig3 = cf.grouped_bar(df, primary_cat, num_cols[:4], top_n=10)
            if fig3:
                st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})

    if len(num_cols) >= 1 and 2 <= df[primary_cat].nunique() <= 12:
        with st.expander(f"Distribution of {primary_num} by {primary_cat}"):
            fig4 = cf.box_plot(df, primary_num, group_col=primary_cat, height=260)
            if fig4:
                st.plotly_chart(fig4, use_container_width=True, config={"displayModeBar": False})

    return True


# ── Distributions ─────────────────────────────────────────────────────────────

def _render_distribution_section(df: pd.DataFrame, intel: ColumnIntel) -> bool:
    all_num  = intel.kpi_cols + intel.mean_cols + intel.dist_cols
    num_cols = [c for c in all_num if c in df.columns]
    plottable = [
        c for c in num_cols
        if pd.to_numeric(df[c], errors="coerce").dropna().nunique() >= 5
    ]
    if not plottable:
        return False

    section_title("Distributions")

    grid_cols = plottable[:6]
    rows = (len(grid_cols) + 1) // 2
    for row in range(rows):
        pair = grid_cols[row * 2: row * 2 + 2]
        ui_cols = st.columns(len(pair))
        for col_name, ui_col in zip(pair, ui_cols):
            with ui_col:
                st.caption(f"**{col_name.replace('_', ' ').title()}**")
                fig = cf.histogram(df, col_name)
                if fig:
                    st.plotly_chart(fig, use_container_width=True,
                                    config={"displayModeBar": False})
                else:
                    st.info("Not enough distinct values.")
    return True


# ── Correlations ──────────────────────────────────────────────────────────────

def _render_correlation_section(df: pd.DataFrame, intel: ColumnIntel) -> bool:
    all_num  = intel.kpi_cols + intel.mean_cols + intel.dist_cols
    num_cols = [c for c in all_num if c in df.columns]
    if len(num_cols) < 3:
        return False

    section_title("Correlations")

    c1, c2 = st.columns([3, 2])
    with c1:
        st.caption("**Correlation matrix**")
        fig = cf.correlation_heatmap(df, num_cols[:10], height=380)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Need ≥ 3 numeric columns with non-zero variance.")

    with c2:
        st.caption("**Top correlated pair**")
        top_pair = _top_correlated_pair(df, num_cols)
        if top_pair:
            x_col, y_col = top_pair
            cat_hint = intel.primary_category if intel.primary_category in df.columns else None
            fig2 = cf.scatter_trend(df, x_col, y_col, color_col=cat_hint, height=380)
            if fig2:
                st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Not enough data points for a scatter chart.")
    return True


# ── Summary table ─────────────────────────────────────────────────────────────

def _render_summary_table(df: pd.DataFrame, intel: ColumnIntel) -> None:
    all_num  = intel.kpi_cols + intel.mean_cols + intel.dist_cols
    num_cols = [c for c in all_num if c in df.columns]
    if not num_cols:
        return

    with st.expander("Descriptive statistics", expanded=False):
        stats = cf.summary_stats(df, num_cols)
        if stats is not None:
            st.dataframe(stats, use_container_width=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _top_correlated_pair(
    df: pd.DataFrame,
    num_cols: list[str],
) -> tuple[str, str] | None:
    cols = num_cols[:10]
    work = df[cols].apply(pd.to_numeric, errors="coerce")
    valid = [c for c in work.columns if work[c].std() > 0]
    if len(valid) < 2:
        return None
    corr = work[valid].corr().abs()
    np.fill_diagonal(corr.values, 0)
    idx = corr.stack().idxmax()
    return (str(idx[0]), str(idx[1]))
