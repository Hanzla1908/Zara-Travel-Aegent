"""Data Explorer page — Preview, Column Profile, Quality, Statistics, Export."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from app.components.cards import (
    page_header, metric_row, section_title, empty_state, content_card,
)
from app.analytics.profiler import profile as compute_profile
from app.services.export_service import to_csv_bytes, to_excel_bytes


# ── Colour palette for dtype badges ─────────────────────────────────────────
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
    page_header("Data Explorer", "Preview, profile, and audit your dataset.")

    lr = st.session_state.get("load_result")
    df: pd.DataFrame | None = st.session_state.get("df")

    if df is None or lr is None:
        empty_state("🔍", "No dataset loaded",
                    "Upload a CSV, Excel, Parquet, or JSON file from the sidebar to begin.")
        return

    # ── Sheet selector (Excel only) ──────────────────────────────────
    _maybe_render_sheet_selector(lr)
    # Re-read in case a sheet change triggered a rerun
    lr = st.session_state["load_result"]
    df = st.session_state["df"]

    # ── Load warnings ────────────────────────────────────────────────
    for w in lr.warnings:
        st.warning(w, icon="⚠️")

    # ── KPI strip ────────────────────────────────────────────────────
    dup = int(df.duplicated().sum())
    null_cells = int(df.isna().sum().sum())
    total_cells = df.shape[0] * df.shape[1]
    metric_row([
        {"label": "Rows",          "value": f"{lr.rows:,}",  "icon": "📋"},
        {"label": "Columns",       "value": str(lr.columns), "icon": "📐"},
        {"label": "Missing Cells", "value": f"{null_cells:,}",
         "delta": f"{null_cells/total_cells*100:.1f}%",
         "delta_type": "negative" if null_cells > 0 else "neutral", "icon": "⚠️"},
        {"label": "Duplicate Rows","value": f"{dup:,}",
         "delta_type": "negative" if dup > 0 else "neutral", "icon": "♻️"},
        {"label": "File type",     "value": lr.file_type.upper(), "icon": "📁"},
        {"label": "Memory",        "value": f"{round(df.memory_usage(deep=True).sum()/1024,0):.0f} KB",
         "icon": "💾"},
    ])

    # ── Tabs ─────────────────────────────────────────────────────────
    tab_preview, tab_profile, tab_quality, tab_stats, tab_export = st.tabs([
        "📋 Preview",
        "🔬 Column Profile",
        "⚠️ Data Quality",
        "📊 Statistics",
        "⬇️ Export",
    ])

    # Compute profile once and cache in session state
    profile_key = f"_profile_{id(df)}"
    if st.session_state.get(profile_key) is None:
        with st.spinner("Profiling dataset…"):
            st.session_state[profile_key] = compute_profile(df)
    prof = st.session_state[profile_key]

    with tab_preview:
        _render_preview(df)

    with tab_profile:
        _render_column_profile(prof)

    with tab_quality:
        _render_quality(prof)

    with tab_stats:
        _render_statistics(df)

    with tab_export:
        _render_export(df, lr)


# ── Sheet selector ───────────────────────────────────────────────────────────

def _maybe_render_sheet_selector(lr) -> None:
    from app.services.data_loader import reload_sheet

    if not lr.sheet_names or len(lr.sheet_names) <= 1:
        return

    st.markdown(
        '<div style="margin-bottom:10px;display:flex;align-items:center;gap:12px;">',
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns([3, 5])
    with col1:
        new_sheet = st.selectbox(
            "Excel sheet",
            options=lr.sheet_names,
            index=lr.sheet_names.index(lr.active_sheet),
            key="sheet_sel",
        )
    st.markdown('</div>', unsafe_allow_html=True)

    if new_sheet != lr.active_sheet:
        raw = st.session_state.get("_raw_bytes", b"")
        if raw:
            with st.spinner(f"Loading sheet '{new_sheet}'…"):
                new_lr = reload_sheet(raw, lr.filename, new_sheet)
            st.session_state["load_result"] = new_lr
            st.session_state["df"] = new_lr.df
            # Invalidate cached profile
            for k in list(st.session_state.keys()):
                if k.startswith("_profile_"):
                    del st.session_state[k]
            st.rerun()


# ── Preview tab ──────────────────────────────────────────────────────────────

def _render_preview(df: pd.DataFrame) -> None:
    section_title("Filter & Display")

    col1, col2, col3 = st.columns([3, 3, 1])
    with col1:
        search = st.text_input("Search rows (any column)",
                               placeholder="Type to filter…", key="prev_search")
    with col2:
        all_cols = df.columns.tolist()
        default_cols = all_cols[:min(10, len(all_cols))]
        col_sel = st.multiselect("Visible columns", all_cols, default=default_cols, key="prev_cols")
    with col3:
        row_limit = st.selectbox("Rows to show", [100, 500, 1_000, 5_000, "All"], key="prev_limit")

    view = df[col_sel] if col_sel else df
    if search:
        mask = view.apply(
            lambda c: c.astype(str).str.contains(search, case=False, na=False)
        ).any(axis=1)
        view = view[mask]

    n = len(view) if row_limit == "All" else int(row_limit)
    shown = min(n, len(view))

    st.markdown(
        f'<div style="font-size:12px;color:#8a9aaa;margin:8px 0 4px;">'
        f'Showing <b>{shown:,}</b> of <b>{len(view):,}</b> rows'
        f'{"  ·  filtered from " + str(len(df)) + " total" if search else ""}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Column-type chips above the table
    _render_column_chips(view.columns, df)

    st.dataframe(
        view.head(n),
        use_container_width=True,
        height=450,
        column_config={
            c: st.column_config.Column(c) for c in view.columns
        },
    )


def _render_column_chips(columns, df: pd.DataFrame) -> None:
    from app.analytics.profiler import _dtype_category
    chips = ""
    for c in columns:
        cat = _dtype_category(df[c])
        bg, fg = _DTYPE_STYLE.get(cat, _DTYPE_STYLE["other"])
        chips += (
            f'<span style="display:inline-flex;align-items:center;gap:4px;'
            f'background:{bg};color:{fg};font-size:11px;font-weight:600;'
            f'padding:3px 7px;border-radius:99px;margin:2px 3px 2px 0;'
            f'white-space:nowrap;">'
            f'{c}'
            f'</span>'
        )
    if chips:
        st.markdown(
            f'<div style="margin-bottom:8px;line-height:2;">{chips}</div>',
            unsafe_allow_html=True,
        )


# ── Column Profile tab ───────────────────────────────────────────────────────

def _render_column_profile(prof: dict) -> None:
    section_title("Per-column summary")
    col_profs = prof["columns"]

    rows = []
    for col, cp in col_profs.items():
        null_pct = cp["null_pct"]
        bar = _null_bar(null_pct)
        cat = cp["dtype_category"]
        bg, fg = _DTYPE_STYLE.get(cat, _DTYPE_STYLE["other"])
        type_badge = (
            f'<span style="background:{bg};color:{fg};font-size:11px;font-weight:600;'
            f'padding:2px 7px;border-radius:99px;">{cat}</span>'
        )
        issue_badges = _issue_badges(cp["issues"])
        sample = ", ".join(cp.get("sample_values", [])[:3])

        rows.append({
            "Column":    col,
            "Type":      cat,
            "Dtype":     cp["dtype"],
            "Nulls":     f"{cp['null_count']:,} ({null_pct:.1f}%)",
            "Unique":    f"{cp['unique_count']:,} ({cp['unique_pct']:.1f}%)",
            "Sample values": sample[:80] + ("…" if len(sample) > 80 else ""),
            "Issues":    ", ".join(cp["issues"]) if cp["issues"] else "—",
        })

    profile_df = pd.DataFrame(rows)

    # Highlight rows with issues
    def _highlight(row):
        if "all_null" in str(row.get("Issues", "")):
            return ["background:#fee2e2"] * len(row)
        if any(i in str(row.get("Issues", "")) for i in ("constant", "numeric_as_string", "high_null_severe")):
            return ["background:#fef3c7"] * len(row)
        return [""] * len(row)

    st.dataframe(
        profile_df.style.apply(_highlight, axis=1),
        use_container_width=True,
        height=500,
        hide_index=True,
    )

    # Null heatmap row
    section_title("Null % per column")
    null_data = pd.DataFrame({
        "Column": list(col_profs.keys()),
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
            margin=dict(t=20, b=40, l=10, r=10),
            xaxis=dict(tickangle=-35),
            coloraxis_showscale=False,
            height=260,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.success("✅ No missing values found in any column.")


# ── Quality tab ──────────────────────────────────────────────────────────────

def _render_quality(prof: dict) -> None:
    quality = prof["quality"]
    score   = quality["score"]
    checks  = quality["checks"]

    # Score dial
    col1, col2 = st.columns([1, 3])
    with col1:
        score_color = "#10b981" if score >= 80 else ("#f59e0b" if score >= 60 else "#ef4444")
        label = "Excellent" if score >= 80 else ("Fair" if score >= 60 else "Poor")
        st.markdown(f"""
        <div style="background:{score_color}15;border:2px solid {score_color}40;border-radius:12px;
                    padding:20px;text-align:center;margin-bottom:8px;">
            <div style="font-size:44px;font-weight:800;color:{score_color};line-height:1;">{score}</div>
            <div style="font-size:13px;font-weight:600;color:{score_color};margin-top:4px;">{label}</div>
            <div style="font-size:11px;color:#8a9aaa;margin-top:2px;">Quality score / 100</div>
        </div>""", unsafe_allow_html=True)

    with col2:
        errors   = sum(1 for c in checks if c["severity"] == "error")
        warnings = sum(1 for c in checks if c["severity"] == "warning")
        infos    = sum(1 for c in checks if c["severity"] == "info")
        metric_row([
            {"label": "Errors",   "value": str(errors),   "icon": "🔴",
             "delta_type": "negative" if errors   else "neutral"},
            {"label": "Warnings", "value": str(warnings), "icon": "🟡",
             "delta_type": "negative" if warnings else "neutral"},
            {"label": "Info",     "value": str(infos),    "icon": "🔵"},
        ])

    if not checks:
        st.success("✅ No quality issues detected — your dataset looks clean!")
        return

    section_title(f"{len(checks)} issue(s) found")

    for chk in checks:
        sev  = chk["severity"]
        bg, fg = _ISSUE_SEVERITY.get(sev, ("#f1f5f9", "#475569"))
        icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(sev, "•")
        cols_html = ""
        if chk["columns"]:
            tags = "".join(
                f'<span style="background:#f1f5f9;color:#475569;font-size:11px;'
                f'padding:2px 7px;border-radius:99px;margin:2px;">{c}</span>'
                for c in chk["columns"][:8]
            )
            extra = f" +{len(chk['columns'])-8} more" if len(chk["columns"]) > 8 else ""
            cols_html = f'<div style="margin-top:8px;">{tags}{extra}</div>'

        st.markdown(f"""
        <div style="background:{bg}22;border-left:4px solid {fg};border-radius:0 8px 8px 0;
                    padding:14px 16px;margin:8px 0;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                <span>{icon}</span>
                <span style="font-size:13.5px;font-weight:600;color:#1a2332;">{chk["name"]}</span>
                <span style="font-size:11px;font-weight:600;background:{bg};color:{fg};
                             padding:2px 7px;border-radius:99px;">{sev}</span>
            </div>
            <div style="font-size:13px;color:#4a5a6a;">{chk["description"]}</div>
            {cols_html}
        </div>""", unsafe_allow_html=True)


# ── Statistics tab ───────────────────────────────────────────────────────────

def _render_statistics(df: pd.DataFrame) -> None:
    section_title("Descriptive Statistics")

    num_df = df.select_dtypes("number")
    cat_df = df.select_dtypes("object")

    if not num_df.empty:
        st.markdown("**Numeric columns**")
        desc = num_df.describe().T.round(4)
        from app.analytics.statistics import describe
        full = describe(df)
        for col in ("skew", "kurtosis"):
            if col in full.columns:
                desc[col] = full[col].round(3)
        st.dataframe(desc.fillna("—"), use_container_width=True)
    else:
        st.info("No numeric columns.")

    if not cat_df.empty:
        section_title("Categorical columns")
        cat_desc = cat_df.describe().T
        st.dataframe(cat_desc.fillna("—"), use_container_width=True)

    # Value counts for categorical columns
    if not cat_df.empty:
        section_title("Top value counts")
        cat_cols = cat_df.columns.tolist()
        pick = st.selectbox("Column", cat_cols, key="stats_vc")
        vc = df[pick].value_counts().head(20).reset_index()
        vc.columns = [pick, "Count"]
        vc["Percentage"] = (vc["Count"] / len(df) * 100).round(2)
        col1, col2 = st.columns([2, 3])
        with col1:
            st.dataframe(vc, use_container_width=True, hide_index=True)
        with col2:
            import plotly.express as px
            fig = px.bar(vc.head(15), x=pick, y="Count", text="Count")
            fig.update_layout(
                plot_bgcolor="white", paper_bgcolor="white",
                font_family="Inter, sans-serif", font_color="#1a2332",
                margin=dict(t=20, b=40, l=10, r=10),
                xaxis_tickangle=-35, height=320,
            )
            fig.update_traces(textposition="outside", marker_color="#2563eb")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── Export tab ───────────────────────────────────────────────────────────────

def _render_export(df: pd.DataFrame, lr) -> None:
    section_title("Download dataset")

    fname = lr.filename.rsplit(".", 1)[0]

    col1, col2 = st.columns([2, 3])
    with col1:
        st.markdown('<div class="content-card">', unsafe_allow_html=True)
        content_card("Export options", f"Source: {lr.filename}")

        row_limit = st.selectbox(
            "Rows to export", ["All rows", "First 1,000", "First 10,000"],
            key="exp_row_limit",
        )
        n_export = None if row_limit == "All rows" else int(row_limit.split()[1].replace(",", ""))
        export_df = df if n_export is None else df.head(n_export)

        st.markdown(
            f'<div style="font-size:12px;color:#8a9aaa;padding:6px 0;">'
            f'Will export {min(len(export_df), len(df)):,} rows × {len(df.columns)} columns</div>',
            unsafe_allow_html=True,
        )

        st.download_button(
            "⬇️  Download CSV",
            data=to_csv_bytes(export_df),
            file_name=f"{fname}.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
        st.download_button(
            "⬇️  Download Excel (.xlsx)",
            data=to_excel_bytes(export_df),
            file_name=f"{fname}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="content-card">', unsafe_allow_html=True)
        content_card("File info", "Current dataset metadata")
        for label, val in [
            ("Filename",      lr.filename),
            ("File type",     lr.file_type.upper()),
            ("Active sheet",  lr.active_sheet or "—"),
            ("Encoding",      lr.encoding),
            ("Rows",          f"{lr.rows:,}"),
            ("Columns",       str(lr.columns)),
            ("Memory (est.)", f"{round(df.memory_usage(deep=True).sum()/1024, 1)} KB"),
        ]:
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;padding:7px 0;'
                f'border-bottom:1px solid #eef2f7;font-size:13px;">'
                f'<span style="color:#8a9aaa;">{label}</span>'
                f'<span style="color:#1a2332;font-weight:500;">{val}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        st.markdown('</div>', unsafe_allow_html=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _null_bar(pct: float) -> str:
    """Mini SVG progress bar for null percentage (unused in table but available)."""
    filled = max(0.0, min(100.0, pct))
    color  = "#ef4444" if filled > 50 else ("#f59e0b" if filled > 20 else "#10b981")
    return (
        f'<svg width="60" height="6" style="border-radius:3px;overflow:hidden;">'
        f'<rect width="60" height="6" fill="#f0f4f8"/>'
        f'<rect width="{filled * 0.6:.1f}" height="6" fill="{color}"/>'
        f'</svg>'
    )


def _issue_badges(issues: list[str]) -> str:
    if not issues:
        return ""
    labels = {
        "all_null":               ("All null",         "error"),
        "constant":               ("Constant",         "warning"),
        "high_null_severe":       ("≥50% null",        "warning"),
        "high_null":              ("20–49% null",      "info"),
        "numeric_as_string":      ("Num→text",         "warning"),
        "datetime_as_string":     ("Date→text",        "info"),
        "high_cardinality":       ("High cardinality", "info"),
        "leading_trailing_spaces":("Whitespace",       "info"),
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
