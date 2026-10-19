import os
import anthropic
from app.utils.logger import get_logger

logger = get_logger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def ask(
    prompt: str,
    system: str = "You are a senior data analyst. Be concise and precise.",
    model: str | None = None,
    max_tokens: int = 2048,
) -> str:
    model = model or os.getenv("DEFAULT_MODEL", "claude-opus-4-5")
    logger.debug("Claude request | model=%s | tokens=%d", model, max_tokens)
    message = _get_client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
