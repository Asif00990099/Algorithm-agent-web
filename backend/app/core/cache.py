"""Redis helpers: JSON cache with TTL, pub/sub for realtime fan-out and a
sliding-window rate limiter. All functions degrade gracefully when Redis is
unavailable (cache misses, no-op limits) so the API stays up."""
import json
import logging
import time
from typing import Any, Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _pool


async def cache_get(key: str) -> Optional[Any]:
    if not settings.redis_enabled:
        return None
    try:
        raw = await get_redis().get(key)
        return json.loads(raw) if raw is not None else None
    except Exception:  # noqa: BLE001 - redis down must not break requests
        return None


async def cache_set(key: str, value: Any, ttl: int = 60) -> None:
    if not settings.redis_enabled:
        return
    try:
        await get_redis().set(key, json.dumps(value, default=str), ex=ttl)
    except Exception:  # noqa: BLE001
        logger.debug("cache_set failed for %s", key)


async def publish(channel: str, message: Any) -> None:
    if not settings.redis_enabled:
        return
    try:
        await get_redis().publish(channel, json.dumps(message, default=str))
    except Exception:  # noqa: BLE001
        logger.debug("publish failed for %s", channel)


async def rate_limit_check(identifier: str, limit: int, window_seconds: int = 60) -> bool:
    """Sliding-window rate limiter. Returns True when the request is allowed."""
    if not settings.redis_enabled:
        return True  # no redis → no distributed limiting (single-instance free tier)
    try:
        r = get_redis()
        now = time.time()
        key = f"ratelimit:{identifier}"
        async with r.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, now - window_seconds)
            pipe.zadd(key, {f"{now}": now})
            pipe.zcard(key)
            pipe.expire(key, window_seconds)
            results = await pipe.execute()
        return int(results[2]) <= limit
    except Exception:  # noqa: BLE001
        return True  # fail-open: don't take the API down with Redis
