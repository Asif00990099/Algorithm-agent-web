"""CryptoCompare market data — a globally accessible OHLCV/price source.

Binance's REST API (including data-api.binance.vision) is geo-blocked from many
cloud/US data centers (Hugging Face, some Render/Railway regions). CryptoCompare
is reachable from those hosts, so it's used as the fallback candle/price source.
Everything is normalized to the Binance shapes the rest of the app expects.
Free tier, no key required (a key just raises rate limits).
"""
from typing import List, Optional

from app.core.config import settings
from app.services.market.http import cached_get_json

BASE = "https://min-api.cryptocompare.com/data"

# app interval -> (endpoint, aggregate multiplier)
_INTERVAL = {
    "1m": ("histominute", 1), "5m": ("histominute", 5), "15m": ("histominute", 15),
    "30m": ("histominute", 30), "1h": ("histohour", 1), "4h": ("histohour", 4),
    "1d": ("histoday", 1), "1w": ("histoday", 7),
}

_QUOTES = ("USDT", "USDC", "BUSD", "USD", "EUR", "BTC", "ETH")


def split_symbol(symbol: str) -> tuple[str, str]:
    """BTCUSDT -> (BTC, USDT). Falls back to USDT quote."""
    s = symbol.upper()
    for q in _QUOTES:
        if s.endswith(q) and len(s) > len(q):
            return s[: -len(q)], q
    return s, "USDT"


def _headers() -> dict:
    key = settings.CRYPTOCOMPARE_API_KEY
    return {"authorization": f"Apikey {key}"} if key else {}


async def get_klines(symbol: str, interval: str = "1h", limit: int = 500) -> Optional[List[list]]:
    """Return candles in Binance kline row format (oldest first)."""
    endpoint, aggregate = _INTERVAL.get(interval, ("histohour", 1))
    fsym, tsym = split_symbol(symbol)
    data = await cached_get_json(
        f"{BASE}/v2/{endpoint}",
        params={"fsym": fsym, "tsym": tsym, "limit": min(limit, 2000), "aggregate": aggregate},
        headers=_headers(),
        cache_key=f"cc:kl:{symbol.upper()}:{interval}:{limit}", ttl=30)
    if not data or data.get("Response") == "Error":
        return None
    rows = ((data.get("Data") or {}).get("Data")) or []
    out: List[list] = []
    for c in rows:
        o, h, low, cl = c.get("open", 0), c.get("high", 0), c.get("low", 0), c.get("close", 0)
        if o == 0 and cl == 0:  # skip padding candles before listing
            continue
        t_ms = int(c["time"]) * 1000
        out.append([t_ms, str(o), str(h), str(low), str(cl),
                    str(c.get("volumefrom", 0)), t_ms, str(c.get("volumeto", 0)), 0, 0, 0, 0])
    return out or None


async def get_price(symbol: str) -> Optional[float]:
    fsym, tsym = split_symbol(symbol)
    data = await cached_get_json(f"{BASE}/price",
                                 params={"fsym": fsym, "tsyms": tsym},
                                 headers=_headers(),
                                 cache_key=f"cc:price:{symbol.upper()}", ttl=15)
    try:
        return float(data[tsym]) if data and tsym in data else None
    except (KeyError, TypeError, ValueError):
        return None
