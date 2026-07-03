"""Binance public REST API — klines, tickers, order book, funding, open
interest, liquidity/spread. Public endpoints need no key. Signed endpoints
(account, orders) are used only by the live-trading executor."""
import hashlib
import hmac
import time
from typing import List, Optional
from urllib.parse import urlencode

from app.core.config import settings
from app.services.market.http import cached_get_json, get_http

SPOT = settings.BINANCE_BASE_URL
FUTURES = "https://fapi.binance.com"

INTERVALS = {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}


async def get_klines(symbol: str, interval: str = "1h", limit: int = 500) -> Optional[List[list]]:
    """OHLCV candles: [open_time, open, high, low, close, volume, close_time, ...]"""
    if interval not in INTERVALS:
        interval = "1h"
    return await cached_get_json(
        f"{SPOT}/api/v3/klines",
        params={"symbol": symbol.upper(), "interval": interval, "limit": min(limit, 1000)},
        cache_key=f"bn:klines:{symbol.upper()}:{interval}:{limit}", ttl=30)


async def get_ticker_24h(symbol: Optional[str] = None) -> Optional[dict | list]:
    params = {"symbol": symbol.upper()} if symbol else None
    return await cached_get_json(f"{SPOT}/api/v3/ticker/24hr", params=params,
                                 cache_key=f"bn:ticker24:{symbol or 'ALL'}", ttl=30)


async def get_order_book(symbol: str, limit: int = 50) -> Optional[dict]:
    return await cached_get_json(f"{SPOT}/api/v3/depth",
                                 params={"symbol": symbol.upper(), "limit": limit},
                                 cache_key=f"bn:depth:{symbol.upper()}:{limit}", ttl=5)


async def get_price(symbol: str) -> Optional[float]:
    data = await cached_get_json(f"{SPOT}/api/v3/ticker/price",
                                 params={"symbol": symbol.upper()},
                                 cache_key=f"bn:price:{symbol.upper()}", ttl=5)
    try:
        return float(data["price"]) if data else None
    except (KeyError, TypeError, ValueError):
        return None


async def get_funding_rate(symbol: str) -> Optional[dict]:
    """Latest funding rate + mark price from USD-M futures."""
    return await cached_get_json(f"{FUTURES}/fapi/v1/premiumIndex",
                                 params={"symbol": symbol.upper()},
                                 cache_key=f"bn:funding:{symbol.upper()}", ttl=60)


async def get_open_interest(symbol: str) -> Optional[dict]:
    return await cached_get_json(f"{FUTURES}/fapi/v1/openInterest",
                                 params={"symbol": symbol.upper()},
                                 cache_key=f"bn:oi:{symbol.upper()}", ttl=60)


async def get_liquidity_metrics(symbol: str) -> Optional[dict]:
    """Spread and near-book liquidity derived from the order book."""
    book = await get_order_book(symbol, limit=50)
    if not book or not book.get("bids") or not book.get("asks"):
        return None
    best_bid = float(book["bids"][0][0])
    best_ask = float(book["asks"][0][0])
    mid = (best_bid + best_ask) / 2
    bid_liquidity = sum(float(p) * float(q) for p, q in book["bids"])
    ask_liquidity = sum(float(p) * float(q) for p, q in book["asks"])
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": round(best_ask - best_bid, 10),
        "spread_pct": round((best_ask - best_bid) / mid * 100, 6) if mid else None,
        "bid_liquidity_usd": round(bid_liquidity, 2),
        "ask_liquidity_usd": round(ask_liquidity, 2),
        "imbalance": round((bid_liquidity - ask_liquidity) / (bid_liquidity + ask_liquidity), 4)
        if (bid_liquidity + ask_liquidity) else None,
    }


# --------------------------------------------------------- signed endpoints

def _sign(params: dict, secret: str) -> str:
    query = urlencode(params)
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


async def signed_request(method: str, path: str, api_key: str, api_secret: str,
                         params: Optional[dict] = None, testnet: bool = True) -> dict:
    """Signed spot request used by the live executor. Raises httpx.HTTPStatusError
    on rejection so callers can log exchange errors verbatim."""
    base = settings.BINANCE_TESTNET_BASE_URL if testnet else SPOT
    params = dict(params or {})
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 5000
    params["signature"] = _sign(params, api_secret)
    headers = {"X-MBX-APIKEY": api_key}
    client = get_http()
    resp = await client.request(method, f"{base}{path}", params=params, headers=headers)
    resp.raise_for_status()
    return resp.json()


def klines_to_ohlcv(klines: List[list]) -> dict:
    """Convert raw kline rows to column arrays for the indicator engine."""
    return {
        "time": [int(k[0]) // 1000 for k in klines],
        "open": [float(k[1]) for k in klines],
        "high": [float(k[2]) for k in klines],
        "low": [float(k[3]) for k in klines],
        "close": [float(k[4]) for k in klines],
        "volume": [float(k[5]) for k in klines],
    }
