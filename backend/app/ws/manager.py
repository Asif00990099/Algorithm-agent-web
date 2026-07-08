"""WebSocket fan-out.

Clients connect to /ws/stream and subscribe to topics:
  {"op": "subscribe", "topics": ["prices:BTCUSDT", "scanner", "signals", "news"]}

Price topics are fed by a single upstream Binance WebSocket (miniTicker
stream) shared across all clients; platform topics (signals, news, scanner,
trades) are fed by Redis pub/sub messages published by the workers.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import defaultdict
from typing import Dict, Set

import websockets
from fastapi import WebSocket

from app.core.cache import get_redis
from app.core.config import settings

logger = logging.getLogger(__name__)

BINANCE_WS = "wss://stream.binance.com:9443/ws/!miniTicker@arr"
PLATFORM_CHANNELS = ("signals", "news", "scanner", "trades", "alerts")


class ConnectionManager:
    def __init__(self) -> None:
        self.topic_subscribers: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.client_topics: Dict[WebSocket, Set[str]] = defaultdict(set)
        self._binance_task: asyncio.Task | None = None
        self._redis_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            if self._binance_task is None or self._binance_task.done():
                self._binance_task = asyncio.create_task(self._binance_pump())
            # platform events flow through Redis pub/sub; skip when Redis is off
            if settings.redis_enabled and (self._redis_task is None or self._redis_task.done()):
                self._redis_task = asyncio.create_task(self._redis_pump())

    def subscribe(self, ws: WebSocket, topics: list[str]) -> list[str]:
        accepted = []
        for topic in topics[:50]:
            if topic in PLATFORM_CHANNELS or (topic.startswith("prices:") and len(topic) < 30):
                self.topic_subscribers[topic].add(ws)
                self.client_topics[ws].add(topic)
                accepted.append(topic)
        return accepted

    def unsubscribe(self, ws: WebSocket, topics: list[str]) -> None:
        for topic in topics:
            self.topic_subscribers.get(topic, set()).discard(ws)
            self.client_topics.get(ws, set()).discard(topic)

    def disconnect(self, ws: WebSocket) -> None:
        for topic in self.client_topics.pop(ws, set()):
            self.topic_subscribers.get(topic, set()).discard(ws)

    async def broadcast(self, topic: str, payload: dict) -> None:
        dead = []
        message = json.dumps({"topic": topic, "data": payload}, default=str)
        for ws in list(self.topic_subscribers.get(topic, ())):
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    # ------------------------------------------------------------- pumps

    async def _binance_pump(self) -> None:
        """Relay Binance mini-tickers to any `prices:SYMBOL` subscribers."""
        while True:
            try:
                async with websockets.connect(BINANCE_WS, ping_interval=20) as upstream:
                    logger.info("Connected to Binance ticker stream")
                    async for raw in upstream:
                        try:
                            tickers = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        for tk in tickers:
                            topic = f"prices:{tk.get('s', '')}"
                            if topic in self.topic_subscribers and self.topic_subscribers[topic]:
                                await self.broadcast(topic, {
                                    "symbol": tk.get("s"),
                                    "price": tk.get("c"),
                                    "open": tk.get("o"),
                                    "high": tk.get("h"),
                                    "low": tk.get("l"),
                                    "volume": tk.get("v"),
                                    "quote_volume": tk.get("q"),
                                    "time": tk.get("E"),
                                })
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("Binance stream dropped (%s); reconnecting in 5s", exc)
                await asyncio.sleep(5)

    async def _redis_pump(self) -> None:
        """Relay worker events (signals/news/scanner/trades) to subscribers."""
        while True:
            try:
                pubsub = get_redis().pubsub()
                await pubsub.subscribe(*PLATFORM_CHANNELS)
                async for msg in pubsub.listen():
                    if msg.get("type") != "message":
                        continue
                    channel = msg["channel"]
                    with contextlib.suppress(json.JSONDecodeError, TypeError):
                        await self.broadcast(channel, json.loads(msg["data"]))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis pubsub dropped (%s); reconnecting in 5s", exc)
                await asyncio.sleep(5)


manager = ConnectionManager()
