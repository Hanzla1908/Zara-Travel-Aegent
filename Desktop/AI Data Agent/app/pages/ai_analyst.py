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

from app.components.cards import page_header, empty_state
from app.services.claude_service import (
    WARN_AT, BLOCK_AT, INSIGHT_TOKENS, DEFAULT_TOKENS,
    ConfigError, UsageLimitError,
    stream_response, get_usage,
)

# ── System prompts ────────────────────────────────────────────────────────────

_INSIGHT_SYSTEM = """\
You are a senior data analyst producing a structured insight report.

CRITICAL RULES:
1. Only cite statistics that appear in the DATA SUMMARY. Never invent, estimate,
   or extrapolate values not explicitly given there.
2. Sections 1-3 contain FACTS only - direct observations from the data.
3. Section 4 contains HYPOTHESES - interpretations or possible causes.
   Prefix every hypothesis bullet with "Possible:" and use hedged language
   (may, could, suggests, appears to).
4. Section 5 contains RECOMMENDATIONS - concrete next steps.
5. Each bullet at most 30 words. Omit a section entirely if there is nothing
   meaningful to say. Never pad with generic filler.
6. Humanise column names (replace underscores with spaces, title-case).

OUTPUT FORMAT (use exactly these headings):

## Key Trends
[Patterns in numeric and time-series data]

## Top & Bottom Performers
[Highest / lowest values per category]

## Anomalies
[Unexpected values, outliers, data quality issues worth investigating]

## Possible Explanations
[Hypotheses - speculative interpretations, clearly not facts]

## Actionable Recommendations
[Specific next steps for the analyst]
"""

_CHAT_SYSTEM_TEMPLATE = """\
You are a senior data analyst assistant. A statistical summary of the dataset
is included below. The user will ask questions about their data.

RULES:
- Only reference statistics present in the DATA SUMMARY. Never invent numbers.
- When giving an interpretation, mark it as your hypothesis, not a fact.
- Be concise and direct. Use markdown tables and code blocks where helpful.
- If a question cannot be answered from the summary, say so clearly and
  suggest what additional analysis would help.

DATA SUMMARY
============
{context}
"""

# ── Starter questions ─────────────────────────────────────────────────────────

_STARTERS = [
    "What are the most important patterns in this data?",
    "Which categories are over- or under-performing?",
    "Are there any data quality issues I should fix first?",
    "What correlations should I investigate further?",
    "What's driving the variation in the primary metric?",
]


# ── Page entry point ──────────────────────────────────────────────────────────

def render() -> None:
    page_header("AI Analyst", "Structured insights and Q&A powered by Claude.")

    df = st.session_state.get("df")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    has_key = bool(api_key)

    # ── API key banner (non-blocking) ────────────────────────────────────
    if not has_key:
        st.warning(
            "**ANTHROPIC_API_KEY** is not set.  "
            "Copy `.env.example` to `.env`, fill in your key, and restart the app.",
            icon="🔑",
        )

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
        _render_insights_tab(df, has_key)

    with tab_chat:
        _render_chat_tab(df, has_key)


# ── Auto Insights tab ─────────────────────────────────────────────────────────

def _render_insights_tab(df, has_key: bool) -> None:
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
            f'Analysing filtered view — {len(filtered_df):,} / {len(df):,} rows</span>',
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

    # Cache key changes when df identity, filter state, or row count changes
    cache_key = f"_insights_{id(df)}_{n_active}_{len(filtered_df)}"
    has_cached = bool(st.session_state.get(cache_key))

    col_btn, col_clear, col_spacer = st.columns([1, 1, 4])
    with col_btn:
        generate = st.button(
            "✨ Generate",
            key="gen_insights_btn",
            use_container_width=True,
            type="primary",
            disabled=not has_key or get_usage() >= BLOCK_AT,
            help="Set ANTHROPIC_API_KEY to enable" if not has_key else None,
        )
    with col_clear:
        if has_cached and st.button("🗑 Clear", key="clear_insights_btn", use_container_width=True):
            del st.session_state[cache_key]
            st.rerun()

    if generate:
        _run_insights(filtered_df, df, intel, cache_key)
        # rerun so the streamed placeholder is replaced by the clean cached render
        st.rerun()
    elif has_cached:
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

    result_area = st.empty()
    full_text_parts: list[str] = []

    try:
        for chunk in stream_response(
            prompt,
            system=_INSIGHT_SYSTEM,
            max_tokens=INSIGHT_TOKENS,
        ):
            full_text_parts.append(chunk)
            result_area.markdown("".join(full_text_parts) + " ▮")

        full_text = "".join(full_text_parts)
        result_area.markdown(full_text)
        st.session_state[cache_key] = full_text

    except (ConfigError, UsageLimitError) as exc:
        result_area.error(str(exc))
    except RuntimeError as exc:
        result_area.error(str(exc))
    except Exception as exc:
        result_area.error(f"Unexpected error: {exc}")


