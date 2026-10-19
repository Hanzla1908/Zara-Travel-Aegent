"""Data Explorer — searchable tables, column profiling, cleaning actions, statistics.

Tabs:
  Preview        — searchable/sortable/filterable table with column-type chips
  Column Profile — per-column stats, null heatmap, individual column drill-down
  Data Quality   — quality score, issue list
  Statistics     — descriptive stats, value-count charts, correlation heatmap
  Clean          — staged cleaning with preview + before/after quality metrics
  Export         — CSV / Excel download

Design contract:
  - _original_df is preserved across all cleaning operations.
  - Every cleaning action shows a preview before the user confirms.
  - Applying an operation updates st.session_state["df"] and appends to _clean_history.
  - Resetting restores _original_df and clears history.
  - Profile cache is keyed by id(df) and is invalidated whenever df changes.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components.cards import (
    page_header, metric_row, section_title, empty_state, content_card,
)
from app.analytics.profiler import profile as compute_profile, _dtype_category
from app.services.export_service import (
    to_csv_bytes, to_excel_bytes, to_chart_png, get_filtered_view,
)
from app.services.report_builder import build_html_report, build_excel_report
import app.analytics.chart_factory as cf


# ── Styling constants ────────────────────────────────────────────────────────

_DTYPE_STYLE: dict[str, tuple[str, str]] = {
    "numeric":     ("#dbeafe", "#1d4ed8"),
    "categorical": ("#ede9fe", "#6d28d9"),
    "datetime":    ("#d1fae5", "#065f46"),
    "boolean":     ("#fef3c7", "#92400e"),
    "other":       ("#f1f5f9", "#475569"),
}

_ISSUE_SEVERITY: dict[str, tuple[str, str]] = {
    "error":   ("#fee2e2", "#991b1b"),
    "warning": ("#fef3c7", "#92400e"),
    "info":    ("#dbeafe", "#1e40af"),
}


# ── Entry point ──────────────────────────────────────────────────────────────

def render() -> None:
    page_header("Data Explorer",
                "Inspect, clean, and export your dataset.")

    lr = st.session_state.get("load_result")
    df: pd.DataFrame | None = st.session_state.get("df")

    if df is None or lr is None:
        empty_state(
            "🔍", "No dataset loaded",
            "Upload a CSV, Excel, Parquet, or JSON file from the sidebar to begin.",
        )
        return

    # ── Preserve original when a new file is loaded ──────────────────────────
    lr_fp = f"{lr.filename}_{lr.rows}_{lr.columns}"
    if st.session_state.get("_explorer_orig_fp") != lr_fp:
        st.session_state["_original_df"]     = df.copy()
        st.session_state["_explorer_orig_fp"] = lr_fp
        st.session_state["_clean_history"]   = []

    orig_df: pd.DataFrame = st.session_state["_original_df"]

    # ── Sheet selector (Excel only) ──────────────────────────────────────────
    _maybe_render_sheet_selector(lr)
    lr = st.session_state["load_result"]
    df = st.session_state["df"]

    for w in lr.warnings:
        st.warning(w, icon="⚠️")

    # ── KPI strip ────────────────────────────────────────────────────────────
    dup        = int(df.duplicated().sum())
    null_cells = int(df.isna().sum().sum())
    tot_cells  = df.shape[0] * df.shape[1]
    row_delta  = len(orig_df) - df.shape[0]

    metric_row([
        {"label": "Rows",    "value": f"{df.shape[0]:,}",
         "delta": f"−{row_delta:,} cleaned" if row_delta > 0 else "",
         "delta_type": "positive" if row_delta > 0 else "neutral"},
        {"label": "Columns", "value": str(df.shape[1])},
        {"label": "Missing", "value": f"{null_cells:,}",
         "delta": f"{null_cells/tot_cells*100:.1f}%" if tot_cells else "0%",
         "delta_type": "negative" if null_cells > 0 else "neutral"},
        {"label": "Duplicates", "value": f"{dup:,}",
         "delta_type": "negative" if dup > 0 else "neutral"},
        {"label": "File type", "value": lr.file_type.upper()},
        {"label": "Memory",   "value": f"{round(df.memory_usage(deep=True).sum()/1024,0):.0f} KB"},
    ])

    # ── Profile (cached per df identity) ─────────────────────────────────────
    profile_key = f"_profile_{id(df)}"
    if st.session_state.get(profile_key) is None:
        with st.spinner("Profiling dataset…"):
            st.session_state[profile_key] = compute_profile(df)
    prof = st.session_state[profile_key]

    # ── Tabs ─────────────────────────────────────────────────────────────────
    (tab_preview, tab_profile, tab_quality,
     tab_stats, tab_clean, tab_export) = st.tabs([
        "📋 Preview",
        "🔬 Column Profile",
        "⚠️ Data Quality",
        "📊 Statistics",
        "🧹 Clean",
        "⬇️ Export",
    ])

    with tab_preview:
        _render_preview(df)

    with tab_profile:
        _render_column_profile(df, prof)

    with tab_quality:
        _render_quality(prof)

    with tab_stats:
        _render_statistics(df)

    with tab_clean:
        _render_clean(df, orig_df, prof)

    with tab_export:
        _render_export(df, lr)


# ── Sheet selector ───────────────────────────────────────────────────────────

def _maybe_render_sheet_selector(lr) -> None:
    from app.services.data_loader import reload_sheet

    if not lr.sheet_names or len(lr.sheet_names) <= 1:
        return

    col1, _ = st.columns([3, 5])
    with col1:
        new_sheet = st.selectbox(
            "Excel sheet",
            options=lr.sheet_names,
            index=lr.sheet_names.index(lr.active_sheet),
            key="sheet_sel",
        )

    if new_sheet != lr.active_sheet:
        raw = st.session_state.get("_raw_bytes", b"")
        if raw:
            with st.spinner(f"Loading sheet '{new_sheet}'…"):
                new_lr = reload_sheet(raw, lr.filename, new_sheet)
            st.session_state["load_result"] = new_lr
            st.session_state["df"]          = new_lr.df
            _invalidate_profile()
            st.rerun()


# ── Preview tab ──────────────────────────────────────────────────────────────

def _render_preview(df: pd.DataFrame) -> None:
    section_title("Filter & Display")

    c1, c2, c3, c4 = st.columns([3, 3, 2, 1])
    with c1:
        search = st.text_input(
            "Search rows",
            placeholder="Type to filter any column…",
            key="prev_search",
        )
    with c2:
        all_cols = df.columns.tolist()
        col_sel  = st.multiselect(
            "Visible columns",
            all_cols,
            default=all_cols[:min(10, len(all_cols))],
            key="prev_cols",
        )
    with c3:
        sort_col = st.selectbox(
            "Sort by",
            ["(none)"] + (col_sel or all_cols),
            key="prev_sort_col",
        )
    with c4:
        sort_asc = st.selectbox("Order", ["↑ Asc", "↓ Desc"], key="prev_sort_dir")

    view = df[col_sel] if col_sel else df.copy()

    if search:
        mask = view.apply(
            lambda c: c.astype(str).str.contains(search, case=False, na=False)
        ).any(axis=1)
        view = view[mask]

    if sort_col != "(none)" and sort_col in view.columns:
        view = view.sort_values(sort_col, ascending=(sort_asc == "↑ Asc"))

    row_limit = st.select_slider(
        "Rows to display",
        options=[50, 100, 500, 1_000, 5_000, "All"],
        value=100,
        key="prev_limit",
    )
    n = len(view) if row_limit == "All" else int(row_limit)
    shown = min(n, len(view))

    st.markdown(
        f'<div style="font-size:12px;color:#8a9aaa;margin:6px 0 4px;">'
        f'Showing <b>{shown:,}</b> of <b>{len(view):,}</b> rows'
        f'{"&nbsp;&nbsp;·&nbsp;&nbsp;filtered from <b>" + str(len(df)) + "</b> total" if search else ""}'
        f'</div>',
        unsafe_allow_html=True,
    )

    _render_column_chips(view.columns, df)

    st.dataframe(view.head(n), use_container_width=True, height=460)


def _render_column_chips(columns, df: pd.DataFrame) -> None:
    chips = ""
    for c in columns:
        cat = _dtype_category(df[c])
        bg, fg = _DTYPE_STYLE.get(cat, _DTYPE_STYLE["other"])
        chips += (
            f'<span style="display:inline-flex;align-items:center;gap:4px;'
            f'background:{bg};color:{fg};font-size:11px;font-weight:600;'
            f'padding:3px 8px;border-radius:99px;margin:2px 3px 2px 0;">'
            f'{c}<span style="opacity:.65;font-weight:400">{_dtype_label(df[c])}</span>'
            f'</span>'
        )
    if chips:
        st.markdown(
            f'<div style="margin-bottom:8px;line-height:2.2;">{chips}</div>',
            unsafe_allow_html=True,
        )


def _dtype_label(s: pd.Series) -> str:
    cat = _dtype_category(s)
    labels = {"numeric": " num", "categorical": " cat",
              "datetime": " date", "boolean": " bool", "other": ""}
    return labels.get(cat, "")


# ── Column Profile tab ───────────────────────────────────────────────────────

def _render_column_profile(df: pd.DataFrame, prof: dict) -> None:
    col_profs = prof["columns"]

    # ── Summary table ─────────────────────────────────────────────────────
    section_title("Column Summary")

    rows = []
    for col, cp in col_profs.items():
        null_pct = cp["null_pct"]
        cat      = cp["dtype_category"]
        bg, fg   = _DTYPE_STYLE.get(cat, _DTYPE_STYLE["other"])
        sample   = ", ".join(cp.get("sample_values", [])[:3])
        rows.append({
            "Column":     col,
            "Type":       cat,
            "Dtype":      cp["dtype"],
            "Nulls":      f'{cp["null_count"]:,} ({null_pct:.1f}%)',
            "Unique":     f'{cp["unique_count"]:,} ({cp["unique_pct"]:.1f}%)',
            "Sample":     sample[:80] + ("…" if len(sample) > 80 else ""),
            "Issues":     ", ".join(cp["issues"]) if cp["issues"] else "—",
        })

    profile_df = pd.DataFrame(rows)

    def _hl(row):
        issues_str = str(row.get("Issues", ""))
        if "all_null" in issues_str:
            return ["background:#fee2e2"] * len(row)
        if any(i in issues_str for i in ("constant", "numeric_as_string", "high_null_severe")):
            return ["background:#fef3c7"] * len(row)
        return [""] * len(row)

    st.dataframe(
        profile_df.style.apply(_hl, axis=1),
        use_container_width=True,
        height=460,
        hide_index=True,
    )

    # ── Column drill-down ──────────────────────────────────────────────────
    section_title("Column Drill-down")
    pick = st.selectbox("Inspect column", list(col_profs.keys()), key="prof_pick")
    cp   = col_profs[pick]
    cat  = cp["dtype_category"]

    c1, c2 = st.columns([1, 1])
    with c1:
        bg, fg = _DTYPE_STYLE.get(cat, _DTYPE_STYLE["other"])
        st.markdown(
            f"""<div style="padding:16px;background:#fafbfc;border-radius:10px;border:1px solid #e8edf2;">
              <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
                <span style="background:{bg};color:{fg};font-size:11px;font-weight:700;
                             padding:3px 9px;border-radius:99px;">{cat}</span>
                <span style="font-size:12px;color:#8a9aaa;">{cp["dtype"]}</span>
              </div>""",
            unsafe_allow_html=True,
        )
        stats_items = [
            ("Null values",  f'{cp["null_count"]:,} ({cp["null_pct"]:.1f}%)'),
            ("Unique values",f'{cp["unique_count"]:,} ({cp["unique_pct"]:.1f}%)'),
        ]
        if cat == "numeric":
            for k in ("min", "max", "mean", "median", "std", "q25", "q75", "iqr"):
                v = cp.get(k)
                if v is not None:
                    stats_items.append((k.capitalize(), f"{v:,.4g}"))
            stats_items += [
                ("Zero values",     f'{cp.get("zero_count", 0):,}'),
                ("Negative values", f'{cp.get("neg_count", 0):,}'),
            ]
        elif cat == "categorical":
            stats_items += [
                ("Avg length",  f'{cp.get("avg_str_length", 0):.1f} chars'),
                ("Min length",  str(cp.get("min_str_length", 0))),
                ("Max length",  str(cp.get("max_str_length", 0))),
                ("Has spaces",  str(cp.get("has_leading_trailing_spaces", False))),
            ]
        elif cat == "datetime":
            stats_items += [
                ("From", str(cp.get("min_date", "—"))),
                ("To",   str(cp.get("max_date", "—"))),
                ("Span (days)", str(cp.get("date_range_days", "—"))),
            ]

        for label, val in stats_items:
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;padding:5px 0;'
                f'border-bottom:1px solid #eef2f7;font-size:13px;">'
                f'<span style="color:#8a9aaa;">{label}</span>'
                f'<span style="color:#1a2332;font-weight:500;">{val}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        issue_html = _issue_badges(cp["issues"])
        if issue_html:
            st.markdown(f'<div style="margin-top:10px;">{issue_html}</div>',
                        unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with c2:
        col_data = df[pick]
        if cat == "numeric":
            fig = cf.histogram(df, pick, height=260)
            if fig:
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        elif cat == "categorical":
            vc = col_data.value_counts().head(15).reset_index()
            vc.columns = [pick, "count"]
            fig = cf.bar_ranked(vc, pick, "count", top_n=15, orientation="h", height=260)
            if fig:
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            samples = cp.get("sample_values", [])
            if samples:
                st.markdown("**Sample values**")
                for sv in samples[:8]:
                    st.markdown(
                        f'<div style="font-size:13px;padding:4px 8px;background:#f8fafc;'
                        f'border-radius:6px;margin:2px 0;font-family:monospace;">{sv}</div>',
                        unsafe_allow_html=True,
                    )

    # ── Null heatmap ───────────────────────────────────────────────────────
    section_title("Missing Values per Column")
    null_data = pd.DataFrame({
        "Column":    list(col_profs.keys()),
        "Missing %": [cp["null_pct"] for cp in col_profs.values()],
    }).sort_values("Missing %", ascending=False)

    if null_data["Missing %"].max() > 0:
        import plotly.express as px
        fig = px.bar(
            null_data.head(40), x="Column", y="Missing %",
            color="Missing %",
            color_continuous_scale=["#dbeafe", "#ef4444"],
            range_color=[0, 100],
        )
        fig.update_layout(
            plot_bgcolor="white", paper_bgcolor="white",
            font_family="Inter, sans-serif", font_color="#1a2332",
            margin=dict(t=20, b=50, l=10, r=10),
            xaxis=dict(tickangle=-35),
            coloraxis_showscale=False,
            height=260,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.success("✅ No missing values in any column.")


# ── Quality tab ──────────────────────────────────────────────────────────────

def _render_quality(prof: dict) -> None:
    quality = prof["quality"]
    score   = quality["score"]
    checks  = quality["checks"]

    c1, c2 = st.columns([1, 3])
    with c1:
        score_color = "#10b981" if score >= 80 else ("#f59e0b" if score >= 60 else "#ef4444")
        label = "Excellent" if score >= 80 else ("Fair" if score >= 60 else "Poor")
        st.markdown(
            f"""<div style="background:{score_color}18;border:2px solid {score_color}40;
                border-radius:12px;padding:20px;text-align:center;">
              <div style="font-size:48px;font-weight:800;color:{score_color};line-height:1;">{score}</div>
              <div style="font-size:13px;font-weight:600;color:{score_color};margin-top:4px;">{label}</div>
              <div style="font-size:11px;color:#8a9aaa;margin-top:2px;">Quality score / 100</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with c2:
        errors   = sum(1 for c in checks if c["severity"] == "error")
        warnings = sum(1 for c in checks if c["severity"] == "warning")
        infos    = sum(1 for c in checks if c["severity"] == "info")
        metric_row([
            {"label": "Errors",   "value": str(errors),
             "delta_type": "negative" if errors   else "neutral"},
            {"label": "Warnings", "value": str(warnings),
             "delta_type": "negative" if warnings else "neutral"},
            {"label": "Info",     "value": str(infos)},
        ])

    if not checks:
        st.success("✅ No quality issues detected — your dataset looks clean!")
        return

    section_title(f"{len(checks)} issue(s) found")

    for chk in checks:
        sev      = chk["severity"]
        bg, fg   = _ISSUE_SEVERITY.get(sev, ("#f1f5f9", "#475569"))
        icon_map = {"error": "🔴", "warning": "🟡", "info": "🔵"}
        icon_str = icon_map.get(sev, "•")

        tags = ""
        if chk["columns"]:
            tags = "".join(
                f'<span style="background:#f1f5f9;color:#475569;font-size:11px;'
                f'padding:2px 7px;border-radius:99px;margin:2px;">{c}</span>'
                for c in chk["columns"][:8]
            )
            if len(chk["columns"]) > 8:
                tags += f' <span style="color:#8a9aaa;font-size:11px;">+{len(chk["columns"])-8} more</span>'

        st.markdown(
            f"""<div style="background:{bg}22;border-left:4px solid {fg};
                border-radius:0 8px 8px 0;padding:14px 16px;margin:8px 0;">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                <span>{icon_str}</span>
                <span style="font-size:13.5px;font-weight:600;color:#1a2332;">{chk["name"]}</span>
                <span style="font-size:11px;font-weight:600;background:{bg};color:{fg};
                             padding:2px 7px;border-radius:99px;">{sev}</span>
              </div>
              <div style="font-size:13px;color:#4a5a6a;">{chk["description"]}</div>
              {"<div style='margin-top:8px;'>" + tags + "</div>" if tags else ""}
            </div>""",
            unsafe_allow_html=True,
        )


