"""Market intelligence: social sentiment, economic calendar, whale feed."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import EconomicEvent, SentimentSnapshot
from app.services.sentiment.analyzer import aggregate, analyze_text
from app.services.sentiment.sources import (CRYPTO_SUBREDDITS,
                                            fetch_reddit_posts, fetch_rss,
                                            fetch_tweets, RSS_FEEDS)

router = APIRouter(prefix="/intel", tags=["intel"])


@router.get("/sentiment/{symbol}")
async def symbol_sentiment(symbol: str, db: AsyncSession = Depends(get_db)):
    """Latest stored snapshots + live aggregate for a symbol."""
    since = datetime.now(timezone.utc) - timedelta(hours=48)
    rows = (await db.execute(
        select(SentimentSnapshot)
        .where(SentimentSnapshot.symbol == symbol.upper(),
               SentimentSnapshot.created_at >= since)
        .order_by(SentimentSnapshot.created_at.desc()).limit(96))).scalars().all()
    return {
        "symbol": symbol.upper(),
        "snapshots": [{"time": r.created_at, "source": r.source, "score": r.score,
                       "positive": r.positive, "negative": r.negative,
                       "neutral": r.neutral, "sample_size": r.sample_size} for r in rows],
    }


@router.get("/social/reddit")
async def reddit_feed(subreddit: str = Query("CryptoCurrency"), limit: int = Query(25, ge=1, le=100)):
    if subreddit not in CRYPTO_SUBREDDITS + ["stocks", "wallstreetbets", "investing", "StockMarket"]:
        subreddit = "CryptoCurrency"
    posts = await fetch_reddit_posts(subreddit, limit)
    for p in posts:
        p["sentiment"] = analyze_text(f"{p['title']} {p['text']}").to_dict()
    return {"subreddit": subreddit, "posts": posts,
            "aggregate": aggregate(f"{p['title']} {p['text']}" for p in posts)}


@router.get("/social/twitter")
async def twitter_feed(q: str = Query("bitcoin", max_length=64), limit: int = Query(25, ge=1, le=100)):
    tweets = await fetch_tweets(q, limit)
    for t in tweets:
        t["sentiment"] = analyze_text(t["text"]).to_dict()
    return {"query": q, "tweets": tweets,
            "aggregate": aggregate(t["text"] for t in tweets),
            "note": None if tweets else "Set TWITTER_BEARER_TOKEN to enable the X feed"}


@router.get("/social/rss")
async def rss_feed(feed: str = Query("coindesk"), limit: int = Query(20, ge=1, le=50)):
    if feed not in RSS_FEEDS:
        feed = "coindesk"
    items = await fetch_rss(feed, limit)
    for i in items:
        i["sentiment"] = analyze_text(f"{i['title']} {i['summary']}").to_dict()
    return {"feed": feed, "available_feeds": list(RSS_FEEDS), "items": items}


@router.get("/calendar")
async def economic_calendar(country: Optional[str] = None,
                            importance: int = Query(1, ge=1, le=3),
                            limit: int = Query(100, ge=1, le=500),
                            db: AsyncSession = Depends(get_db)):
    q = select(EconomicEvent).where(EconomicEvent.importance >= importance)
    if country:
        q = q.where(EconomicEvent.country == country.upper())
    rows = (await db.execute(q.order_by(EconomicEvent.created_at.desc()).limit(limit))
            ).scalars().all()
    return [{"id": e.id, "title": e.title, "country": e.country,
             "category": e.category, "importance": e.importance,
             "event_time": e.event_time, "actual": e.actual, "forecast": e.forecast,
             "previous": e.previous, "source": e.source, "url": e.url} for e in rows]
