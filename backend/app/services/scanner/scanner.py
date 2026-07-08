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


def _rows_from_coingecko(markets: List[dict]) -> List[dict]:
    """Build scanner rows from CoinGecko /coins/markets — used when the Binance
    all-tickers feed is geo-blocked (cloud/US hosts). Same shape as _usdt_pairs."""
    out = []
    for c in markets:
        try:
            price = float(c["current_price"])
            change = float(c.get("price_change_percentage_24h") or 0.0)
            volume = float(c.get("total_volume") or 0.0)
            high = float(c.get("high_24h") or price)
            low = float(c.get("low_24h") or price)
        except (KeyError, TypeError, ValueError):
            continue
        if volume < MIN_VOLUME_USD:
            continue
        rng = high - low
        out.append({
            "symbol": f"{str(c.get('symbol', '')).upper()}USDT",
            "price": price, "change_pct": round(change, 2), "volume_usd": volume,
            "high": high, "low": low, "trades": 0,
            "volatility_pct": round(rng / low * 100, 2) if low > 0 else 0.0,
            "range_position": round((price - low) / rng, 4) if rng > 0 else 0.5,
        })
    return out


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
    # Prefer Binance's full ticker set; fall back to CoinGecko (globally reachable)
    tickers = await get_ticker_24h()
    rows = _usdt_pairs(tickers) if isinstance(tickers, list) else []
    binance_ok = bool(rows)  # whales/liquidations/delistings are Binance-only
    if not rows:
        from app.services.market import coingecko
        markets = await coingecko.get_markets(per_page=250)
        rows = _rows_from_coingecko(markets or [])
    if not rows:
        logger.warning("Scanner: no market data source reachable")
        return None

    by_change = sorted(rows, key=lambda r: r["change_pct"], reverse=True)
    by_volume = sorted(rows, key=lambda r: r["volume_usd"], reverse=True)
    # CoinGecko rows have no trade count → rank "most active" by volume instead
    by_trades = sorted(rows, key=lambda r: r["trades"] or r["volume_usd"], reverse=True)
    by_vol = sorted(rows, key=lambda r: r["volatility_pct"], reverse=True)

    breakouts = [r for r in rows if r["range_position"] >= 0.995 and r["change_pct"] > 3][:20]
    breakdowns = [r for r in rows if r["range_position"] <= 0.005 and r["change_pct"] < -3][:20]

    # whale prints, liquidations and delistings are Binance-only feeds; skip them
    # when Binance is unreachable (CoinGecko fallback) to avoid slow blocked calls
    whales: List[dict] = []
    liquidations: List[dict] = []
    delistings: List[dict] = []
    if binance_ok:
        whales = await fetch_whale_trades([r["symbol"] for r in by_volume])
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
