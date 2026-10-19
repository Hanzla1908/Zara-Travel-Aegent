"""AI Analyst page.

Two tabs:
  Auto Insights — one-click structured report generated from validated stats
  Chat          — multi-turn Q&A backed by the same stats context

Claude never receives raw rows.  All prompts are built from aggregated
statistics via insight_builder.  Facts and hypotheses are separated in both
the system prompt and the rendered output.

Usage limits: warn at 20 calls/session, block at 30.
"""

from __future__ import annotations

import os

import streamlit as st

from app.components.cards import page_header, section_title, empty_state
from app.services.claude_service import (
    WARN_AT, BLOCK_AT, INSIGHT_TOKENS, DEFAULT_TOKENS,
    ConfigError, UsageLimitError,
    ask, stream_response, get_usage,
)

# ── System prompts ────────────────────────────────────────────────────────────

_INSIGHT_SYSTEM = """\
You are a senior data analyst producing a structured insight report.

CRITICAL RULES:
1. Only cite statistics that appear in the DATA SUMMARY. Never invent, estimate,
   or extrapolate values not explicitly given there.
2. Sections 1–3 contain FACTS only — direct observations from the data.
3. Section 4 contains HYPOTHESES — interpretations or possible causes.
   Prefix every hypothesis bullet with "Possible:" and use hedged language
   (may, could, suggests, appears to).
4. Section 5 contains RECOMMENDATIONS — concrete next steps.
5. Each bullet ≤ 30 words.  Omit a section entirely if there is nothing
   meaningful to say.  Never pad with generic filler.
6. Humanise column names (replace underscores with spaces, title-case).

OUTPUT FORMAT (use exactly these headings):

## Key Trends
[Patterns in numeric and time-series data]

## Top & Bottom Performers
[Highest / lowest values per category]

## Anomalies
[Unexpected values, outliers, data quality issues worth investigating]

## Possible Explanations
[Hypotheses — speculative interpretations, clearly not facts]

## Actionable Recommendations
[Specific next steps for the analyst]
"""

_CHAT_SYSTEM = """\
You are a senior data analyst assistant.  The user will ask questions about
their dataset.  A statistical summary of the data is included in the first
message.

RULES:
- Only reference statistics present in the DATA SUMMARY.  Never invent numbers.
- When giving an interpretation, mark it as your hypothesis, not a fact.
- Be concise and direct.  Use markdown tables and code blocks where helpful.
- If a question cannot be answered from the summary, say so clearly and
  suggest what additional analysis would help.
"""

# ── Starter questions ─────────────────────────────────────────────────────────

_STARTERS = [
    "What are the most important patterns in this data?",
    "Which categories are over- or under-performing?",
    "Are there any data quality issues I should address first?",
    "What correlations should I investigate further?",
    "What's driving the variation in the primary metric?",
]


# ── Page entry point ──────────────────────────────────────────────────────────

def render() -> None:
    page_header("AI Analyst", "Structured insights and Q&A powered by Claude.")

    df = st.session_state.get("df")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    # ── API key warning ──────────────────────────────────────────────────
    if not api_key:
        st.warning(
            "**ANTHROPIC_API_KEY** is not set.  "
            "Add it to your `.env` file (see `.env.example`) and restart the app.",
            icon="🔑",
        )
        return

    # ── No data ──────────────────────────────────────────────────────────
    if df is None or df.empty:
        empty_state(
            "🤖",
            "No dataset loaded",
            "Upload a CSV or Excel file in the sidebar, then return here for AI insights.",
        )
        return

    # ── Usage indicator ───────────────────────────────────────────────────
    _render_usage_bar()

    # ── Tabs ─────────────────────────────────────────────────────────────
    tab_insights, tab_chat = st.tabs(["✨ Auto Insights", "💬 Chat"])

    with tab_insights:
        _render_insights_tab(df)

    with tab_chat:
        _render_chat_tab(df)


# ── Auto Insights tab ─────────────────────────────────────────────────────────

