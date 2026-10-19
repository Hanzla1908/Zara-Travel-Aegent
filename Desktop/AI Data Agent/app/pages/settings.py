import streamlit as st
import os
from app.components.cards import page_header, section_title, content_card


def render() -> None:
    page_header("Settings", "Configure the AI Analyst and application preferences.")

    section_title("API Configuration")
    st.markdown('<div class="content-card">', unsafe_allow_html=True)
    content_card("Anthropic API Key", "Required for AI Analyst features")

    current = os.getenv("ANTHROPIC_API_KEY", "")
    masked = f"sk-ant-...{current[-6:]}" if len(current) > 10 else ("Not set" if not current else "Set")

    col1, col2 = st.columns([3, 1])
    with col1:
        st.text_input("Current key", value=masked, disabled=True, key="disp_key")
    with col2:
        st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
        status_color = "#10b981" if current else "#ef4444"
        status_text = "Active" if current else "Missing"
        st.markdown(f'<div style="background:{status_color}1a;color:{status_color};font-size:12px;'
                    f'font-weight:600;padding:8px 12px;border-radius:6px;text-align:center;">'
                    f'{"✓ " if current else "✗ "}{status_text}</div>', unsafe_allow_html=True)

    st.info("To update the API key, edit your `.env` file and restart the app.")
    st.markdown('</div>', unsafe_allow_html=True)

    section_title("Model Preferences")
    st.markdown('<div class="content-card">', unsafe_allow_html=True)
    content_card("Claude Model", "Select the AI model for analysis")

    models = [
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
    ]
    current_model = st.session_state.get("model", os.getenv("DEFAULT_MODEL", models[0]))
    selected = st.selectbox("Model", models,
                            index=models.index(current_model) if current_model in models else 0,
                            key="model_sel")
    if selected != current_model:
        st.session_state["model"] = selected
        st.success(f"Model updated to **{selected}**")

    for name, desc, ctx in [
        ("claude-opus-4-5",    "Most capable, best for complex analysis",   "200K tokens"),
        ("claude-sonnet-4-5",  "Balanced speed and capability",             "200K tokens"),
        ("claude-haiku-4-5",   "Fastest, best for quick questions",         "200K tokens"),
    ]:
        icon = "🥇" if name == selected else "◇"
        st.markdown(f"""
        <div style="display:flex;justify-content:space-between;align-items:center;
                    padding:8px 0;border-bottom:1px solid #eef2f7;font-size:13px;">
            <span style="color:#1a2332;font-weight:{'600' if name==selected else '400'};">{icon} {name}</span>
            <span style="color:#8a9aaa;font-size:12px;">{desc}</span>
            <span style="color:#8a9aaa;font-size:12px;">{ctx}</span>
        </div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    section_title("Upload Limits")
    st.markdown('<div class="content-card">', unsafe_allow_html=True)
    content_card("File Upload", "Supported formats and size limits")
    for fmt, limit, note in [
        ("CSV",     "200 MB", "Comma-separated values"),
        ("Excel",   "200 MB", ".xlsx / .xls"),
        ("Parquet", "200 MB", "Columnar format — fastest for large data"),
        ("JSON",    "200 MB", "Flat or record-oriented"),
    ]:
        st.markdown(f"""
        <div style="display:flex;gap:16px;padding:6px 0;border-bottom:1px solid #eef2f7;font-size:13px;">
            <span style="color:#1a2332;font-weight:600;min-width:70px;">{fmt}</span>
            <span style="color:#2563eb;font-weight:600;min-width:70px;">{limit}</span>
            <span style="color:#8a9aaa;">{note}</span>
        </div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    section_title("About")
    st.markdown("""
    <div class="content-card">
        <div style="font-size:13.5px;color:#4a5a6a;line-height:1.8;">
            <strong>AI Data Analyst Agent</strong> v0.1.0<br>
            Built with Streamlit · Pandas · Plotly · Anthropic Claude API<br>
            <br>
            <span style="color:#8a9aaa;">Stack: Python 3.13 · Streamlit 1.66 · Plotly 7</span>
        </div>
    </div>""", unsafe_allow_html=True)
