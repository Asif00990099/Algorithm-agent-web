"""Shared async HTTP client with Redis caching for external market APIs."""
import logging
from typing import Any, Optional

import httpx

from app.core.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None


def get_http() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(15.0), follow_redirects=True,
                                    headers={"User-Agent": "QuantPulse/1.0"})
    return _client


async def close_http() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def cached_get_json(url: str, *, params: Optional[dict] = None,
                          headers: Optional[dict] = None, cache_key: Optional[str] = None,
                          ttl: int = 60) -> Optional[Any]:
    """GET JSON with a Redis cache in front. Returns None on upstream failure —
    callers surface empty/unavailable states, never fabricated data."""
    key = cache_key or f"http:{url}:{sorted((params or {}).items())}"
    cached = await cache_get(key)
    if cached is not None:
        return cached
    try:
        resp = await get_http().get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        await cache_set(key, data, ttl=ttl)
        return data
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Upstream request failed %s: %s", url, exc)
        return None