def _render_insight_result(text: str) -> None:
    st.markdown(
        """<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px;font-size:11px;">
          <span style="background:#dbeafe;color:#1e40af;border-radius:4px;padding:2px 8px;">
            Facts from data only</span>
          <span style="background:#fef9c3;color:#854d0e;border-radius:4px;padding:2px 8px;">
            "Possible:" prefix = hypothesis</span>
          <span style="background:#dcfce7;color:#166534;border-radius:4px;padding:2px 8px;">
            Recommendations</span>
        </div>""",
        unsafe_allow_html=True,
    )
    st.markdown(text)


# ── Chat tab ──────────────────────────────────────────────────────────────────

def _render_chat_tab(df, has_key: bool) -> None:
    intel = _get_intel(df)

    # Build data context and bake it into the system prompt (cached per df)
    ctx_key = f"_chat_context_{id(df)}"
    if ctx_key not in st.session_state:
        from app.analytics.insight_builder import build_context
        st.session_state[ctx_key] = build_context(df, intel)
    context: str = st.session_state[ctx_key]
    chat_system = _CHAT_SYSTEM_TEMPLATE.format(context=context)

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
                if st.button(
                    q, key=f"starter_{i}",
                    use_container_width=True,
                    disabled=not has_key or get_usage() >= BLOCK_AT,
                ):
                    _chat_send(q, chat_system, history)
                    st.rerun()

    # Message history
    for msg in history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input
    prompt = st.chat_input(
        "Ask anything about your data…" if has_key else "Set ANTHROPIC_API_KEY to enable chat",
        disabled=not has_key or get_usage() >= BLOCK_AT,
    )
    if prompt:
        _chat_send(prompt, chat_system, history)
        st.rerun()

    # Clear button
    if history:
        if st.button("🗑️ Clear conversation", key="clear_chat"):
            st.session_state["_chat_history"] = []
            st.rerun()


def _chat_send(prompt: str, chat_system: str, history: list[dict]) -> None:
    """Add user message, stream assistant reply, append to history."""
    history.append({"role": "user", "content": prompt})

    # Build prior-turn history for the API (all turns except the latest user msg)
    api_history: list[dict] = history[:-1]

    with st.chat_message("assistant"):
        area = st.empty()
        parts: list[str] = []
        try:
            for chunk in stream_response(
                prompt,
                system=chat_system,        # data context is always in system prompt
                max_tokens=DEFAULT_TOKENS,
                history=api_history,
            ):
                parts.append(chunk)
                area.markdown("".join(parts) + " ▮")
            reply = "".join(parts)
            area.markdown(reply)
            history.append({"role": "assistant", "content": reply})
        except (ConfigError, UsageLimitError) as exc:
            msg = str(exc)
            area.error(msg)
            history.append({"role": "assistant", "content": f"Error: {msg}"})
        except RuntimeError as exc:
            msg = str(exc)
            area.error(msg)
            history.append({"role": "assistant", "content": f"Error: {msg}"})
        except Exception as exc:
            msg = f"Unexpected error: {exc}"
            area.error(msg)
            history.append({"role": "assistant", "content": f"Error: {msg}"})


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
            <div style="width:{pct:.0f}%;background:{color};height:100%;border-radius:99px;"></div>
          </div>
          <span style="font-size:11px;color:#64748b;white-space:nowrap;">
            {n} / {BLOCK_AT} API calls</span>
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
