import streamlit as st
import os
from app.components.cards import page_header, section_title, empty_state


_SYSTEM = """You are a senior data analyst assistant. The user will ask questions about their dataset.
Be concise, precise, and actionable. When referencing numbers use the data summary provided.
Format code in markdown code blocks. Format tables as markdown tables."""

_STARTERS = [
    "What are the key statistics of this dataset?",
    "Which columns have missing values?",
    "What correlations exist between numeric columns?",
    "Summarize the distribution of each column.",
    "What are the top 5 most common values in each categorical column?",
]


def render() -> None:
    page_header("AI Analyst", "Ask questions about your data in plain English.")

    df = st.session_state.get("df")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if not api_key:
        st.warning("**ANTHROPIC_API_KEY** is not set. Add it to your `.env` file to enable the AI Analyst.")

    # ── Conversation history ─────────────────────────────────────────
    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    # ── Suggestion chips (shown when chat is empty) ──────────────────
    if not st.session_state["messages"]:
        st.markdown("""
        <div class="content-card" style="margin-bottom:16px;">
            <div class="card-title" style="margin-bottom:12px;">💡 Suggested questions</div>
        </div>""", unsafe_allow_html=True)
        cols = st.columns(len(_STARTERS))
        for i, (col, q) in enumerate(zip(cols, _STARTERS)):
            with col:
                if st.button(q, key=f"starter_{i}", use_container_width=True):
                    _send_message(q, df, api_key)
                    st.rerun()

    # ── Message history ──────────────────────────────────────────────
    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Input ────────────────────────────────────────────────────────
    prompt = st.chat_input(
        "Ask anything about your data…" if df is not None else "Upload data first, then ask questions…",
        disabled=(df is None and not st.session_state["messages"]),
    )

    if prompt:
        _send_message(prompt, df, api_key)
        st.rerun()

    # ── Clear button ─────────────────────────────────────────────────
    if st.session_state["messages"]:
        if st.button("🗑️ Clear conversation", key="clear_chat"):
            st.session_state["messages"] = []
            st.rerun()


def _send_message(prompt: str, df, api_key: str) -> None:
    st.session_state["messages"].append({"role": "user", "content": prompt})

    if not api_key:
        st.session_state["messages"].append({
            "role": "assistant",
            "content": "⚠️ No API key configured. Please set `ANTHROPIC_API_KEY` in your `.env` file.",
        })
        return

    context = ""
    if df is not None:
        from app.analytics.profiler import profile as compute_profile
        from app.analytics.statistics import describe
        full = compute_profile(df)
        p = full["summary"]
        stats = describe(df).to_string()
        context = (
            f"\n\n---\nDataset summary:\n"
            f"- Shape: {p['rows']} rows × {p['columns']} columns\n"
            f"- Numeric columns: {', '.join(p['numeric_columns'])}\n"
            f"- Categorical columns: {', '.join(p['categorical_columns'])}\n"
            f"- Missing %: {p['missing_pct']}%\n"
            f"- Duplicates: {p['duplicate_rows']}\n"
            f"- Quality score: {full['quality']['score']}/100\n\n"
            f"Descriptive statistics:\n{stats}"
        )

    from app.services.claude_service import ask
    reply = ask(prompt + context, system=_SYSTEM)
    st.session_state["messages"].append({"role": "assistant", "content": reply})
