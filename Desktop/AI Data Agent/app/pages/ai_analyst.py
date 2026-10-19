"""AI Analyst page.

Two tabs:
  Auto Insights — one-click structured report generated from validated stats
  Chat          — plan → execute → explain flow (never runs LLM-generated code)

Claude returns a JSON query plan; Python validates every field against an
allowlist and executes it with Pandas.  Claude then explains the verified
result.  No arbitrary LLM-generated code or SQL is ever executed.

Usage limits: warn at 20 calls/session, block at 30.
Planning calls (step 1) do not count toward the limit.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from app.components.icons import icon as svg_icon
from app.components.cards import page_header, empty_state
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

# ── Analyst chat system prompts are in query_planner — imported on demand ─────

_ANALYST_EXPLAIN_TOKENS = 600   # per-message explanation


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
            svg_icon("bot", 48, "#cbd5e1"),
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


# ── Chat tab (plan → execute → explain) ───────────────────────────────────────

def _render_chat_tab(df: pd.DataFrame, has_key: bool) -> None:
    from app.analytics.query_planner import (
        build_schema_summary, build_suggestion_questions,
    )
    intel = _get_intel(df)

    schema_key = f"_analyst_schema_{id(df)}"
    if schema_key not in st.session_state:
        st.session_state[schema_key] = build_schema_summary(df, intel)
    schema_summary: str = st.session_state[schema_key]

    if "_analyst_history" not in st.session_state:
        st.session_state["_analyst_history"] = []
    history: list[dict] = st.session_state["_analyst_history"]

    # Suggestion chips (only when chat is empty)
    if not history:
        st.markdown(
            '<div style="color:#64748b;font-size:12px;margin-bottom:8px;">'
            "Try a question — results are computed in Python, then explained by Claude:</div>",
            unsafe_allow_html=True,
        )
        starters = build_suggestion_questions(df, intel)
        cols = st.columns(len(starters))
        for i, (col, q) in enumerate(zip(cols, starters)):
            with col:
                if st.button(
                    q, key=f"analyst_starter_{i}",
                    use_container_width=True,
                    disabled=not has_key or get_usage() >= BLOCK_AT,
                ):
                    _analyst_ask(q, df, intel, schema_summary, history)
                    st.rerun()

    # Render stored history
    for msg in history:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                _render_analyst_message(msg)
            else:
                st.markdown(msg["content"])

    # Chat input
    question = st.chat_input(
        "Ask anything about your data…" if has_key else "Set ANTHROPIC_API_KEY to enable chat",
        disabled=not has_key or get_usage() >= BLOCK_AT,
    )
    if question:
        _analyst_ask(question, df, intel, schema_summary, history)
        st.rerun()

    if history:
        if st.button("Clear conversation", key="clear_analyst_chat"):
            st.session_state["_analyst_history"] = []
            st.rerun()


def _render_analyst_message(msg: dict) -> None:
    """Re-render a stored assistant message from history."""
    if msg.get("plan_error"):
        st.warning(f"Could not build a query plan: {msg['plan_error']}", icon="⚠️")

    if msg.get("error"):
        st.error(msg["error"])

    result_df: pd.DataFrame | None = msg.get("result_df")
    result_chart = msg.get("result_chart")

    if result_chart is not None:
        st.plotly_chart(result_chart, use_container_width=True, config={"displayModeBar": False})

    if result_df is not None and not result_df.empty:
        with st.expander(f"Data table ({len(result_df)} rows)", expanded=False):
            st.dataframe(result_df, use_container_width=True)

    if msg.get("content"):
        st.markdown(msg["content"])


def _analyst_ask(
    question: str,
    df: pd.DataFrame,
    intel,
    schema_summary: str,
    history: list[dict],
) -> None:
    """Plan → validate → execute → explain.  Appends to history."""
    from app.analytics.query_planner import (
        PLANNER_SYSTEM, EXPLAINER_SYSTEM, FALLBACK_EXPLAINER_SYSTEM,
        parse_and_validate,
    )
    from app.analytics.query_executor import execute

    history.append({"role": "user", "content": question})

    result_df = None
    result_chart = None
    plan_error = ""
    exec_error = ""
    explanation = ""

    # Show user message immediately
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        status_area = st.empty()
        content_area = st.empty()

        try:
            # ── Step 1: Plan (free call — doesn't count toward usage limit) ──
            status_area.markdown("*Analysing your question…*")
            planner_prompt = (
                f"USER QUESTION: {question}\n\n"
                f"DATASET SCHEMA:\n{schema_summary}"
            )
            raw_plan = ask(
                planner_prompt,
                system=PLANNER_SYSTEM,
                max_tokens=600,
                bump=False,   # planning calls are free
            )

            # ── Step 2: Validate ─────────────────────────────────────────────
            plan_or_error = parse_and_validate(raw_plan, df, intel)

            if isinstance(plan_or_error, str):
                plan_error = plan_or_error
                status_area.empty()
                # Fallback: direct Claude answer from schema
                fallback_prompt = (
                    f"QUESTION: {question}\n\n"
                    f"DATASET SCHEMA:\n{schema_summary}"
                )
                parts: list[str] = []
                for chunk in stream_response(
                    fallback_prompt,
                    system=FALLBACK_EXPLAINER_SYSTEM,
                    max_tokens=_ANALYST_EXPLAIN_TOKENS,
                ):
                    parts.append(chunk)
                    content_area.markdown("".join(parts) + " ▮")
                explanation = "".join(parts)
                content_area.markdown(explanation)

            else:
                plan = plan_or_error
                status_area.markdown(f"*Running `{plan.operation}` — {plan.intent}…*")

                # ── Step 3: Execute (pure Python, no LLM code) ───────────────
                result = execute(plan, df)

                if result.error:
                    exec_error = result.error
                    status_area.empty()
                    content_area.error(f"Execution error: {result.error}")
                else:
                    result_df = result.df
                    result_chart = result.chart

                    if result_chart is not None:
                        st.plotly_chart(result_chart, use_container_width=True,
                                        config={"displayModeBar": False})

                    if result_df is not None and not result_df.empty:
                        with st.expander(f"Data table ({len(result_df)} rows)", expanded=False):
                            st.dataframe(result_df, use_container_width=True)

                    # ── Step 4: Explain (streaming, counts toward limit) ──────
                    status_area.empty()
                    explain_prompt = (
                        f"QUESTION: {question}\n\n"
                        f"RESULT:\n{result.summary_text}"
                    )
                    parts = []
                    for chunk in stream_response(
                        explain_prompt,
                        system=EXPLAINER_SYSTEM,
                        max_tokens=_ANALYST_EXPLAIN_TOKENS,
                    ):
                        parts.append(chunk)
                        content_area.markdown("".join(parts) + " ▮")
                    explanation = "".join(parts)
                    content_area.markdown(explanation)

        except (ConfigError, UsageLimitError) as exc:
            status_area.empty()
            content_area.error(str(exc))
            explanation = f"Error: {exc}"
        except RuntimeError as exc:
            status_area.empty()
            content_area.error(str(exc))
            explanation = f"Error: {exc}"
        except Exception as exc:
            status_area.empty()
            content_area.error(f"Unexpected error: {exc}")
            explanation = f"Error: {exc}"

    history.append({
        "role":         "assistant",
        "content":      explanation,
        "result_df":    result_df,
        "result_chart": result_chart,
        "plan_error":   plan_error,
        "error":        exec_error,
    })


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
