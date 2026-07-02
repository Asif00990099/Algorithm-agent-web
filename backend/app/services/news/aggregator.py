"""News aggregation from free APIs: NewsAPI, CryptoPanic, Marketaux and RSS.

Each source is normalized to a common shape:
  {title, description, url, source, published_at, symbols}
Deduplication happens downstream via a content hash on (title + source_url).
"""
import hashlib
import logging
from typing import List

from app.core.config import settings
from app.services.market.http import cached_get_json
from app.services.sentiment.sources import fetch_all_rss

logger = logging.getLogger(__name__)


def source_hash(title: str, url: str) -> str:
    return hashlib.sha256(f"{title.strip().lower()}|{url.strip()}".encode()).hexdigest()


async def fetch_newsapi(query: str = "crypto OR bitcoin OR stock market", limit: int = 25) -> List[dict]:
    if not settings.NEWSAPI_API_KEY:
        return []
    data = await cached_get_json(
        "https://newsapi.org/v2/everything",
        params={"q": query, "language": "en", "sortBy": "publishedAt",
                "pageSize": min(limit, 100), "apiKey": settings.NEWSAPI_API_KEY},
        cache_key=f"newsapi:{query}:{limit}", ttl=600)
    if not data or data.get("status") != "ok":
        return []
    return [{
        "title": a.get("title") or "", "description": a.get("description") or "",
        "url": a.get("url") or "", "source": (a.get("source") or {}).get("name", "NewsAPI"),
        "published_at": a.get("publishedAt"), "image_url": a.get("urlToImage") or "",
        "symbols": [],
    } for a in data.get("articles", []) if a.get("title")]


async def fetch_cryptopanic(limit: int = 25) -> List[dict]:
    if not settings.CRYPTOPANIC_API_KEY:
        return []
    data = await cached_get_json(
        "https://cryptopanic.com/api/v1/posts/",
        params={"auth_token": settings.CRYPTOPANIC_API_KEY, "public": "true", "kind": "news"},
        cache_key="cryptopanic:news", ttl=600)
    if not data:
        return []
    out = []
    for p in data.get("results", [])[:limit]:
        out.append({
            "title": p.get("title") or "", "description": "",
            "url": p.get("url") or "", "source": (p.get("source") or {}).get("title", "CryptoPanic"),
            "published_at": p.get("published_at"), "image_url": "",
            "symbols": [c.get("code", "") for c in p.get("currencies") or []],
        })
    return out


async def fetch_marketaux(limit: int = 25) -> List[dict]:
    if not settings.MARKETAUX_API_KEY:
        return []
    data = await cached_get_json(
        "https://api.marketaux.com/v1/news/all",
        params={"api_token": settings.MARKETAUX_API_KEY, "language": "en",
                "filter_entities": "true", "limit": min(limit, 100)},
        cache_key="marketaux:news", ttl=600)
    if not data:
        return []
    out = []
    for a in data.get("data", []):
        out.append({
            "title": a.get("title") or "", "description": a.get("description") or "",
            "url": a.get("url") or "", "source": a.get("source") or "Marketaux",
            "published_at": a.get("published_at"), "image_url": a.get("image_url") or "",
            "symbols": [e.get("symbol", "") for e in a.get("entities") or []],
        })
    return out


async def fetch_rss_news(limit_per_feed: int = 8) -> List[dict]:
    items = await fetch_all_rss(limit_per_feed)
    return [{
        "title": i["title"], "description": i["summary"], "url": i["link"],
        "source": i["source"], "published_at": i["published"], "image_url": "",
        "symbols": [],
    } for i in items if i.get("title")]


async def collect_all_news() -> List[dict]:
    """Fetch from every configured source; RSS always works without keys."""
    articles: List[dict] = []
    articles.extend(await fetch_rss_news())
    articles.extend(await fetch_newsapi())
    articles.extend(await fetch_cryptopanic())
    articles.extend(await fetch_marketaux())

    seen = set()
    unique = []
    for a in articles:
        h = source_hash(a["title"], a["url"])
        if h in seen:
            continue
        seen.add(h)
        a["source_hash"] = h
        unique.append(a)
    logger.info("Collected %d unique articles from all sources", len(unique))
    return unique
