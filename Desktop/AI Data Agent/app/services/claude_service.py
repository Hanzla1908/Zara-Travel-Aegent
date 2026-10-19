"""Claude API service.

Reads ANTHROPIC_API_KEY from the environment (set via .env / system env —
never hard-coded).  Exposes:

  ask()             — single-turn, returns full reply str
  stream_response() — generator yielding text chunks for st.write_stream()
  get_usage()       — session-level call counter
  bump_usage()      — increment counter (called by callers after each request)

Usage limits
------------
  WARN_AT  = 20 calls  — show yellow notice
  BLOCK_AT = 30 calls  — refuse and surface a clear message

The counter lives in a module-level dict keyed by Streamlit session_id so it
resets on each new browser session without touching session_state.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Generator, Sequence

import anthropic

from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_MODEL   = "claude-opus-4-5"
DEFAULT_TOKENS  = 1_024
INSIGHT_TOKENS  = 1_500
WARN_AT         = 20
BLOCK_AT        = 30

# ── Usage tracking (module-level, keyed by session) ──────────────────────────

_usage: dict[str, int] = defaultdict(int)


def _session_key() -> str:
    try:
        import streamlit as st
        return st.runtime.scriptrunner.get_script_run_ctx().session_id  # type: ignore[union-attr]
    except Exception:
        return "default"


def get_usage() -> int:
    return _usage[_session_key()]


def bump_usage() -> None:
    _usage[_session_key()] += 1


# ── Client factory ────────────────────────────────────────────────────────────

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ConfigError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file and restart the app."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


# ── Custom exceptions ─────────────────────────────────────────────────────────

class ConfigError(RuntimeError):
    """Raised when the API key is missing or obviously invalid."""


class UsageLimitError(RuntimeError):
    """Raised when the per-session call limit is reached."""


# ── Public API ────────────────────────────────────────────────────────────────

def ask(
    prompt: str,
    system: str = "You are a senior data analyst. Be concise and precise.",
    model: str | None = None,
    max_tokens: int = DEFAULT_TOKENS,
    history: list[dict] | None = None,
) -> str:
    """Non-streaming single request.  Returns the full reply text.

    Parameters
    ----------
    history: Optional prior turns as [{role, content}, ...] excluding the
             latest user message (which is `prompt`).
    """
    _check_limit()
    client = _get_client()
    model = model or os.getenv("DEFAULT_MODEL", DEFAULT_MODEL)

    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": prompt})

    logger.debug("Claude ask | model=%s | turns=%d | max_tokens=%d", model, len(messages), max_tokens)
    t0 = time.monotonic()
    try:
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        bump_usage()
        elapsed = time.monotonic() - t0
        logger.debug("Claude ask | ok | %.1fs | usage=%d", elapsed, get_usage())
        return msg.content[0].text
    except anthropic.AuthenticationError as exc:
        raise ConfigError("Invalid API key. Check ANTHROPIC_API_KEY in your .env.") from exc
    except anthropic.RateLimitError as exc:
        raise RuntimeError("Anthropic rate limit reached. Wait a moment and try again.") from exc
    except anthropic.APIStatusError as exc:
        raise RuntimeError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise RuntimeError("Cannot reach Anthropic API. Check your internet connection.") from exc


def stream_response(
    prompt: str,
    system: str = "You are a senior data analyst. Be concise and precise.",
    model: str | None = None,
    max_tokens: int = DEFAULT_TOKENS,
    history: list[dict] | None = None,
) -> Generator[str, None, None]:
    """Streaming generator — pass directly to st.write_stream().

    Yields text chunks as they arrive from the API.  Bumps the usage counter
    once the stream is fully consumed.
    """
    _check_limit()
    client = _get_client()
    model = model or os.getenv("DEFAULT_MODEL", DEFAULT_MODEL)

    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": prompt})

    logger.debug("Claude stream | model=%s | turns=%d", model, len(messages))
    try:
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        ) as stream:
            for chunk in stream.text_stream:
                yield chunk
        bump_usage()
        logger.debug("Claude stream | done | usage=%d", get_usage())
    except anthropic.AuthenticationError as exc:
        raise ConfigError("Invalid API key. Check ANTHROPIC_API_KEY in your .env.") from exc
    except anthropic.RateLimitError as exc:
        raise RuntimeError("Anthropic rate limit reached. Wait a moment and try again.") from exc
    except anthropic.APIStatusError as exc:
        raise RuntimeError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise RuntimeError("Cannot reach Anthropic API. Check your internet connection.") from exc


# ── Internal helpers ──────────────────────────────────────────────────────────

def _check_limit() -> None:
    n = get_usage()
    if n >= BLOCK_AT:
        raise UsageLimitError(
            f"Session API limit reached ({BLOCK_AT} calls). "
            "Refresh the page to start a new session."
        )
