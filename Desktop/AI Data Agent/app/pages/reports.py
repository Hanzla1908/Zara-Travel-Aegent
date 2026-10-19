import streamlit as st
from app.components.cards import page_header, section_title, empty_state, metric_row, content_card


def render() -> None:
    page_header("Reports", "Generate and export analysis reports.")

    df = st.session_state.get("df")

    if df is None:
        empty_state("📋", "No dataset loaded",
                    "Upload a dataset to generate an automated analysis report.")
        return

    section_title("Report Builder")

    col1, col2 = st.columns([2, 1])

    with col1:
        report_title = st.text_input("Report title", value="Data Analysis Report", key="rep_title")
        report_desc  = st.text_area("Description (optional)", height=80, key="rep_desc",
                                    placeholder="Brief description of the dataset and purpose…")
        include_stats    = st.checkbox("Include descriptive statistics", value=True)
        include_nulls    = st.checkbox("Include missing value analysis", value=True)
        include_corr     = st.checkbox("Include correlation matrix", value=True)
        include_head     = st.checkbox("Include data preview (first 10 rows)", value=True)

    with col2:
        st.markdown("""
        <div class="content-card">
            <div class="card-title" style="margin-bottom:10px;">Report formats</div>""",
            unsafe_allow_html=True)
        for fmt, desc in [("📊 HTML", "Interactive, browser-ready"),
                           ("📄 CSV", "Raw data export"),
                           ("📗 Excel", "Multi-sheet workbook")]:
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;align-items:center;
                        padding:8px 0;border-bottom:1px solid #eef2f7;">
                <span style="font-size:13px;font-weight:600;color:#1a2332;">{fmt}</span>
                <span style="font-size:12px;color:#8a9aaa;">{desc}</span>
            </div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    if st.button("⚡ Generate Report", type="primary", use_container_width=False):
        _generate_report(
            df, report_title, report_desc,
            include_stats, include_nulls, include_corr, include_head,
        )


def _generate_report(df, title, desc, stats, nulls, corr, head) -> None:
    from app.analytics.profiler import profile as compute_profile
    from app.analytics.statistics import describe, correlation_matrix
    from app.services.export_service import to_csv_bytes
    import pandas as pd

    full = compute_profile(df)
    p = full["summary"]

    with st.spinner("Building report…"):
        sections: list[str] = [f"# {title}\n"]
        if desc:
            sections.append(f"_{desc}_\n")

        sections.append("## Dataset Summary\n")
        sections.append(f"| Metric | Value |\n|---|---|\n"
                        f"| Rows | {p['rows']:,} |\n"
                        f"| Columns | {p['columns']} |\n"
                        f"| Missing cells | {p['missing_cells']:,} ({p['missing_pct']}%) |\n"
                        f"| Duplicate rows | {p['duplicate_rows']:,} |\n"
                        f"| Memory | {p['memory_kb']} KB |\n")

        if stats:
            sections.append("\n## Descriptive Statistics\n")
            sections.append(describe(df).fillna("—").to_markdown())

        if nulls:
            sections.append("\n## Missing Value Analysis\n")
            null_df = df.isna().sum().rename("Missing").to_frame()
            null_df["Pct"] = (null_df["Missing"] / len(df) * 100).round(2)
            null_df = null_df[null_df["Missing"] > 0].sort_values("Missing", ascending=False)
            if null_df.empty:
                sections.append("✅ No missing values found.\n")
            else:
                sections.append(null_df.to_markdown())

        if corr:
            sections.append("\n## Correlation Matrix\n")
            sections.append(correlation_matrix(df).round(3).to_markdown())

        if head:
            sections.append("\n## Data Preview (first 10 rows)\n")
            sections.append(df.head(10).to_markdown(index=False))

        report_md = "\n".join(sections)

    st.success("✅ Report generated!")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button("⬇️ Download Markdown",
                           data=report_md.encode("utf-8"),
                           file_name=f"{title.replace(' ','_')}.md",
                           mime="text/markdown", use_container_width=True)
    with col2:
        st.download_button("⬇️ Download CSV (raw data)",
                           data=to_csv_bytes(df),
                           file_name="dataset.csv",
                           mime="text/csv", use_container_width=True)

    with st.expander("📄 Preview report"):
        st.markdown(report_md)
