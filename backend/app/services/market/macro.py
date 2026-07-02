"""Macro & sentiment context: Fear/Greed index, FRED economic series,
stock/forex quotes via Finnhub, Alpha Vantage and FMP free tiers."""
from typing import List, Optional

from app.core.config import settings
from app.services.market.http import cached_get_json


# ------------------------------------------------- Alternative.me Fear&Greed

async def get_fear_greed(limit: int = 30) -> Optional[List[dict]]:
    data = await cached_get_json("https://api.alternative.me/fng/",
                                 params={"limit": limit, "format": "json"},
                                 cache_key=f"fng:{limit}", ttl=3600)
    return data.get("data") if data else None


# ---------------------------------------------------------------------- FRED

FRED_SERIES = {
    "CPIAUCSL": "CPI (Consumer Price Index)",
    "PPIACO": "PPI (Producer Price Index)",
    "PAYEMS": "NFP (Nonfarm Payrolls)",
    "FEDFUNDS": "Federal Funds Rate",
    "GDP": "US GDP",
    "UNRATE": "Unemployment Rate",
    "T10Y2Y": "10Y-2Y Treasury Spread",
    "DFF": "Effective Federal Funds Rate (daily)",
}


async def get_fred_series(series_id: str, limit: int = 24) -> Optional[dict]:
    if not settings.FRED_API_KEY:
        return None
    data = await cached_get_json(
        "https://api.stlouisfed.org/fred/series/observations",
        params={"series_id": series_id, "api_key": settings.FRED_API_KEY,
                "file_type": "json", "sort_order": "desc", "limit": limit},
        cache_key=f"fred:{series_id}:{limit}", ttl=3600)
    if not data:
        return None
    return {"series_id": series_id, "name": FRED_SERIES.get(series_id, series_id),
            "observations": data.get("observations", [])}


async def get_macro_dashboard() -> dict:
    """All key macro series in one payload (only those FRED returns)."""
    out = {}
    for sid in FRED_SERIES:
        series = await get_fred_series(sid, limit=13)
        if series:
            out[sid] = series
    return out


# ------------------------------------------------------------------- stocks

async def finnhub_quote(symbol: str) -> Optional[dict]:
    if not settings.FINNHUB_API_KEY:
        return None
    return await cached_get_json("https://finnhub.io/api/v1/quote",
                                 params={"symbol": symbol.upper(), "token": settings.FINNHUB_API_KEY},
                                 cache_key=f"fh:quote:{symbol.upper()}", ttl=60)


async def finnhub_profile(symbol: str) -> Optional[dict]:
    if not settings.FINNHUB_API_KEY:
        return None
    return await cached_get_json("https://finnhub.io/api/v1/stock/profile2",
                                 params={"symbol": symbol.upper(), "token": settings.FINNHUB_API_KEY},
                                 cache_key=f"fh:profile:{symbol.upper()}", ttl=86400)


async def alpha_vantage_daily(symbol: str) -> Optional[dict]:
    if not settings.ALPHA_VANTAGE_API_KEY:
        return None
    return await cached_get_json("https://www.alphavantage.co/query",
                                 params={"function": "TIME_SERIES_DAILY", "symbol": symbol.upper(),
                                         "outputsize": "compact",
                                         "apikey": settings.ALPHA_VANTAGE_API_KEY},
                                 cache_key=f"av:daily:{symbol.upper()}", ttl=3600)


async def alpha_vantage_fx(from_ccy: str, to_ccy: str) -> Optional[dict]:
    if not settings.ALPHA_VANTAGE_API_KEY:
        return None
    return await cached_get_json("https://www.alphavantage.co/query",
                                 params={"function": "CURRENCY_EXCHANGE_RATE",
                                         "from_currency": from_ccy.upper(),
                                         "to_currency": to_ccy.upper(),
                                         "apikey": settings.ALPHA_VANTAGE_API_KEY},
                                 cache_key=f"av:fx:{from_ccy}:{to_ccy}", ttl=300)


async def fmp_gainers_losers(kind: str = "gainers") -> Optional[list]:
    if not settings.FMP_API_KEY:
        return None
    endpoint = {"gainers": "stock_market/gainers", "losers": "stock_market/losers",
                "actives": "stock_market/actives"}.get(kind, "stock_market/gainers")
    return await cached_get_json(f"https://financialmodelingprep.com/api/v3/{endpoint}",
                                 params={"apikey": settings.FMP_API_KEY},
                                 cache_key=f"fmp:{kind}", ttl=300)