def _render_insights_tab(df) -> None:
    st.markdown(
        '<div style="color:#64748b;font-size:13px;margin-bottom:16px;">'
        "Claude analyses the dataset's aggregated statistics — never your raw rows — "
        "and returns a structured report that clearly separates observed facts from hypotheses."
        "</div>",
        unsafe_allow_html=True,
    )

    # Detect filtered state
    intel = _get_intel(df)
    from app.services.filter_service import build_options, apply_filters, active_count
    opts = build_options(df, intel)
    filtered_df = apply_filters(df, intel, st.session_state, opts)
    n_active = active_count(st.session_state, opts)
    is_filtered = len(filtered_df) < len(df)

    # Source badge
    if is_filtered:
        st.markdown(
            f'<span style="background:#2563eb;color:#fff;border-radius:6px;'
            f'padding:2px 10px;font-size:11px;font-weight:700;">'
            f'🔍 Analysing filtered view — {len(filtered_df):,} / {len(df):,} rows</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<span style="background:#f0f4f8;color:#64748b;border-radius:6px;'
            f'padding:2px 10px;font-size:11px;">'
            f'Analysing full dataset — {len(df):,} rows</span>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # Cached insights key: changes when df identity or filter state changes
    cache_key = f"_insights_{id(df)}_{n_active}_{len(filtered_df)}"
    existing = st.session_state.get(cache_key)

    col_btn, col_clear = st.columns([1, 4])
    with col_btn:
        generate = st.button(
            "✨ Generate Insights",
            key="gen_insights_btn",
            use_container_width=True,
            type="primary",
            disabled=get_usage() >= BLOCK_AT,
        )
    with col_clear:
        if existing and st.button("🗑 Clear", key="clear_insights_btn"):
            del st.session_state[cache_key]
            st.rerun()

    if generate:
        _run_insights(filtered_df, df, intel, cache_key)

    # Render cached result
    if st.session_state.get(cache_key):
        st.markdown("---")
        _render_insight_result(st.session_state[cache_key])


def _run_insights(filtered_df, full_df, intel, cache_key: str) -> None:
    """Build context, call Claude, stream into a placeholder, cache result."""
    from app.analytics.insight_builder import build_context

    context = build_context(filtered_df, intel, full_df=full_df)
    prompt = (
        "Generate a structured insight report for the dataset described below.\n\n"
        "DATA SUMMARY\n"
        "============\n"
        f"{context}"
    )

    placeholder = st.empty()
    full_text = ""
    try:
        with st.spinner("Analysing data…"):
            # Use placeholder to stream into
            with placeholder.container():
                st.markdown("*Generating insights…*")

        full_text_parts: list[str] = []
        with placeholder.container():
            result_placeholder = st.empty()
            for chunk in stream_response(
                prompt,
                system=_INSIGHT_SYSTEM,
                max_tokens=INSIGHT_TOKENS,
            ):
                full_text_parts.append(chunk)
                result_placeholder.markdown("".join(full_text_parts) + "▌")
            full_text = "".join(full_text_parts)
            result_placeholder.markdown(full_text)

        st.session_state[cache_key] = full_text

    except (ConfigError, UsageLimitError) as exc:
        placeholder.error(str(exc), icon="🔑" if isinstance(exc, ConfigError) else "🚫")
    except RuntimeError as exc:
        placeholder.error(str(exc), icon="⚠️")
    except Exception as exc:
        placeholder.error(f"Unexpected error: {exc}", icon="⚠️")


def _render_insight_result(text: str) -> None:
    """Render the cached insight with a visual legend."""
    st.markdown(
        """<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:12px;font-size:11px;">
          <span style="background:#dbeafe;color:#1e40af;border-radius:4px;padding:2px 8px;">
            📊 Facts — from data only</span>
          <span style="background:#fef9c3;color:#854d0e;border-radius:4px;padding:2px 8px;">
            💡 "Possible:" prefix = hypothesis</span>
          <span style="background:#dcfce7;color:#166534;border-radius:4px;padding:2px 8px;">
            ✅ Recommendations</span>
        </div>""",
        unsafe_allow_html=True,
    )
    st.markdown(text)


# ── Chat tab ──────────────────────────────────────────────────────────────────

def _render_chat_tab(df) -> None:
    intel = _get_intel(df)

    # Build shared context once per df (cache it)
    ctx_key = f"_chat_context_{id(df)}"
    if ctx_key not in st.session_state:
        from app.analytics.insight_builder import build_context
        st.session_state[ctx_key] = build_context(df, intel)
    context = st.session_state[ctx_key]

    # Per-tab message history (separate from any old "messages" key)
    if "_chat_history" not in st.session_state:
        st.session_state["_chat_history"] = []
    history: list[dict] = st.session_state["_chat_history"]

    # Suggestion chips (shown when chat is empty)
    if not history:
        st.markdown(
            '<div style="color:#64748b;font-size:12px;margin-bottom:8px;">Try a question:</div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(len(_STARTERS))
        for i, (col, q) in enumerate(zip(cols, _STARTERS)):
            with col:
                if st.button(q, key=f"starter_{i}", use_container_width=True):
                    _chat_send(q, context, history)
                    st.rerun()

    # Message history
    for msg in history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input
    prompt = st.chat_input(
        "Ask anything about your data…",
        disabled=get_usage() >= BLOCK_AT,
    )
    if prompt:
        _chat_send(prompt, context, history)
        st.rerun()

    # Clear button
    if history:
        if st.button("🗑️ Clear conversation", key="clear_chat"):
            st.session_state["_chat_history"] = []
            st.rerun()


def _chat_send(prompt: str, context: str, history: list[dict]) -> None:
    """Add user message, call Claude (streaming), append assistant reply."""
    history.append({"role": "user", "content": prompt})

    # First turn injects the data context as a system-adjacent user primer
    if len(history) == 1:
        full_prompt = (
            f"{prompt}\n\n"
            "DATA SUMMARY (use only these statistics in your answer)\n"
            "======================================================\n"
            f"{context}"
        )
    else:
        full_prompt = prompt

    # Build history slice for API (all prior pairs, NOT the current message)
    api_history: list[dict] = history[:-1]  # everything except the latest user msg

    # Inject context into the first user message in history too, if needed
    if api_history and len(api_history) >= 1:
        # Context is already baked into the first assistant exchange
        pass

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_text_parts: list[str] = []
        try:
            for chunk in stream_response(
                full_prompt,
                system=_CHAT_SYSTEM,
                max_tokens=DEFAULT_TOKENS,
                history=api_history,
            ):
                full_text_parts.append(chunk)
                placeholder.markdown("".join(full_text_parts) + "▌")
            reply = "".join(full_text_parts)
            placeholder.markdown(reply)
            history.append({"role": "assistant", "content": reply})
        except (ConfigError, UsageLimitError) as exc:
            msg = str(exc)
            placeholder.error(msg)
            history.append({"role": "assistant", "content": f"⚠️ {msg}"})
        except RuntimeError as exc:
            msg = str(exc)
            placeholder.error(msg)
            history.append({"role": "assistant", "content": f"⚠️ {msg}"})
        except Exception as exc:
            msg = f"Unexpected error: {exc}"
            placeholder.error(msg)
            history.append({"role": "assistant", "content": f"⚠️ {msg}"})


# ── Usage indicator ───────────────────────────────────────────────────────────

def _render_usage_bar() -> None:
    n = get_usage()
    pct = n / BLOCK_AT * 100

    if n >= BLOCK_AT:
        st.error(
            f"Session limit reached ({BLOCK_AT} API calls). "
            "Refresh the page to start a new session.",
            icon="🚫",
        )
        return

    color = "#ef4444" if n >= WARN_AT else ("#f59e0b" if n >= WARN_AT * 0.7 else "#10b981")
    st.markdown(
        f"""<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
          <div style="flex:1;background:#e2e8f0;border-radius:99px;height:6px;overflow:hidden;">
            <div style="width:{pct:.0f}%;background:{color};height:100%;border-radius:99px;
                        transition:width 0.3s;"></div>
          </div>
          <span style="font-size:11px;color:#64748b;white-space:nowrap;">
            {n} / {BLOCK_AT} API calls this session</span>
        </div>""",
        unsafe_allow_html=True,
    )
    if n >= WARN_AT:
        st.warning(
            f"Approaching session limit ({n}/{BLOCK_AT} calls used). "
            "Refresh the page after this session to reset.",
            icon="⚠️",
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_intel(df):
    from app.analytics.column_intelligence import analyze
    key = f"_intel_{id(df)}"
    if key not in st.session_state:
        st.session_state[key] = analyze(df)
    return st.session_state[key]
