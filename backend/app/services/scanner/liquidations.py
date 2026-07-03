"""Futures liquidation collector.

Samples the Binance USD-M force-order stream (`!forceOrder@arr`) for a few
seconds each scanner cycle and appends events to a capped Redis list, giving
the platform a rolling window of real liquidations with zero API keys.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import List

import websockets

from app.core.cache import get_redis, publish

logger = logging.getLogger(__name__)

STREAM = "wss://fstream.binance.com/ws/!forceOrder@arr"
REDIS_KEY = "scanner:liquidations"
MAX_STORED = 200


async def sample_liquidations(duration_seconds: float = 8.0) -> List[dict]:
    """Listen to the liquidation stream for `duration_seconds`, store and
    return normalized events (newest first)."""
    events: List[dict] = []
    try:
        async with websockets.connect(STREAM, ping_interval=None, open_timeout=6) as ws:
            loop = asyncio.get_event_loop()
            deadline = loop.time() + duration_seconds
            while loop.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=max(0.2, deadline - loop.time()))
                except asyncio.TimeoutError:
                    break
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                order = msg.get("o", {})
                try:
                    price = float(order.get("ap") or order.get("p") or 0)
                    qty = float(order.get("q") or 0)
                except (TypeError, ValueError):
                    continue
                if price <= 0 or qty <= 0:
                    continue
                events.append({
                    "symbol": order.get("s"),
                    # SELL force order = a long got liquidated, and vice versa
                    "side_liquidated": "long" if order.get("S") == "SELL" else "short",
                    "price": price,
                    "quantity": qty,
                    "notional_usd": round(price * qty, 2),
                    "time": order.get("T"),
                })
    except Exception as exc:  # noqa: BLE001 - stream may be geo-blocked/unreachable
        logger.warning("Liquidation stream unavailable: %s", exc)

    if events:
        try:
            r = get_redis()
            await r.lpush(REDIS_KEY, *[json.dumps(e) for e in events])
            await r.ltrim(REDIS_KEY, 0, MAX_STORED - 1)
            await r.expire(REDIS_KEY, 86400)
        except Exception:  # noqa: BLE001
            logger.debug("Could not persist liquidations to redis")
        big = [e for e in events if e["notional_usd"] >= 100_000]
        if big:
            await publish("scanner", {"type": "liquidations", "events": big[:10]})
    return sorted(events, key=lambda e: e["notional_usd"], reverse=True)


async def get_recent_liquidations(limit: int = 50) -> List[dict]:
    try:
        raw = await get_redis().lrange(REDIS_KEY, 0, limit - 1)
        return [json.loads(x) for x in raw]
    except Exception:  # noqa: BLE001
        return []
