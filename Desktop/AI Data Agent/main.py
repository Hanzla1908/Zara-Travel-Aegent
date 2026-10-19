"""Entry point — run with: streamlit run main.py"""

import streamlit as st
from pathlib import Path
from app.utils.config import load_config


# ── Page config (must be first Streamlit call) ───────────────────────────────
st.set_page_config(
    page_title="AI Data Analyst",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _inject_css() -> None:
    css_path = Path(__file__).parent / "assets" / "styles" / "theme.css"
    css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def main() -> None:
    load_config()
    _inject_css()

    from app.components.sidebar import render_sidebar
    page = render_sidebar()

    # ── Route to page ────────────────────────────────────────────────
    if page == "Overview":
        from app.pages.overview import render
    elif page == "Dashboard":
        from app.pages.dashboard import render
    elif page == "Data Explorer":
        from app.pages.data_explorer import render
    elif page == "AI Analyst":
        from app.pages.ai_analyst import render
    elif page == "Reports":
        from app.pages.reports import render
    elif page == "Settings":
        from app.pages.settings import render
    else:
        from app.pages.overview import render

    render()


if __name__ == "__main__":
    main()
