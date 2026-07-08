"""In-process background scheduler.

For single-service deployments (Hugging Face, one Render/Railway service) there
is no separate Celery worker/beat and often no Redis. This scheduler runs the
same periodic jobs directly inside the FastAPI event loop using asyncio, so
signals, news, the market scanner, sentiment and the economic calendar keep
updating with nothing but the one web service + a database.

Enable with settings.RUN_BACKGROUND_JOBS (default True). Disable it when running
dedicated Celery workers so jobs don't run twice.
"""
from __future__ import annotations

import asyncio
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_tasks: list[asyncio.Task] = []


async def _run_once(coro_fn, name: str) -> None:
    try:
        result = await coro_fn()
        logger.info("[scheduler] %s: %s", name, result)
    except Exception as exc:  # noqa: BLE001 - one job failing must not kill the loop
        logger.warning("[scheduler] %s failed: %s", name, exc)


async def _loop(coro_fn, name: str, interval: int, initial_delay: int) -> None:
    await asyncio.sleep(initial_delay)
    while True:
        await _run_once(coro_fn, name)
        await asyncio.sleep(max(interval, 15))


def start() -> None:
    """Launch every periodic job as a background asyncio task. Jobs are staggered
    so they don't all fire at once on a small free instance."""
    if _tasks:
        return
    from app.workers import tasks as t

    # (coroutine, name, interval_seconds, initial_delay_seconds)
    jobs = [
        (t._market_sync, "market_sync", settings.MARKET_SYNC_INTERVAL, 5),
        (t._scanner_cycle, "scanner", settings.SCANNER_INTERVAL, 12),
        (t._trade_monitor, "trade_monitor", settings.TRADE_MONITOR_INTERVAL, 20),
        (t._signal_cycle, "signals", settings.SIGNAL_INTERVAL, 25),
        (t._calendar_sync, "calendar", settings.CALENDAR_INTERVAL, 35),
        (t._news_cycle, "news", settings.NEWS_INTERVAL, 45),
        (t._sentiment_cycle, "sentiment", settings.SENTIMENT_INTERVAL, 70),
        (t._evaluate_signals, "evaluate_signals", 3600, 300),
        (t._publish_scheduled, "publish_scheduled", 300, 120),
    ]
    for coro_fn, name, interval, delay in jobs:
        _tasks.append(asyncio.create_task(_loop(coro_fn, name, interval, delay)))
    logger.info("In-process scheduler started (%d jobs)", len(_tasks))


async def stop() -> None:
    for task in _tasks:
        task.cancel()
    _tasks.clear()
