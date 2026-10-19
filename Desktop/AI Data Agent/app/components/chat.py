import streamlit as st
from app.services.claude_service import ask


def render_chat() -> None:
    st.subheader("Ask the Analyst")
    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask a question about your data…"):
        st.session_state["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                df = st.session_state.get("df")
                context = ""
                if df is not None:
                    context = f"\n\nDataset info:\n{df.describe(include='all').to_string()}"
                reply = ask(prompt + context)
            st.markdown(reply)
            st.session_state["messages"].append({"role": "assistant", "content": reply})
