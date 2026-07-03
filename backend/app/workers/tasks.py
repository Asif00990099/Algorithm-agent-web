"""Background automation tasks (Celery).

Each task runs its own asyncio loop and disposes the DB engine afterwards so
pooled connections never leak across loops. Every cycle publishes progress to
Redis pub/sub, which the WebSocket layer fans out to connected clients.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from celery import shared_task
from sqlalchemy import select

from app.core.cache import cache_set, publish
from app.workers.celery_app import celery_app  # noqa: F401 - registers app

logger = logging.getLogger(__name__)

WATCHED_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
                   "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"]


def run_async(coro):
    """Run an async job inside a sync Celery task with clean engine teardown.
    Applies admin-managed API keys from the DB first so workers use the same
    credentials as the API process."""
    async def wrapper():
        from app.db.session import AsyncSessionLocal, engine
        from app.services.runtime_config import apply_credentials_to_settings
        try:
            async with AsyncSessionLocal() as db:
                await apply_credentials_to_settings(db)
            return await coro
        finally:
            await engine.dispose()
    return asyncio.run(wrapper())


# ------------------------------------------------------------- market sync

@shared_task(name="app.workers.tasks.market_sync")
def market_sync():
    return run_async(_market_sync())


async def _market_sync():
    """Warm the market caches (top coins, global, tickers) every minute so
    user requests are always served hot from Redis."""
    from app.services.market import binance, coingecko, macro
    top = await coingecko.get_markets(per_page=100)
    await coingecko.get_global()
    await macro.get_fear_greed(1)
    for symbol in WATCHED_SYMBOLS:
        await binance.get_ticker_24h(symbol)
    count = len(top) if top else 0
    await cache_set("worker:last_market_sync",
                    {"time": datetime.now(timezone.utc).isoformat(), "coins": count}, ttl=600)
    return {"coins_cached": count}


# ----------------------------------------------------------------- scanner

@shared_task(name="app.workers.tasks.scanner_cycle")
def scanner_cycle():
    return run_async(_scanner_cycle())


async def _scanner_cycle():
    from app.services.scanner.scanner import run_scan
    result = await run_scan()
    return {"pairs_scanned": result["pairs_scanned"] if result else 0}


# ----------------------------------------------------------------- signals

@shared_task(name="app.workers.tasks.signal_cycle")
def signal_cycle():
    return run_async(_signal_cycle())


async def _signal_cycle():
    """Run every active strategy's agent over the watchlist and persist
    actionable signals."""
    from app.db.session import AsyncSessionLocal
    from app.models import Signal, SignalAction, Strategy
    from app.services.ai.agent import analyze_symbol

    generated = 0
    async with AsyncSessionLocal() as db:
        strategies = (await db.execute(
            select(Strategy).where(Strategy.is_active.is_(True)))).scalars().all()
        for strat in strategies:
            try:
                params = json.loads(strat.params or "{}")
            except json.JSONDecodeError:
                params = {}
            for symbol in WATCHED_SYMBOLS[:6]:
                try:
                    decision = await analyze_symbol(symbol, strat.timeframe, params,
                                                    include_sentiment=False, use_llm=False)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Signal analysis failed %s/%s: %s", strat.name, symbol, exc)
                    continue
                if decision is None or decision.action == "hold":
                    continue
                sig = Signal(
                    strategy_id=strat.id, symbol=decision.symbol,
                    timeframe=decision.timeframe, action=SignalAction(decision.action),
                    price_at_signal=decision.price, probability=decision.probability,
                    confidence=decision.confidence, risk_reward=decision.risk_reward,
                    stop_loss=decision.stop_loss, take_profit=decision.take_profit,
                    trailing_stop_pct=decision.trailing_stop_pct,
                    indicators_snapshot=json.dumps(decision.indicators, default=str),
                    sentiment_score=decision.sentiment_score,
                    rationale=decision.rationale, ai_provider=decision.ai_provider)
                db.add(sig)
                strat.total_signals += 1
                generated += 1
                await publish("signals", {"type": "new_signal", "symbol": decision.symbol,
                                          "action": decision.action,
                                          "confidence": decision.confidence,
                                          "strategy": strat.name})
        await db.commit()
    return {"signals_generated": generated}


# --------------------------------------------------------- learning loop

@shared_task(name="app.workers.tasks.evaluate_signals")
def evaluate_signals():
    return run_async(_evaluate_signals())


async def _evaluate_signals():
    """Score signals older than their evaluation horizon against the live
    price, update strategy accuracy and re-rank strategies."""
    from app.db.session import AsyncSessionLocal
    from app.models import ModelEvaluation, Signal, SignalAction, Strategy
    from app.services.market.binance import get_price

    horizon = timedelta(hours=4)
    cutoff = datetime.now(timezone.utc) - horizon
    evaluated = 0
    async with AsyncSessionLocal() as db:
        signals = (await db.execute(
            select(Signal).where(Signal.evaluated.is_(False),
                                 Signal.created_at <= cutoff)
            .limit(200))).scalars().all()
        for sig in signals:
            price = await get_price(sig.symbol)
            if price is None:
                continue
            ret = (price - sig.price_at_signal) / sig.price_at_signal * 100
            sig.outcome_price = price
            sig.outcome_return_pct = round(ret, 4)
            if sig.action == SignalAction.BUY:
                sig.was_correct = ret > 0.15
            elif sig.action == SignalAction.SELL:
                sig.was_correct = ret < -0.15
            else:
                sig.was_correct = abs(ret) <= 0.5
            sig.evaluated = True
            sig.evaluated_at = datetime.now(timezone.utc)
            evaluated += 1
            if sig.strategy_id:
                strat = await db.get(Strategy, sig.strategy_id)
                if strat:
                    if sig.was_correct:
                        strat.correct_signals += 1
                    if strat.total_signals > 0:
                        strat.win_rate = round(strat.correct_signals / strat.total_signals * 100, 2)
                    strat.rank_score = round(strat.win_rate * 0.6
                                             + strat.profit_factor * 15
                                             + strat.sharpe_ratio * 8, 2)
        if evaluated:
            db.add(ModelEvaluation(window_hours=int(horizon.total_seconds() // 3600),
                                   signals_evaluated=evaluated,
                                   accuracy=0.0, notes="hourly evaluation cycle"))
        await db.commit()
    return {"signals_evaluated": evaluated}


# ---------------------------------------------------------------- trading

@shared_task(name="app.workers.tasks.trade_monitor")
def trade_monitor():
    return run_async(_trade_monitor())


async def _trade_monitor():
    """Enforce SL/TP/trailing on every open position; also trigger price alerts."""
    from app.db.session import AsyncSessionLocal
    from app.models import Notification, PriceAlert, Trade, TradeStatus, User
    from app.services.market.binance import get_price
    from app.services.trading.engine import monitor_open_trade

    closed = 0
    alerts_fired = 0
    async with AsyncSessionLocal() as db:
        trades = (await db.execute(
            select(Trade).where(Trade.status == TradeStatus.OPEN))).scalars().all()
        for trade in trades:
            user = await db.get(User, trade.user_id)
            if user is None:
                continue
            try:
                reason = await monitor_open_trade(db, user, trade)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Trade monitor error %s: %s", trade.id, exc)
                continue
            if reason:
                closed += 1
                await publish("trades", {"type": "auto_close", "trade_id": trade.id,
                                         "symbol": trade.symbol, "reason": reason})

        alerts = (await db.execute(
            select(PriceAlert).where(PriceAlert.is_triggered.is_(False)))).scalars().all()
        prices: dict[str, float | None] = {}
        for alert in alerts:
            if alert.symbol not in prices:
                prices[alert.symbol] = await get_price(alert.symbol)
            price = prices[alert.symbol]
            if price is None:
                continue
            hit = price >= alert.target_price if alert.condition == "above" \
                else price <= alert.target_price
            if hit:
                alert.is_triggered = True
                alert.triggered_at = datetime.now(timezone.utc)
                alerts_fired += 1
                db.add(Notification(user_id=alert.user_id, kind="alert",
                                    title=f"Price alert: {alert.symbol} {alert.condition} {alert.target_price}",
                                    body=f"Current price {price}"))
                await publish("alerts", {"type": "price_alert", "symbol": alert.symbol,
                                         "price": price, "user_id": alert.user_id})
        await db.commit()
    return {"positions_closed": closed, "alerts_fired": alerts_fired}


# -------------------------------------------------------------------- news

@shared_task(name="app.workers.tasks.news_cycle")
def news_cycle():
    return run_async(_news_cycle())


async def _news_cycle():
    """Collect news from every source, rewrite into original articles and
    auto-publish (unless news_auto_publish=false in app settings)."""
    from app.api.v1.content import _get_or_create_category, _sync_tags
    from app.db.session import AsyncSessionLocal
    from app.models import AppSetting, Article, ArticleStatus
    from app.services.news.aggregator import collect_all_news
    from app.services.news.rewriter import rewrite_article

    raw_articles = await collect_all_news()
    published = 0
    async with AsyncSessionLocal() as db:
        auto_setting = await db.get(AppSetting, "news_auto_publish")
        auto_publish = (auto_setting.value.lower() != "false") if auto_setting else True

        for raw in raw_articles[:30]:  # bounded per cycle
            if not raw.get("source_hash"):
                continue
            exists = await db.scalar(select(Article).where(
                Article.source_hash == raw["source_hash"]))
            if exists:
                continue
            rewritten = await rewrite_article(raw)
            if rewritten is None:
                continue
            slug = rewritten["slug"]
            if await db.scalar(select(Article).where(Article.slug == slug)):
                slug = f"{slug}-{int(datetime.now().timestamp())}"
            article = Article(
                title=rewritten["title"], slug=slug, summary=rewritten["summary"],
                content=rewritten["content"],
                status=ArticleStatus.PUBLISHED if auto_publish else ArticleStatus.DRAFT,
                seo_title=rewritten["seo_title"], seo_description=rewritten["seo_description"],
                seo_keywords=rewritten["seo_keywords"],
                featured_image_url=rewritten["featured_image_url"],
                is_auto_generated=True, source_name=rewritten["source_name"],
                source_url=rewritten["source_url"], source_hash=rewritten["source_hash"],
                sentiment=rewritten["sentiment"], symbols=rewritten["symbols"],
                published_at=datetime.now(timezone.utc) if auto_publish else None)
            article.category_id = (await _get_or_create_category(db, rewritten["category"])).id
            article.tags = await _sync_tags(db, rewritten["tags"])
            db.add(article)
            published += 1
            await publish("news", {"type": "new_article", "title": article.title,
                                   "slug": slug, "sentiment": article.sentiment})
        await db.commit()
    return {"articles_created": published}


@shared_task(name="app.workers.tasks.publish_scheduled")
def publish_scheduled():
    return run_async(_publish_scheduled())


async def _publish_scheduled():
    from app.db.session import AsyncSessionLocal
    from app.models import Article, ArticleStatus

    now = datetime.now(timezone.utc)
    count = 0
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Article).where(Article.status == ArticleStatus.SCHEDULED,
                                  Article.scheduled_for <= now))).scalars().all()
        for article in rows:
            article.status = ArticleStatus.PUBLISHED
            article.published_at = now
            count += 1
        await db.commit()
    return {"published": count}


# --------------------------------------------------------------- sentiment

@shared_task(name="app.workers.tasks.sentiment_cycle")
def sentiment_cycle():
    return run_async(_sentiment_cycle())


async def _sentiment_cycle():
    """Aggregate social sentiment per watched asset and store snapshots."""
    from app.db.session import AsyncSessionLocal
    from app.models import SentimentSnapshot
    from app.services.sentiment.analyzer import aggregate
    from app.services.sentiment.sources import fetch_all_rss, fetch_reddit_posts

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        reddit_texts: list[str] = []
        for sub in ("CryptoCurrency", "Bitcoin", "stocks"):
            posts = await fetch_reddit_posts(sub)
            reddit_texts.extend(f"{p['title']} {p['text']}" for p in posts)
        rss_items = await fetch_all_rss(8)
        rss_texts = [f"{i['title']} {i['summary']}" for i in rss_items]

        for source, texts in (("reddit", reddit_texts), ("rss", rss_texts)):
            agg = aggregate(texts)
            if agg["sample_size"] == 0:
                continue
            db.add(SentimentSnapshot(created_at=now, symbol="MARKET", source=source,
                                     score=agg["score"], positive=agg["positive"],
                                     negative=agg["negative"], neutral=agg["neutral"],
                                     sample_size=agg["sample_size"]))

        # per-asset snapshots from the combined text pool
        pool = reddit_texts + rss_texts
        for base in ("BTC", "ETH", "SOL", "XRP", "DOGE"):
            keywords = {"BTC": ["btc", "bitcoin"], "ETH": ["eth", "ethereum"],
                        "SOL": ["sol", "solana"], "XRP": ["xrp", "ripple"],
                        "DOGE": ["doge", "dogecoin"]}[base]
            texts = [t for t in pool if any(k in t.lower() for k in keywords)]
            agg = aggregate(texts)
            if agg["sample_size"] == 0:
                continue
            db.add(SentimentSnapshot(created_at=now, symbol=f"{base}USDT", source="aggregate",
                                     score=agg["score"], positive=agg["positive"],
                                     negative=agg["negative"], neutral=agg["neutral"],
                                     sample_size=agg["sample_size"]))
        await db.commit()
    return {"time": now.isoformat()}


# ---------------------------------------------------------------- calendar

@shared_task(name="app.workers.tasks.calendar_sync")
def calendar_sync():
    return run_async(_calendar_sync())


async def _calendar_sync():
    from app.db.session import AsyncSessionLocal
    from app.models import EconomicEvent
    from app.services.calendar.economic import collect_calendar

    events = await collect_calendar()
    inserted = 0
    async with AsyncSessionLocal() as db:
        for ev in events:
            exists = await db.scalar(select(EconomicEvent).where(
                EconomicEvent.external_id == ev["external_id"]))
            if exists:
                continue
            event_time = None
            if ev.get("event_time"):
                try:
                    event_time = datetime.fromisoformat(ev["event_time"])
                except ValueError:
                    event_time = None
            db.add(EconomicEvent(external_id=ev["external_id"], title=ev["title"][:300],
                                 country=ev["country"], category=ev["category"],
                                 importance=ev["importance"], event_time=event_time,
                                 source=ev["source"], url=ev["url"][:600]))
            inserted += 1
        await db.commit()
    return {"events_added": inserted}
