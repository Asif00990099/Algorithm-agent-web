"""LLM provider abstraction: OpenAI, Anthropic (Claude) and any local
OpenAI-compatible server (Ollama, vLLM, LM Studio).

The platform is fully functional without an LLM (quant-only mode); when a
provider is configured it enhances signal rationale, news rewriting and
sentiment refinement."""
import logging
from typing import Optional

from app.core.config import settings
from app.services.market.http import get_http

logger = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    pass


async def _openai_compatible(base_url: str, api_key: str, model: str,
                             system: str, user: str, max_tokens: int) -> str:
    resp = await get_http().post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key or 'ollama'}"},
        json={"model": model, "max_tokens": max_tokens,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user}]},
        timeout=120.0)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


async def _anthropic(system: str, user: str, max_tokens: int) -> str:
    resp = await get_http().post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": settings.ANTHROPIC_API_KEY,
                 "anthropic-version": "2023-06-01"},
        json={"model": settings.ANTHROPIC_MODEL, "max_tokens": max_tokens,
              "system": system,
              "messages": [{"role": "user", "content": user}]},
        timeout=120.0)
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def llm_available() -> bool:
    p = settings.AI_PROVIDER
    return ((p == "openai" and bool(settings.OPENAI_API_KEY))
            or (p == "anthropic" and bool(settings.ANTHROPIC_API_KEY))
            or p == "local")


async def complete(system: str, user: str, max_tokens: int = 1024) -> str:
    """Run a completion against the configured provider. Raises LLMUnavailable
    when no provider is configured or the call fails — callers must degrade
    gracefully, never fabricate output."""
    provider = settings.AI_PROVIDER
    try:
        if provider == "openai" and settings.OPENAI_API_KEY:
            return await _openai_compatible("https://api.openai.com/v1",
                                            settings.OPENAI_API_KEY,
                                            settings.OPENAI_MODEL, system, user, max_tokens)
        if provider == "anthropic" and settings.ANTHROPIC_API_KEY:
            return await _anthropic(system, user, max_tokens)
        if provider == "local":
            return await _openai_compatible(settings.LOCAL_LLM_BASE_URL, "",
                                            settings.LOCAL_LLM_MODEL, system, user, max_tokens)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM call failed (%s): %s", provider, exc)
        raise LLMUnavailable(str(exc)) from exc
    raise LLMUnavailable(f"No LLM provider configured (AI_PROVIDER={provider})")


async def try_complete(system: str, user: str, max_tokens: int = 1024) -> Optional[str]:
    try:
        return await complete(system, user, max_tokens)
    except LLMUnavailable:
        return None
