"""Public market data API: coins, charts, indicators, order book, funding,
open interest, fear & greed, macro series, stocks and forex."""
from fastapi import APIRouter, HTTPException, Query, status

from app.core.cache import cache_get
from app.services.indicators.ta import compute_snapshot
from app.services.market import binance, coingecko, macro

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/overview")
async def market_overview():
    """Global stats + top coins + fear/greed in one call for the homepage."""
    global_data = await coingecko.get_global()
    top = await coingecko.get_markets(per_page=20)
    fng = await macro.get_fear_greed(1)
    trending = await coingecko.get_trending()
    return {
        "global": (global_data or {}).get("data"),
        "top_coins": top or [],
        "fear_greed": (fng or [None])[0],
        "trending": (trending or {}).get("coins", [])[:7],
    }


@router.get("/coins")
async def coins(page: int = Query(1, ge=1, le=20), per_page: int = Query(100, ge=1, le=250),
                vs_currency: str = "usd"):
    data = await coingecko.get_markets(vs_currency=vs_currency, page=page, per_page=per_page)
    if data is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Market data source unavailable")
    return data


@router.get("/coins/{coin_id}")
async def coin_detail(coin_id: str):
    data = await coingecko.get_coin_detail(coin_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Coin not found or source unavailable")
    return data


@router.get("/coins/{coin_id}/chart")
async def coin_chart(coin_id: str, days: int = Query(30, ge=1, le=365)):
    data = await coingecko.get_market_chart(coin_id, days=days)
    if data is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Chart data unavailable")
    return data


@router.get("/search")
async def search(q: str = Query(min_length=1, max_length=64)):
    data = await coingecko.search(q)
    return data or {"coins": []}


@router.get("/klines/{symbol}")
async def klines(symbol: str, interval: str = "1h", limit: int = Query(300, ge=10, le=1000)):
    data = await binance.get_klines(symbol, interval, limit)
    if not data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No candles for {symbol}")
    return binance.klines_to_ohlcv(data)


@router.get("/indicators/{symbol}")
async def indicators(symbol: str, interval: str = "1h", limit: int = Query(300, ge=60, le=1000)):
    data = await binance.get_klines(symbol, interval, limit)
    if not data or len(data) < 60:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Not enough candle data for {symbol}")
    ohlcv = binance.klines_to_ohlcv(data)
    snap = compute_snapshot(ohlcv["high"], ohlcv["low"], ohlcv["close"], ohlcv["volume"])
    return {"symbol": symbol.upper(), "interval": interval, **snap.to_dict()}


@router.get("/ticker/{symbol}")
async def ticker(symbol: str):
    data = await binance.get_ticker_24h(symbol)
    if not data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No ticker for {symbol}")
    return data


@router.get("/orderbook/{symbol}")
async def orderbook(symbol: str, limit: int = Query(50, ge=5, le=500)):
    data = await binance.get_order_book(symbol, limit)
    if not data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No order book for {symbol}")
    liquidity = await binance.get_liquidity_metrics(symbol)
    return {"book": data, "liquidity": liquidity}


@router.get("/derivatives/{symbol}")
async def derivatives(symbol: str):
    funding = await binance.get_funding_rate(symbol)
    oi = await binance.get_open_interest(symbol)
    return {"funding": funding, "open_interest": oi}


@router.get("/fear-greed")
async def fear_greed(limit: int = Query(30, ge=1, le=365)):
    data = await macro.get_fear_greed(limit)
    if data is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Fear & Greed source unavailable")
    return data


@router.get("/macro")
async def macro_dashboard():
    data = await macro.get_macro_dashboard()
    return {"series": data,
            "note": None if data else "Set FRED_API_KEY to enable macro data (free at fred.stlouisfed.org)"}


@router.get("/stocks/{symbol}")
async def stock_quote(symbol: str):
    quote = await macro.finnhub_quote(symbol)
    profile = await macro.finnhub_profile(symbol)
    daily = await macro.alpha_vantage_daily(symbol)
    if not any([quote, profile, daily]):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Set FINNHUB_API_KEY / ALPHA_VANTAGE_API_KEY to enable stock data")
    return {"quote": quote, "profile": profile, "daily": daily}


@router.get("/forex/{pair}")
async def forex(pair: str):
    """pair like EURUSD"""
    if len(pair) != 6:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pair must be 6 letters, e.g. EURUSD")
    data = await macro.alpha_vantage_fx(pair[:3], pair[3:])
    if data is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Set ALPHA_VANTAGE_API_KEY to enable forex data")
    return data


@router.get("/scanner")
async def scanner_results():
    data = await cache_get("scanner:latest")
    if data is None:
        # first call before the worker has run — scan synchronously once
        from app.services.scanner.scanner import run_scan
        data = await run_scan()
    if data is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Scanner data unavailable")
    return data
