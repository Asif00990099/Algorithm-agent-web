"""CoinGecko free API — coin metadata, market snapshots, global stats.

Free tier: ~30 req/min. Everything here is cached aggressively in Redis and
refreshed by the market-sync worker, so user traffic never hits CoinGecko
directly."""
from typing import Any, List, Optional

from app.core.config import settings
from app.services.market.http import cached_get_json

BASE = "https://api.coingecko.com/api/v3"


def _headers() -> dict:
    return {"x-cg-demo-api-key": settings.COINGECKO_API_KEY} if settings.COINGECKO_API_KEY else {}


async def get_markets(vs_currency: str = "usd", page: int = 1, per_page: int = 100,
                      ids: Optional[str] = None) -> Optional[List[dict]]:
    """Top coins with price, volume, market cap, rank, logo, ATH/ATL, changes."""
    params = {
        "vs_currency": vs_currency, "order": "market_cap_desc",
        "per_page": per_page, "page": page, "sparkline": "true",
        "price_change_percentage": "24h,7d,30d",
    }
    if ids:
        params["ids"] = ids
    return await cached_get_json(f"{BASE}/coins/markets", params=params, headers=_headers(),
                                 cache_key=f"cg:markets:{vs_currency}:{page}:{per_page}:{ids}", ttl=60)


async def get_coin_detail(coin_id: str) -> Optional[dict]:
    """Full coin detail: 52w-ish ranges come from market_data; includes ATH/ATL,
    supply, links and description."""
    params = {"localization": "false", "tickers": "false", "market_data": "true",
              "community_data": "true", "developer_data": "false", "sparkline": "true"}
    return await cached_get_json(f"{BASE}/coins/{coin_id}", params=params, headers=_headers(),
                                 cache_key=f"cg:coin:{coin_id}", ttl=120)


async def get_global() -> Optional[dict]:
    return await cached_get_json(f"{BASE}/global", headers=_headers(),
                                 cache_key="cg:global", ttl=300)


async def get_trending() -> Optional[dict]:
    return await cached_get_json(f"{BASE}/search/trending", headers=_headers(),
                                 cache_key="cg:trending", ttl=300)


async def get_market_chart(coin_id: str, days: int = 30, vs_currency: str = "usd") -> Optional[dict]:
    params = {"vs_currency": vs_currency, "days": days}
    return await cached_get_json(f"{BASE}/coins/{coin_id}/market_chart", params=params,
                                 headers=_headers(),
                                 cache_key=f"cg:chart:{coin_id}:{days}", ttl=300)


async def search(query: str) -> Optional[dict]:
    return await cached_get_json(f"{BASE}/search", params={"query": query}, headers=_headers(),
                                 cache_key=f"cg:search:{query.lower()}", ttl=3600)


async def get_new_listings() -> Optional[Any]:
    """Recently added coins — powers the scanner's New Listings feed."""
    return await cached_get_json(f"{BASE}/coins/list/new", headers=_headers(),
                                 cache_key="cg:new_listings", ttl=1800)
