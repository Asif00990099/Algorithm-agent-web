"""Social data collectors: Reddit public JSON, X (Twitter) API v2 (optional
bearer token), Telegram public channel RSS bridges and finance RSS feeds."""
import logging
from typing import List, Optional

import feedparser

from app.core.config import settings
from app.services.market.http import cached_get_json, get_http

logger = logging.getLogger(__name__)

CRYPTO_SUBREDDITS = ["CryptoCurrency", "Bitcoin", "ethereum", "CryptoMarkets"]
STOCK_SUBREDDITS = ["stocks", "wallstreetbets", "investing", "StockMarket"]

RSS_FEEDS = {
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
    "decrypt": "https://decrypt.co/feed",
    "bitcoinmagazine": "https://bitcoinmagazine.com/.rss/full/",
    "reuters_markets": "https://feeds.reuters.com/reuters/businessNews",
    "cnbc_markets": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "investing_news": "https://www.investing.com/rss/news.rss",
}


async def fetch_reddit_posts(subreddit: str, limit: int = 25) -> List[dict]:
    """Reddit's public JSON endpoint — no API key needed."""
    data = await cached_get_json(
        f"https://www.reddit.com/r/{subreddit}/hot.json",
        params={"limit": limit},
        headers={"User-Agent": settings.REDDIT_USER_AGENT},
        cache_key=f"reddit:{subreddit}:{limit}", ttl=300)
    if not data:
        return []
    posts = []
    for child in data.get("data", {}).get("children", []):
        p = child.get("data", {})
        posts.append({
            "id": p.get("id"), "title": p.get("title", ""),
            "text": p.get("selftext", "")[:500], "score": p.get("score", 0),
            "num_comments": p.get("num_comments", 0),
            "url": f"https://reddit.com{p.get('permalink', '')}",
            "created_utc": p.get("created_utc"), "subreddit": subreddit,
        })
    return posts


async def fetch_tweets(query: str, limit: int = 25) -> List[dict]:
    """X API v2 recent search — requires TWITTER_BEARER_TOKEN (free tier)."""
    if not settings.TWITTER_BEARER_TOKEN:
        return []
    data = await cached_get_json(
        "https://api.twitter.com/2/tweets/search/recent",
        params={"query": f"{query} -is:retweet lang:en", "max_results": min(limit, 100),
                "tweet.fields": "public_metrics,created_at"},
        headers={"Authorization": f"Bearer {settings.TWITTER_BEARER_TOKEN}"},
        cache_key=f"twitter:{query}:{limit}", ttl=300)
    if not data:
        return []
    return [{"id": t.get("id"), "text": t.get("text", ""),
             "metrics": t.get("public_metrics", {}), "created_at": t.get("created_at")}
            for t in data.get("data", [])]


async def fetch_rss(feed_key: str, limit: int = 20) -> List[dict]:
    url = RSS_FEEDS.get(feed_key)
    if not url:
        return []
    try:
        resp = await get_http().get(url)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("RSS fetch failed %s: %s", feed_key, exc)
        return []
    items = []
    for entry in parsed.entries[:limit]:
        items.append({
            "title": entry.get("title", ""),
            "summary": entry.get("summary", "")[:1000],
            "link": entry.get("link", ""),
            "published": entry.get("published", ""),
            "source": feed_key,
        })
    return items


async def fetch_all_rss(limit_per_feed: int = 10) -> List[dict]:
    out: List[dict] = []
    for key in RSS_FEEDS:
        out.extend(await fetch_rss(key, limit_per_feed))
    return out


async def collect_symbol_texts(symbol_query: str) -> dict:
    """Gather raw texts about a symbol from every configured source."""
    texts: dict[str, List[str]] = {"reddit": [], "twitter": [], "rss": []}
    for sub in CRYPTO_SUBREDDITS[:2]:
        posts = await fetch_reddit_posts(sub)
        texts["reddit"].extend(
            f"{p['title']} {p['text']}" for p in posts
            if symbol_query.lower() in (p["title"] + p["text"]).lower())
    tweets = await fetch_tweets(symbol_query)
    texts["twitter"].extend(t["text"] for t in tweets)
    for item in await fetch_all_rss(5):
        blob = f"{item['title']} {item['summary']}"
        if symbol_query.lower() in blob.lower():
            texts["rss"].append(blob)
    return texts
