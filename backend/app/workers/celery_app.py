"""Celery application + beat schedule for the 24/7 automation pipeline."""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "quantpulse",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_soft_time_limit=240,
    task_time_limit=300,
    worker_max_tasks_per_child=200,
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    "market-sync": {
        "task": "app.workers.tasks.market_sync",
        "schedule": settings.MARKET_SYNC_INTERVAL,
    },
    "scanner-cycle": {
        "task": "app.workers.tasks.scanner_cycle",
        "schedule": settings.SCANNER_INTERVAL,
    },
    "signal-cycle": {
        "task": "app.workers.tasks.signal_cycle",
        "schedule": settings.SIGNAL_INTERVAL,
    },
    "news-cycle": {
        "task": "app.workers.tasks.news_cycle",
        "schedule": settings.NEWS_INTERVAL,
    },
    "sentiment-cycle": {
        "task": "app.workers.tasks.sentiment_cycle",
        "schedule": settings.SENTIMENT_INTERVAL,
    },
    "calendar-sync": {
        "task": "app.workers.tasks.calendar_sync",
        "schedule": settings.CALENDAR_INTERVAL,
    },
    "trade-monitor": {
        "task": "app.workers.tasks.trade_monitor",
        "schedule": settings.TRADE_MONITOR_INTERVAL,
    },
    "signal-evaluation": {
        "task": "app.workers.tasks.evaluate_signals",
        "schedule": 3600,  # hourly learning loop
    },
    "publish-scheduled-articles": {
        "task": "app.workers.tasks.publish_scheduled",
        "schedule": 300,
    },
}
