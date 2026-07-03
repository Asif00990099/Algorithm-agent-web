"""Market scanner — runs every minute over the full Binance 24h ticker set.

Produces: top gainers/losers, most active, highest volume, highest volatility,
breakouts/breakdowns (vs 24h range), new listings, and large whale prints
sampled from recent aggregate trades on the most active pairs. Results are
cached in Redis for instant API/WebSocket reads.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from app.core.cache import cache_set, publish
from app.services.market.binance import SPOT, get_ticker_24h
from app.services.market.coingecko import get_new_listings
from app.services.market.http import cached_get_json
from app.services.scanner.liquidations import get_recent_liquidations, sample_liquidations

logger = logging.getLogger(__name__)

QUOTE = "USDT"
MIN_VOLUME_USD = 1_000_000       # ignore illiquid pairs
WHALE_TRADE_USD = 250_000        # single print considered whale-sized


def _usdt_pairs(tickers: List[dict]) -> List[dict]:
    out = []
    for tk in tickers:
        sym = tk.get("symbol", "")
        if not sym.endswith(QUOTE) or any(x in sym for x in ("UP", "DOWN", "BULL", "BEAR")):
            continue
        try:
            row = {
                "symbol": sym,
                "price": float(tk["lastPrice"]),
                "change_pct": float(tk["priceChangePercent"]),
                "volume_usd": float(tk["quoteVolume"]),
                "high": float(tk["highPrice"]),
                "low": float(tk["lowPrice"]),
                "trades": int(tk["count"]),
            }
        except (KeyError, ValueError):
            continue
        if row["volume_usd"] >= MIN_VOLUME_USD:
            row["volatility_pct"] = round((row["high"] - row["low"]) / row["low"] * 100, 2) \
                if row["low"] > 0 else 0.0
            # breakout: closing within 0.5% of 24h high; breakdown: near low
            rng = row["high"] - row["low"]
            row["range_position"] = round((row["price"] - row["low"]) / rng, 4) if rng > 0 else 0.5
            out.append(row)
    return out


async def fetch_whale_trades(symbols: List[str], limit: int = 60) -> List[dict]:
    whales = []
    for sym in symbols[:8]:  # keep request volume polite
        trades = await cached_get_json(f"{SPOT}/api/v3/aggTrades",
                                       params={"symbol": sym, "limit": limit},
                                       cache_key=f"bn:aggtrades:{sym}", ttl=60)
        if not trades:
            continue
        for tr in trades:
            try:
                notional = float(tr["p"]) * float(tr["q"])
            except (KeyError, ValueError):
                continue
            if notional >= WHALE_TRADE_USD:
                whales.append({"symbol": sym, "price": float(tr["p"]),
                               "quantity": float(tr["q"]),
                               "notional_usd": round(notional, 0),
                               "side": "sell" if tr.get("m") else "buy",
                               "time": tr.get("T")})
    whales.sort(key=lambda w: w["notional_usd"], reverse=True)
    return whales[:50]


async def fetch_delistings() -> List[dict]:
    """Symbols whose trading status is no longer TRADING on Binance spot
    (BREAK/HALT/END_OF_DAY) — the exchange's delisting/halt signal."""
    info = await cached_get_json(f"{SPOT}/api/v3/exchangeInfo",
                                 params={"permissions": "SPOT"},
                                 cache_key="bn:exchangeInfo", ttl=1800)
    if not info:
        return []
    out = []
    for sym in info.get("symbols", []):
        status = sym.get("status")
        if status and status != "TRADING" and sym.get("quoteAsset") == QUOTE:
            out.append({"symbol": sym.get("symbol"), "status": status,
                        "base_asset": sym.get("baseAsset")})
    return out[:50]


async def run_scan() -> Optional[dict]:
    tickers = await get_ticker_24h()
    if not isinstance(tickers, list):
        logger.warning("Scanner: ticker feed unavailable")
        return None
    rows = _usdt_pairs(tickers)
    if not rows:
        return None

    by_change = sorted(rows, key=lambda r: r["change_pct"], reverse=True)
    by_volume = sorted(rows, key=lambda r: r["volume_usd"], reverse=True)
    by_trades = sorted(rows, key=lambda r: r["trades"], reverse=True)
    by_vol = sorted(rows, key=lambda r: r["volatility_pct"], reverse=True)

    breakouts = [r for r in rows if r["range_position"] >= 0.995 and r["change_pct"] > 3][:20]
    breakdowns = [r for r in rows if r["range_position"] <= 0.005 and r["change_pct"] < -3][:20]

    whales = await fetch_whale_trades([r["symbol"] for r in by_volume])

    # liquidations: sample the futures force-order stream this cycle, then
    # merge with the rolling window already stored in Redis
    fresh_liqs = await sample_liquidations(duration_seconds=6.0)
    liquidations = fresh_liqs or await get_recent_liquidations(50)

    delistings = await fetch_delistings()

    new_listings = await get_new_listings()
    listings = [{"id": c.get("id"), "symbol": c.get("symbol"), "name": c.get("name"),
                 "activated_at": c.get("activated_at")}
                for c in (new_listings or [])[:20]] if isinstance(new_listings, list) else []

    result = {
        "gainers": by_change[:20],
        "losers": by_change[-20:][::-1],
        "most_active": by_trades[:20],
        "highest_volume": by_volume[:20],
        "highest_volatility": by_vol[:20],
        "breakouts": breakouts,
        "breakdowns": breakdowns,
        "whale_trades": whales,
        "liquidations": liquidations[:50],
        "new_listings": listings,
        "delistings": delistings,
        "pairs_scanned": len(rows),
    }
    await cache_set("scanner:latest", result, ttl=180)
    await publish("scanner", {"type": "scanner_update", "pairs_scanned": len(rows)})
    return result
