"""Coinbase Exchange public market data.

Coinbase is a US company whose public market-data API is reliably reachable from
US/cloud hosts (Hugging Face, AWS, etc.) where Binance is geo-blocked. Used as a
candle/price fallback. Data is normalized to the Binance shapes the app expects.
No API key required. Coinbase quotes in USD (BTC-USD), which tracks USDT closely.
"""
from typing import List, Optional

from app.services.market.http import cached_get_json

BASE = "https://api.exchange.coinbase.com"

# app interval -> Coinbase granularity (seconds). Coinbase supports only
# 60/300/900/3600/21600/86400, so 30m→15m, 4h→6h, 1w→1d are approximated.
_GRAN = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 900, "1h": 3600,
    "4h": 21600, "1d": 86400, "1w": 86400,
}
_QUOTES = ("USDT", "USDC", "BUSD", "USD", "EUR", "BTC", "ETH")


def _product(symbol: str) -> str:
    """BTCUSDT -> BTC-USD (Coinbase uses USD quote products)."""
    s = symbol.upper()
    for q in _QUOTES:
        if s.endswith(q) and len(s) > len(q):
            return f"{s[:-len(q)]}-USD"
    return f"{s}-USD"


async def get_klines(symbol: str, interval: str = "1h", limit: int = 500) -> Optional[List[list]]:
    """Return candles in Binance kline row format (oldest first). Coinbase caps
    at ~300 candles per request, which is enough for the indicator engine."""
    gran = _GRAN.get(interval, 3600)
    product = _product(symbol)
    data = await cached_get_json(f"{BASE}/products/{product}/candles",
                                 params={"granularity": gran},
                                 cache_key=f"cb:kl:{product}:{gran}", ttl=30)
    if not isinstance(data, list) or not data:
        return None
    # Coinbase row: [time_s, low, high, open, close, volume], newest first
    rows: List[list] = []
    for c in reversed(data):
        try:
            t_ms = int(c[0]) * 1000
            rows.append([t_ms, str(c[3]), str(c[2]), str(c[1]), str(c[4]),
                         str(c[5]), t_ms, "0", 0, 0, 0, 0])
        except (IndexError, ValueError, TypeError):
            continue
    return rows[-limit:] or None


async def get_price(symbol: str) -> Optional[float]:
    product = _product(symbol)
    data = await cached_get_json(f"{BASE}/products/{product}/ticker",
                                 cache_key=f"cb:price:{product}", ttl=10)
    try:
        return float(data["price"]) if data and data.get("price") else None
    except (KeyError, TypeError, ValueError):
        return None
