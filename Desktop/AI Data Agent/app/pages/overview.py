import streamlit as st
from app.components.cards import page_header, metric_row, section_title, empty_state, content_card


def render() -> None:
    page_header(
        "Overview",
        "Welcome back — here's a summary of your workspace.",
    )

    df = st.session_state.get("df")

    if df is None:
        # ── Welcome / empty state ──────────────────────────────────
        col1, col2 = st.columns([3, 2])
        with col1:
            st.markdown("""
            <div class="content-card" style="padding:32px;">
                <div style="font-size:42px;margin-bottom:16px;">👋</div>
                <div style="font-size:20px;font-weight:700;color:#1a2332;margin-bottom:8px;">
                    Get started with AI Data Analysis
                </div>
                <div style="font-size:14px;color:#6a7a8a;line-height:1.7;max-width:420px;">
                    Upload a CSV, Excel, Parquet, or JSON file using the sidebar.
                    The AI Analyst will help you explore, visualize, and extract
                    insights from your data instantly.
                </div>
                <div style="margin-top:20px;display:flex;gap:12px;flex-wrap:wrap;">
                    <span class="badge info">📄 CSV / Excel</span>
                    <span class="badge purple">📦 Parquet</span>
                    <span class="badge success">🔄 JSON</span>
                    <span class="badge warning">⚡ Up to 200 MB</span>
                </div>
            </div>""", unsafe_allow_html=True)

        with col2:
            st.markdown("""
            <div class="content-card" style="padding:24px;">
                <div class="card-header" style="margin-bottom:14px;padding-bottom:10px;">
                    <div class="card-title">Quick actions</div>
                </div>""", unsafe_allow_html=True)
            for label, desc in [
                ("📁 Upload data", "Import from CSV, Excel, Parquet"),
                ("🤖 Ask the AI", "Natural language data questions"),
                ("📊 Build charts", "Drag-and-drop chart explorer"),
                ("📋 Export report", "PDF / Excel summary"),
            ]:
                st.markdown(f"""
                <div style="display:flex;align-items:flex-start;gap:10px;padding:10px 0;
                            border-bottom:1px solid #eef2f7;">
                    <div style="font-size:14px;font-weight:600;color:#1a2332;min-width:130px;">{label}</div>
                    <div style="font-size:12.5px;color:#8a9aaa;">{desc}</div>
                </div>""", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    else:
        # ── Dataset loaded — show summary metrics ──────────────────
        from app.analytics.profiler import profile as compute_profile
        full = compute_profile(df)
        p = full["summary"]   # new profiler returns {"summary": ..., "columns": ..., "quality": ...}

        lr = st.session_state.get("load_result")
        quality_score = full["quality"]["score"]
        score_color = "#10b981" if quality_score >= 80 else ("#f59e0b" if quality_score >= 60 else "#ef4444")

        metric_row([
            {"label": "Total Rows",    "value": f"{p['rows']:,}",         "icon": "📋"},
            {"label": "Columns",       "value": str(p["columns"]),        "icon": "📐"},
            {"label": "Missing Cells", "value": f"{p['missing_pct']}%",   "icon": "🔍",
             "delta": f"{p['missing_cells']:,} cells",
             "delta_type": "negative" if p["missing_pct"] > 5 else "neutral"},
            {"label": "Duplicate Rows","value": f"{p['duplicate_rows']:,}","icon": "♻️",
             "delta_type": "negative" if p["duplicate_rows"] > 0 else "neutral"},
            {"label": "Quality Score", "value": str(quality_score),       "icon": "✅",
             "delta_type": "positive" if quality_score >= 80 else ("neutral" if quality_score >= 60 else "negative")},
            {"label": "Memory",        "value": f"{p['memory_kb']} KB",   "icon": "💾"},
        ])

        section_title("Column Summary")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<div class="content-card">', unsafe_allow_html=True)
            content_card("Numeric Columns", f"{len(p['numeric_columns'])} columns", "Quantitative")
            if p["numeric_columns"]:
                for c in p["numeric_columns"][:8]:
                    st.markdown(f'<div style="padding:4px 0;font-size:13px;color:#4a5a6a;">📈 {c}</div>',
                                unsafe_allow_html=True)
                if len(p["numeric_columns"]) > 8:
                    st.markdown(f'<div style="font-size:12px;color:#8a9aaa;padding-top:4px;">'
                                f'+{len(p["numeric_columns"])-8} more</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:#8a9aaa;font-size:13px;">No numeric columns</div>',
                            unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with col2:
            st.markdown('<div class="content-card">', unsafe_allow_html=True)
            content_card("Categorical Columns", f"{len(p['categorical_columns'])} columns", "Qualitative")
            if p["categorical_columns"]:
                for c in p["categorical_columns"][:8]:
                    st.markdown(f'<div style="padding:4px 0;font-size:13px;color:#4a5a6a;">🏷️ {c}</div>',
                                unsafe_allow_html=True)
                if len(p["categorical_columns"]) > 8:
                    st.markdown(f'<div style="font-size:12px;color:#8a9aaa;padding-top:4px;">'
                                f'+{len(p["categorical_columns"])-8} more</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:#8a9aaa;font-size:13px;">No categorical columns</div>',
                            unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