# ── Statistics tab ───────────────────────────────────────────────────────────

def _render_statistics(df: pd.DataFrame) -> None:
    num_df = df.select_dtypes("number")
    cat_df = df.select_dtypes("object")

    # ── Descriptive statistics ─────────────────────────────────────────────
    section_title("Descriptive Statistics")

    if not num_df.empty:
        st.markdown("**Numeric columns**")
        from app.analytics.statistics import describe
        desc = num_df.describe().T.round(4)
        extra = describe(df)
        for col in ("skew", "kurtosis"):
            if col in extra.columns:
                desc[col] = extra[col].round(3)
        st.dataframe(desc.fillna("—"), use_container_width=True)
    else:
        st.info("No numeric columns.")

    if not cat_df.empty:
        section_title("Categorical Columns")
        cat_desc = cat_df.describe().T
        st.dataframe(cat_desc.fillna("—"), use_container_width=True)

    # ── Value counts ───────────────────────────────────────────────────────
    all_obj = cat_df.columns.tolist()
    low_card = [c for c in all_obj if df[c].nunique() <= 200]
    if low_card:
        section_title("Value Counts")
        pick_vc = st.selectbox("Column", low_card, key="stats_vc")
        vc = df[pick_vc].value_counts().head(20).reset_index()
        vc.columns = [pick_vc, "Count"]
        vc["Pct"] = (vc["Count"] / len(df) * 100).round(2)

        c1, c2 = st.columns([2, 3])
        with c1:
            st.dataframe(vc, use_container_width=True, hide_index=True)
        with c2:
            import plotly.express as px
            fig = px.bar(vc.head(15), x=pick_vc, y="Count",
                         text_auto=True, color_discrete_sequence=["#2563eb"])
            fig.update_layout(
                plot_bgcolor="white", paper_bgcolor="white",
                font_family="Inter, sans-serif", font_color="#1a2332",
                margin=dict(t=20, b=40, l=10, r=10),
                xaxis_tickangle=-35, height=320,
            )
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── Correlation analysis ───────────────────────────────────────────────
    num_cols = num_df.columns.tolist()
    if len(num_cols) >= 2:
        section_title("Correlation Analysis")

        selected_corr = st.multiselect(
            "Columns for correlation",
            num_cols,
            default=num_cols[:min(10, len(num_cols))],
            key="corr_cols",
        )
        if len(selected_corr) >= 2:
            from app.analytics.statistics import correlation_matrix
            corr = correlation_matrix(df[selected_corr]).round(3)

            c1, c2 = st.columns([3, 2])
            with c1:
                fig_heat = cf.correlation_heatmap(df, selected_corr, height=380)
                if fig_heat:
                    st.plotly_chart(fig_heat, use_container_width=True,
                                    config={"displayModeBar": False})

            with c2:
                # Top correlated pairs
                import numpy as np
                pairs: list[dict] = []
                seen: set[frozenset] = set()
                for a in corr.columns:
                    for b in corr.columns:
                        pair = frozenset([a, b])
                        if a == b or pair in seen:
                            continue
                        seen.add(pair)
                        v = corr.loc[a, b]
                        if not pd.isna(v):
                            pairs.append({
                                "A": a, "B": b,
                                "r": round(float(v), 3),
                                "abs": abs(float(v)),
                            })

                if pairs:
                    top = sorted(pairs, key=lambda x: -x["abs"])[:8]
                    st.markdown("**Strongest pairs**")
                    for p in top:
                        bar_w = int(p["abs"] * 80)
                        color = "#2563eb" if p["r"] > 0 else "#ef4444"
                        st.markdown(
                            f'<div style="display:flex;align-items:center;gap:8px;'
                            f'padding:5px 0;border-bottom:1px solid #f0f4f8;font-size:12px;">'
                            f'<span style="width:100px;overflow:hidden;text-overflow:ellipsis;'
                            f'white-space:nowrap;color:#4a5a6a;" title="{p["A"]}">{p["A"]}</span>'
                            f'<span style="color:#8a9aaa;">↔</span>'
                            f'<span style="width:100px;overflow:hidden;text-overflow:ellipsis;'
                            f'white-space:nowrap;color:#4a5a6a;" title="{p["B"]}">{p["B"]}</span>'
                            f'<div style="flex:1;background:#f0f4f8;border-radius:3px;height:6px;">'
                            f'<div style="width:{bar_w}px;background:{color};height:100%;'
                            f'border-radius:3px;"></div></div>'
                            f'<span style="font-weight:600;color:{color};min-width:40px;">{p["r"]:+.2f}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

            # Scatter for top pair
            if pairs:
                top_pair = max(pairs, key=lambda x: x["abs"])
                st.markdown(
                    f'**Scatter: {top_pair["A"]} vs {top_pair["B"]}**  '
                    f'(r = {top_pair["r"]:+.3f})'
                )
                fig_sc = cf.scatter_trend(df, top_pair["A"], top_pair["B"], height=300)
                if fig_sc:
                    st.plotly_chart(fig_sc, use_container_width=True,
                                    config={"displayModeBar": False})
                    _chart_download_row(fig_sc, f"scatter_{top_pair['A']}_{top_pair['B']}.png")

        # Correlation heatmap download
        if len(selected_corr) >= 3:
            _chart_download_row(fig_heat, "correlation_heatmap.png")


# ── Chart download helper ─────────────────────────────────────────────────────

def _chart_download_row(fig, default_fname: str = "chart.png") -> None:
    """Render a compact PNG + interactive-HTML download strip below a chart."""
    if fig is None:
        return

    c1, c2, _ = st.columns([1, 1, 4])
    with c1:
        png = to_chart_png(fig)
        if png:
            st.download_button(
                "⬇ PNG",
                data=png,
                file_name=default_fname,
                mime="image/png",
                key=f"dl_png_{default_fname}",
                help="Download chart as PNG image",
            )
    with c2:
        html_bytes = fig.to_html(
            full_html=True,
            include_plotlyjs=True,
            config={"displayModeBar": True, "scrollZoom": True},
        ).encode("utf-8")
        st.download_button(
            "⬇ Interactive HTML",
            data=html_bytes,
            file_name=default_fname.replace(".png", ".html"),
            mime="text/html",
            key=f"dl_html_{default_fname}",
            help="Download as interactive HTML (open in browser)",
        )


# ── Clean tab ────────────────────────────────────────────────────────────────

def _render_clean(df: pd.DataFrame, orig_df: pd.DataFrame, prof: dict) -> None:
    """Cleaning pipeline — each action previews its effect before committing."""

    # ── Before/after quality banner ────────────────────────────────────────
    _render_quality_delta(orig_df, df)

    # ── Change history + reset ─────────────────────────────────────────────
    history: list[dict] = st.session_state.get("_clean_history", [])
    if history:
        with st.expander(f"✓ {len(history)} change(s) applied", expanded=False):
            for i, op in enumerate(history):
                st.markdown(
                    f'<div style="font-size:13px;padding:5px 0;border-bottom:1px solid #eef2f7;">'
                    f'<b>{i+1}.</b> {op["description"]}'
                    f'<span style="color:#64748b;font-size:12px;margin-left:8px;">'
                    f'{op["rows_before"]:,} → {op["rows_after"]:,} rows</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        if st.button("↺ Reset to original dataset", key="reset_to_orig", type="secondary"):
            st.session_state["df"] = orig_df.copy()
            st.session_state["_clean_history"] = []
            _invalidate_profile()
            st.rerun()

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    section_title("Cleaning Actions")

    with st.expander("1 · Drop duplicate rows", expanded=False):
        _clean_duplicates(df)

    with st.expander("2 · Handle missing values", expanded=False):
        _clean_missing(df, prof)

    with st.expander("3 · Fix column data types", expanded=False):
        _clean_types(df, prof)

    with st.expander("4 · Rename columns", expanded=False):
        _clean_rename(df)

    with st.expander("5 · Drop columns", expanded=False):
        _clean_drop_columns(df)

    with st.expander("6 · Trim whitespace in text columns", expanded=False):
        _clean_trim(df, prof)


def _render_quality_delta(orig_df: pd.DataFrame, df: pd.DataFrame) -> None:
    """Side-by-side before/after quality metrics card."""
    is_modified = (
        len(df) != len(orig_df) or
        list(df.columns) != list(orig_df.columns) or
        df.isna().sum().sum() != orig_df.isna().sum().sum()
    )

    orig_nulls = int(orig_df.isna().sum().sum())
    orig_dups  = int(orig_df.duplicated().sum())
    curr_nulls = int(df.isna().sum().sum())
    curr_dups  = int(df.duplicated().sum())

    orig_score_key = "_orig_quality_score"
    if st.session_state.get(orig_score_key) is None:
        with st.spinner("Computing original quality score…"):
            op = compute_profile(orig_df)
            st.session_state[orig_score_key] = op["quality"]["score"]
    orig_score = st.session_state[orig_score_key]

    curr_prof_key = f"_profile_{id(df)}"
    curr_prof     = st.session_state.get(curr_prof_key)
    curr_score    = curr_prof["quality"]["score"] if curr_prof else orig_score

    def _delta_html(orig_v, curr_v, lower_is_better=True):
        diff = curr_v - orig_v
        if diff == 0:
            return f'<span style="color:#8a9aaa;font-size:11px;">no change</span>'
        better = (diff < 0) == lower_is_better
        color  = "#10b981" if better else "#ef4444"
        sign   = "+" if diff > 0 else ""
        return f'<span style="color:{color};font-size:11px;font-weight:600;">{sign}{diff:,}</span>'

    score_delta  = curr_score - orig_score
    score_color  = "#10b981" if score_delta >= 0 else "#ef4444"
    score_sign   = "+" if score_delta > 0 else ""

    st.markdown(
        f"""<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:12px;
            background:#f8fafc;border-radius:12px;padding:16px;margin-bottom:16px;">
          <div style="text-align:center;">
            <div style="font-size:11px;color:#8a9aaa;text-transform:uppercase;letter-spacing:.05em;">Quality score</div>
            <div style="font-size:22px;font-weight:700;color:#1a2332;">{curr_score}</div>
            <div style="font-size:11px;">was {orig_score}
              {"&nbsp;<span style='color:" + score_color + ";font-weight:600;'>" + score_sign + str(score_delta) + "</span>" if score_delta != 0 else ""}
            </div>
          </div>
          <div style="text-align:center;">
            <div style="font-size:11px;color:#8a9aaa;text-transform:uppercase;letter-spacing:.05em;">Rows</div>
            <div style="font-size:22px;font-weight:700;color:#1a2332;">{df.shape[0]:,}</div>
            <div style="font-size:11px;">was {orig_df.shape[0]:,}&nbsp;{_delta_html(orig_df.shape[0], df.shape[0], lower_is_better=False)}</div>
          </div>
          <div style="text-align:center;">
            <div style="font-size:11px;color:#8a9aaa;text-transform:uppercase;letter-spacing:.05em;">Missing cells</div>
            <div style="font-size:22px;font-weight:700;color:#1a2332;">{curr_nulls:,}</div>
            <div style="font-size:11px;">was {orig_nulls:,}&nbsp;{_delta_html(orig_nulls, curr_nulls)}</div>
          </div>
          <div style="text-align:center;">
            <div style="font-size:11px;color:#8a9aaa;text-transform:uppercase;letter-spacing:.05em;">Duplicate rows</div>
            <div style="font-size:22px;font-weight:700;color:#1a2332;">{curr_dups:,}</div>
            <div style="font-size:11px;">was {orig_dups:,}&nbsp;{_delta_html(orig_dups, curr_dups)}</div>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )


def _clean_duplicates(df: pd.DataFrame) -> None:
    n_dup = int(df.duplicated().sum())

    if n_dup == 0:
        st.success("✅ No duplicate rows found.")
        return

    st.markdown(
        f'<div style="padding:10px 14px;background:#fef3c722;border:1px solid #fbbf24;'
        f'border-radius:8px;font-size:13px;margin-bottom:12px;">'
        f'<b>{n_dup:,}</b> duplicate row(s) — {n_dup/len(df)*100:.1f}% of dataset</div>',
        unsafe_allow_html=True,
    )

    # Show sample duplicates
    dup_sample = df[df.duplicated(keep=False)].head(8)
    st.markdown("**Sample duplicate rows (showing first 8):**")
    st.dataframe(dup_sample, use_container_width=True, height=200, hide_index=True)

    keep = st.selectbox(
        "Which occurrence to keep",
        ["first", "last", "none (drop all occurrences)"],
        key="dup_keep",
    )
    keep_val: str | bool = keep.split(" ")[0] if keep.startswith(("first", "last")) else False

    preview_df = df.drop_duplicates(keep=keep_val)
    n_removed  = len(df) - len(preview_df)

    st.info(
        f"**Preview:** will remove **{n_removed:,}** rows → "
        f"**{len(preview_df):,}** rows remaining"
    )

    if st.button("Apply: Drop duplicates", key="apply_dup", type="primary"):
        _apply_op(preview_df, f"Dropped {n_removed:,} duplicate rows (keep={keep_val})")


def _clean_missing(df: pd.DataFrame, prof: dict) -> None:
    null_cols = [
        (col, prof["columns"][col]["null_count"],
               prof["columns"][col]["null_pct"],
               prof["columns"][col]["dtype_category"])
        for col in df.columns
        if prof["columns"][col]["null_count"] > 0
    ]

    if not null_cols:
        st.success("✅ No missing values found.")
        return

    st.markdown(f"**{len(null_cols)} column(s) have missing values.**")

    bulk_mode = st.radio(
        "Strategy",
        ["Configure per column", "Drop all rows with any missing value"],
        horizontal=True,
        key="missing_bulk",
    )

    if bulk_mode == "Drop all rows with any missing value":
        preview_df = df.dropna()
        n_dropped  = len(df) - len(preview_df)
        st.info(
            f"**Preview:** will drop **{n_dropped:,}** rows with any null → "
            f"**{len(preview_df):,}** rows remaining"
        )
        if n_dropped > 0 and st.button(
            "Apply: Drop rows with missing values", key="apply_dropna", type="primary"
        ):
            _apply_op(preview_df, f"Dropped {n_dropped:,} rows with missing values")
        elif n_dropped == 0:
            st.success("No rows would be dropped.")
        return

    # ── Per-column ──────────────────────────────────────────────────────────
    choices: dict[str, str] = {}

    for col, null_count, null_pct, cat in null_cols:
        if cat == "numeric":
            options = ["skip", "fill with mean", "fill with median",
                       "fill with mode", "fill with 0", "fill with custom value", "drop rows"]
        else:
            options = ["skip", "fill with mode", "fill with 'Unknown'",
                       "fill with custom value", "drop rows"]

        c1, c2 = st.columns([2, 3])
        with c1:
            st.markdown(
                f'<div style="font-size:13px;padding:6px 0;">'
                f'<b>{col}</b> — '
                f'<span style="color:#ef4444;">{null_count:,} nulls ({null_pct:.1f}%)</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with c2:
            choices[col] = st.selectbox(
                f"Action for {col}",
                options,
                key=f"miss_{col}",
                label_visibility="collapsed",
            )

    # Build preview
    preview_df = df.copy()
    changes: list[str] = []
    for col, null_count, null_pct, cat in null_cols:
        choice = choices.get(col, "skip")
        if choice == "skip":
            continue
        n_null = preview_df[col].isna().sum()
        if choice == "fill with mean" and cat == "numeric":
            v = preview_df[col].mean()
            preview_df[col] = preview_df[col].fillna(v)
            changes.append(f"{col}: filled {n_null:,} nulls with mean ({v:.4g})")
        elif choice == "fill with median" and cat == "numeric":
            v = preview_df[col].median()
            preview_df[col] = preview_df[col].fillna(v)
            changes.append(f"{col}: filled {n_null:,} nulls with median ({v:.4g})")
        elif choice in ("fill with mode", ):
            modes = preview_df[col].mode()
            if not modes.empty:
                preview_df[col] = preview_df[col].fillna(modes[0])
                changes.append(f"{col}: filled {n_null:,} nulls with mode ({modes[0]})")
        elif choice == "fill with 0":
            preview_df[col] = preview_df[col].fillna(0)
            changes.append(f"{col}: filled {n_null:,} nulls with 0")
        elif choice == "fill with 'Unknown'":
            preview_df[col] = preview_df[col].fillna("Unknown")
            changes.append(f"{col}: filled {n_null:,} nulls with 'Unknown'")
        elif choice == "fill with custom value":
            cv = st.text_input(
                f"Custom value for {col}",
                key=f"miss_cv_{col}",
                placeholder="Enter fill value…",
            )
            if cv:
                preview_df[col] = preview_df[col].fillna(cv)
                changes.append(f"{col}: filled {n_null:,} nulls with '{cv}'")
        elif choice == "drop rows":
            preview_df = preview_df.dropna(subset=[col])
            changes.append(f"{col}: dropped {n_null:,} rows with null")

    if changes:
        st.markdown("---")
        st.markdown("**Preview of changes:**")
        for c in changes:
            st.markdown(f"- {c}")
        n_null_after = int(preview_df.isna().sum().sum())
        st.info(
            f"Missing cells: **{int(df.isna().sum().sum()):,}** → **{n_null_after:,}** "
            f"&nbsp;|&nbsp; Rows: **{len(df):,}** → **{len(preview_df):,}**"
        )
        if st.button("Apply missing-value fixes", key="apply_missing", type="primary"):
            _apply_op(preview_df,
                      f"Fixed missing values in {len(changes)} column(s)")
    else:
        st.info("Select an action for at least one column to see a preview.")


def _clean_types(df: pd.DataFrame, prof: dict) -> None:
    type_issues = {
        col: cp for col, cp in prof["columns"].items()
        if any(i in cp["issues"] for i in ("numeric_as_string", "datetime_as_string"))
    }

    if not type_issues:
        st.success("✅ No type-mismatch issues found.")
        return

    st.markdown(f"**{len(type_issues)} column(s) with type issues:**")

    fixes: dict[str, str] = {}
    for col, cp in type_issues.items():
        has_num  = "numeric_as_string"  in cp["issues"]
        has_date = "datetime_as_string" in cp["issues"]
        issue_str = "numeric stored as text" if has_num else "date stored as text"
        opts = ["skip"]
        if has_num:
            opts.append("convert to numeric (float)")
        if has_date:
            opts.append("convert to datetime")

        c1, c2 = st.columns([2, 3])
        with c1:
            st.markdown(
                f'<div style="font-size:13px;padding:6px 0;"><b>{col}</b>'
                f'<br><span style="color:#f59e0b;font-size:11px;">{issue_str}</span></div>',
                unsafe_allow_html=True,
            )
        with c2:
            fixes[col] = st.selectbox(
                f"Action for {col}", opts,
                key=f"type_{col}", label_visibility="collapsed",
            )

    # Build preview
    preview_df = df.copy()
    changes: list[str] = []
    for col, action in fixes.items():
        if action == "skip":
            continue
        if "numeric" in action:
            converted = pd.to_numeric(preview_df[col], errors="coerce")
            n_coerced = int(converted.isna().sum() - preview_df[col].isna().sum())
            preview_df[col] = converted
            changes.append(
                f"{col}: → float64"
                + (f" ({n_coerced} values became NaN)" if n_coerced else "")
            )
        elif "datetime" in action:
            try:
                converted = pd.to_datetime(preview_df[col], errors="coerce", format="mixed")
            except Exception:
                converted = pd.to_datetime(preview_df[col], errors="coerce")
            n_coerced = int(converted.isna().sum() - preview_df[col].isna().sum())
            preview_df[col] = converted
            changes.append(
                f"{col}: → datetime64"
                + (f" ({n_coerced} values became NaT)" if n_coerced else "")
            )

    if changes:
        st.markdown("---")
        st.markdown("**Preview of changes:**")
        for c in changes:
            st.markdown(f"- {c}")
        if st.button("Apply type conversions", key="apply_types", type="primary"):
            _apply_op(preview_df,
                      f"Converted types: {', '.join(col for col in fixes if fixes[col] != 'skip')}")
    else:
        st.info("Select an action for at least one column to see a preview.")


def _clean_rename(df: pd.DataFrame) -> None:
    st.markdown(
        '<div style="font-size:13px;color:#64748b;margin-bottom:10px;">'
        "Edit column names below (leave blank or unchanged to keep original).</div>",
        unsafe_allow_html=True,
    )

    rename_map: dict[str, str] = {}
    cols_per_row = 3
    all_cols     = df.columns.tolist()

    for i in range(0, len(all_cols), cols_per_row):
        batch = all_cols[i : i + cols_per_row]
        ui_cols = st.columns(cols_per_row)
        for col, ui_col in zip(batch, ui_cols):
            with ui_col:
                new_name = st.text_input(
                    col, value=col, key=f"rename_{col}",
                    label_visibility="visible",
                )
                if new_name and new_name != col:
                    rename_map[col] = new_name

    if rename_map:
        st.markdown("---")
        st.markdown("**Preview of renames:**")
        for old, new in rename_map.items():
            st.markdown(
                f'<span style="font-family:monospace;font-size:13px;">'
                f'{old} → <b>{new}</b></span>',
                unsafe_allow_html=True,
            )
        preview_df = df.rename(columns=rename_map)
        st.info(f"Will rename {len(rename_map)} column(s).")
        if st.button("Apply renames", key="apply_rename", type="primary"):
            _apply_op(preview_df, f"Renamed {len(rename_map)} column(s)")
    else:
        st.info("Edit one or more column names above to preview the change.")


def _clean_drop_columns(df: pd.DataFrame) -> None:
    to_drop = st.multiselect(
        "Select columns to drop",
        df.columns.tolist(),
        key="drop_cols_sel",
    )

    if not to_drop:
        st.info("Select columns above to preview dropping them.")
        return

    preview_df    = df.drop(columns=to_drop)
    remaining     = preview_df.columns.tolist()
    preview_chips = "".join(
        f'<span style="background:#dbeafe;color:#1d4ed8;font-size:11px;font-weight:600;'
        f'padding:3px 8px;border-radius:99px;margin:2px;">{c}</span>'
        for c in remaining[:20]
    )
    st.markdown(
        f'<div style="margin-top:8px;"><b>Remaining columns ({len(remaining)}):</b><br>'
        f'<div style="margin-top:6px;line-height:2;">{preview_chips}</div></div>',
        unsafe_allow_html=True,
    )
    st.info(f"Will drop {len(to_drop)} column(s) → {len(remaining)} remaining.")
    if st.button("Apply: Drop columns", key="apply_drop_cols", type="primary"):
        _apply_op(preview_df, f"Dropped {len(to_drop)} column(s): {', '.join(to_drop)}")


def _clean_trim(df: pd.DataFrame, prof: dict) -> None:
    space_cols = [
        col for col, cp in prof["columns"].items()
        if "leading_trailing_spaces" in cp["issues"]
    ]

    text_cols = [
        col for col, cp in prof["columns"].items()
        if cp["dtype_category"] == "categorical"
    ]

    if not space_cols:
        st.success("✅ No whitespace issues detected in text columns.")
        if not text_cols:
            return
        st.markdown(
            '<div style="font-size:13px;color:#64748b;">You can still trim all text columns:</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="padding:10px 14px;background:#fef3c722;border:1px solid #fbbf24;'
            f'border-radius:8px;font-size:13px;margin-bottom:12px;">'
            f'<b>{len(space_cols)}</b> column(s) have leading/trailing spaces: '
            f'{", ".join(space_cols[:6])}</div>',
            unsafe_allow_html=True,
        )

    trim_cols = st.multiselect(
        "Columns to trim",
        options=text_cols,
        default=space_cols[:min(len(space_cols), 10)],
        key="trim_cols_sel",
    )

    if not trim_cols:
        st.info("Select text columns to trim.")
        return

    # Show before/after sample
    sample_col = trim_cols[0]
    before = df[sample_col].dropna().astype(str).head(4).tolist()
    after  = [v.strip() for v in before]
    changed = sum(1 for b, a in zip(before, after) if b != a)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Before (sample)**")
        for v in before:
            st.markdown(
                f'<code style="font-size:12px;">&quot;{v}&quot;</code>', unsafe_allow_html=True
            )
    with c2:
        st.markdown("**After (sample)**")
        for v in after:
            st.markdown(
                f'<code style="font-size:12px;">&quot;{v}&quot;</code>', unsafe_allow_html=True
            )

    preview_df = df.copy()
    for col in trim_cols:
        mask = preview_df[col].notna()
        preview_df.loc[mask, col] = preview_df.loc[mask, col].astype(str).str.strip()

    st.info(f"Will trim whitespace in {len(trim_cols)} column(s).")
    if st.button("Apply: Trim whitespace", key="apply_trim", type="primary"):
        _apply_op(preview_df, f"Trimmed whitespace in {len(trim_cols)} column(s)")


# ── Export tab ───────────────────────────────────────────────────────────────

def _render_export(df: pd.DataFrame, lr) -> None:
    """Three export sections: data downloads, analysis reports, chart images."""
    fname    = lr.filename.rsplit(".", 1)[0]
    orig_df  = st.session_state.get("_original_df", df)
    history  = st.session_state.get("_clean_history", [])
    is_clean = len(history) > 0

    # ── 1. Data downloads ──────────────────────────────────────────────────
    section_title("Data Downloads")

    # Filtered view (matches what Preview tab is showing right now)
    filtered_df = get_filtered_view(df)
    is_filtered = (len(filtered_df) != len(df) or
                   list(filtered_df.columns) != list(df.columns))

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        st.markdown(
            _export_card_header(
                "Current dataset",
                f"{df.shape[0]:,} rows × {df.shape[1]} cols",
                is_cleaned=is_clean,
            ),
            unsafe_allow_html=True,
        )
        st.download_button(
            "⬇ CSV",
            data=to_csv_bytes(df),
            file_name=f"{fname}_cleaned.csv" if is_clean else f"{fname}.csv",
            mime="text/csv",
            use_container_width=True,
            key="exp_curr_csv",
        )
        st.download_button(
            "⬇ Excel (.xlsx)",
            data=to_excel_bytes(df),
            file_name=f"{fname}_cleaned.xlsx" if is_clean else f"{fname}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="exp_curr_xlsx",
        )

    with col_b:
        filter_label = (
            f"{len(filtered_df):,} rows × {len(filtered_df.columns)} cols (filtered)"
            if is_filtered else "Matches current dataset"
        )
        st.markdown(
            _export_card_header("Filtered view", filter_label),
            unsafe_allow_html=True,
        )
        st.download_button(
            "⬇ CSV",
            data=to_csv_bytes(filtered_df),
            file_name=f"{fname}_filtered.csv",
            mime="text/csv",
            use_container_width=True,
            key="exp_filt_csv",
            disabled=not is_filtered,
        )
        st.download_button(
            "⬇ Excel (.xlsx)",
            data=to_excel_bytes(filtered_df),
            file_name=f"{fname}_filtered.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="exp_filt_xlsx",
            disabled=not is_filtered,
        )
        if not is_filtered:
            st.caption("Apply a search/column filter in the Preview tab first.")

    with col_c:
        orig_label = (
            f"{len(orig_df):,} rows × {len(orig_df.columns)} cols"
            if is_clean else "No cleaning applied yet"
        )
        st.markdown(
            _export_card_header("Original dataset", orig_label),
            unsafe_allow_html=True,
        )
        st.download_button(
            "⬇ CSV",
            data=to_csv_bytes(orig_df),
            file_name=f"{fname}_original.csv",
            mime="text/csv",
            use_container_width=True,
            key="exp_orig_csv",
            disabled=not is_clean,
        )
        st.download_button(
            "⬇ Excel (.xlsx)",
            data=to_excel_bytes(orig_df),
            file_name=f"{fname}_original.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="exp_orig_xlsx",
            disabled=not is_clean,
        )
        if not is_clean:
            st.caption("Available after applying cleaning operations.")

    # ── 2. Analysis reports ────────────────────────────────────────────────
    section_title("Analysis Reports")

    prof_key = f"_profile_{id(df)}"
    prof     = st.session_state.get(prof_key)

    if prof is None:
        st.info("Navigate to any other tab first to compute the profile, then return here.")
        return

    rep_col1, rep_col2 = st.columns(2)

    with rep_col1:
        st.markdown(
            _export_card_header(
                "HTML Report",
                "Self-contained · charts + tables · printable to PDF",
            ),
            unsafe_allow_html=True,
        )
        st.caption(
            "Includes dataset summary, KPIs, quality issues, "
            "descriptive statistics, correlation analysis, key insights, "
            "column profiles, and a data sample. "
            "Open in any browser; use File → Print → Save as PDF."
        )
        with st.spinner("Building HTML report…"):
            try:
                html_bytes = build_html_report(df, orig_df, prof, lr, history)
                st.download_button(
                    "⬇ Download HTML Report",
                    data=html_bytes,
                    file_name=f"{fname}_analysis_report.html",
                    mime="text/html",
                    use_container_width=True,
                    key="exp_html_report",
                )
            except Exception as e:
                st.error(f"HTML report error: {e}")

    with rep_col2:
        st.markdown(
            _export_card_header(
                "Excel Report",
                "Multi-sheet · Summary · Quality · Statistics · Data · Charts",
            ),
            unsafe_allow_html=True,
        )
        st.caption(
            "Sheets: Summary (KPIs + insights), Data Quality, "
            "Column Profiles, Statistics + Correlation, Data sample "
            "(up to 10,000 rows)"
            + (", Original Data, Cleaning History" if is_clean else "")
            + ", Charts (PNG images)."
        )
        with st.spinner("Building Excel report…"):
            try:
                xl_bytes = build_excel_report(df, orig_df, prof, lr, history)
                st.download_button(
                    "⬇ Download Excel Report (.xlsx)",
                    data=xl_bytes,
                    file_name=f"{fname}_analysis_report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="exp_xlsx_report",
                )
            except Exception as e:
                st.error(f"Excel report error: {e}")

    # ── 3. Chart image downloads ───────────────────────────────────────────
    section_title("Chart Image Downloads")
    st.caption("PNG images generated at print resolution (1.5×). Download and embed in slides or docs.")

    num_cols = df.select_dtypes("number").columns.tolist()
    charts: list[tuple[str, object, str]] = []  # (label, fig, filename)

    # Correlation heatmap
    if len(num_cols) >= 3:
        fig_heat = cf.correlation_heatmap(df, num_cols[:12], height=420)
        if fig_heat:
            charts.append(("Correlation Heatmap", fig_heat, f"{fname}_correlation.png"))

    # Null distribution
    import plotly.express as _px
    null_data = {c: prof.get("columns", {}).get(c, {}).get("null_pct", 0)
                 for c in df.columns}
    null_df = (
        pd.DataFrame({"Column": list(null_data.keys()), "Missing %": list(null_data.values())})
        .query("`Missing %` > 0")
        .sort_values("Missing %", ascending=False)
    )
    if len(null_df) > 0:
        fig_null = _px.bar(
            null_df.head(30), x="Column", y="Missing %",
            color="Missing %",
            color_continuous_scale=["#dbeafe", "#ef4444"],
            range_color=[0, 100],
        )
        fig_null.update_layout(
            plot_bgcolor="white", paper_bgcolor="white",
            font_family="Inter, sans-serif", font_color="#1a2332",
            margin=dict(t=20, b=50, l=10, r=10),
            xaxis=dict(tickangle=-35),
            coloraxis_showscale=False, height=320,
        )
        charts.append(("Missing Values", fig_null, f"{fname}_missing_values.png"))

    # Column histograms
    for nc in num_cols[:4]:
        fig_h = cf.histogram(df, nc, height=280)
        if fig_h:
            charts.append((f"Distribution: {nc}", fig_h, f"{fname}_dist_{nc}.png"))

    # Categorical bar charts
    cat_cols = [c for c in df.select_dtypes("object").columns if 2 <= df[c].nunique() <= 20]
    for cc in cat_cols[:2]:
        vc = df[cc].value_counts().head(12).reset_index()
        vc.columns = [cc, "count"]
        fig_b = cf.bar_ranked(vc, cc, "count", top_n=12, height=280)
        if fig_b:
            charts.append((f"Top {cc}", fig_b, f"{fname}_top_{cc}.png"))

    if not charts:
        st.info("No charts available. Load a dataset with numeric columns to enable chart downloads.")
    else:
        cols_per_row = 3
        for i in range(0, len(charts), cols_per_row):
            batch = charts[i : i + cols_per_row]
            ch_cols = st.columns(cols_per_row)
            for (label, fig, fname_chart), ch_col in zip(batch, ch_cols):
                with ch_col:
                    st.markdown(f"**{label}**")
                    png = to_chart_png(fig)
                    if png:
                        st.image(png, use_container_width=True)
                        st.download_button(
                            f"⬇ PNG",
                            data=png,
                            file_name=fname_chart,
                            mime="image/png",
                            use_container_width=True,
                            key=f"exp_chart_{fname_chart}",
                        )
                    else:
                        st.caption("PNG export unavailable.")

    # ── File info strip ────────────────────────────────────────────────────
    section_title("File Info")
    info_cols = st.columns(4)
    meta_items = [
        ("Filename",  lr.filename),
        ("File type", lr.file_type.upper()),
        ("Encoding",  lr.encoding),
        ("Memory",    f"{round(df.memory_usage(deep=True).sum()/1024, 1)} KB"),
        ("Rows (current)",  f"{df.shape[0]:,}"),
        ("Rows (original)", f"{len(orig_df):,}"),
        ("Columns",         str(df.shape[1])),
        ("Active sheet",    lr.active_sheet or "—"),
    ]
    for idx, (label, val) in enumerate(meta_items):
        with info_cols[idx % 4]:
            st.markdown(
                f'<div style="padding:8px 0;border-bottom:1px solid #eef2f7;font-size:13px;">'
                f'<div style="font-size:10px;color:#8a9aaa;text-transform:uppercase;'
                f'letter-spacing:.06em;margin-bottom:2px;">{label}</div>'
                f'<div style="font-weight:600;color:#1a2332;">{val}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def _export_card_header(title: str, subtitle: str, is_cleaned: bool = False) -> str:
    badge = (
        '<span style="background:#d1fae5;color:#065f46;font-size:10px;font-weight:700;'
        'padding:2px 6px;border-radius:99px;margin-left:6px;">cleaned</span>'
        if is_cleaned else ""
    )
    return (
        f'<div style="margin-bottom:8px;">'
        f'<div style="font-size:13px;font-weight:700;color:#1a2332;">{title}{badge}</div>'
        f'<div style="font-size:11px;color:#64748b;margin-top:2px;">{subtitle}</div>'
        f'</div>'
    )


# ── Session helpers ──────────────────────────────────────────────────────────

def _apply_op(new_df: pd.DataFrame, description: str) -> None:
    """Commit a cleaning operation: update df, record in history, rerun."""
    old_df = st.session_state.get("df", new_df)
    history = st.session_state.setdefault("_clean_history", [])
    history.append({
        "description": description,
        "rows_before": len(old_df),
        "rows_after":  len(new_df),
    })
    st.session_state["df"] = new_df
    _invalidate_profile()
    st.rerun()


def _invalidate_profile() -> None:
    for k in list(st.session_state.keys()):
        if k.startswith("_profile_"):
            del st.session_state[k]


# ── Small render helpers ─────────────────────────────────────────────────────

def _null_bar(pct: float) -> str:
    filled = max(0.0, min(100.0, pct))
    color  = "#ef4444" if filled > 50 else ("#f59e0b" if filled > 20 else "#10b981")
    return (
        f'<svg width="60" height="6" style="border-radius:3px;overflow:hidden;">'
        f'<rect width="60" height="6" fill="#f0f4f8"/>'
        f'<rect width="{filled * 0.6:.1f}" height="6" fill="{color}"/>'
        f'</svg>'
    )


def _issue_badges(issues: list[str]) -> str:
    labels = {
        "all_null":                ("All null",         "error"),
        "constant":                ("Constant",         "warning"),
        "high_null_severe":        ("≥50% null",        "warning"),
        "high_null":               ("20–49% null",      "info"),
        "numeric_as_string":       ("Num→text",         "warning"),
        "datetime_as_string":      ("Date→text",        "info"),
        "high_cardinality":        ("High cardinality", "info"),
        "leading_trailing_spaces": ("Whitespace",       "info"),
    }
    html = ""
    for issue in issues:
        if issue in labels:
            text, sev = labels[issue]
            bg, fg = _ISSUE_SEVERITY.get(sev, ("#f1f5f9", "#475569"))
            html += (
                f'<span style="background:{bg};color:{fg};font-size:10px;font-weight:600;'
                f'padding:2px 6px;border-radius:99px;margin-right:3px;">{text}</span>'
            )
    return html
