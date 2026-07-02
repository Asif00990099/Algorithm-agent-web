"""Economic calendar & central-bank monitoring.

Sources (all free):
  • FRED release calendar + key series (CPI, PPI, NFP, GDP, rates, employment)
  • Central-bank RSS: Federal Reserve, ECB, Bank of England, Bank of Japan
Events are upserted into `economic_events`; the news worker also scores
central-bank headlines for breaking-event alerts.
"""
import hashlib
import logging
from typing import List

import feedparser

from app.core.config import settings
from app.services.market.http import cached_get_json, get_http

logger = logging.getLogger(__name__)

CENTRAL_BANK_FEEDS = {
    "fed": ("US", "https://www.federalreserve.gov/feeds/press_all.xml"),
    "ecb": ("EU", "https://www.ecb.europa.eu/rss/press.html"),
    "boe": ("GB", "https://www.bankofengland.co.uk/rss/news"),
    "boj": ("JP", "https://www.boj.or.jp/en/rss/whatsnew.xml"),
}

HIGH_IMPACT_KEYWORDS = {
    "fomc": 3, "rate decision": 3, "interest rate": 3, "cpi": 3, "inflation": 2,
    "nonfarm": 3, "payroll": 3, "nfp": 3, "gdp": 2, "ppi": 2, "unemployment": 2,
    "monetary policy": 3, "quantitative": 2, "employment": 2, "minutes": 2,
    "statement": 2, "press conference": 2,
}


def _importance(title: str) -> int:
    t = title.lower()
    return max((v for k, v in HIGH_IMPACT_KEYWORDS.items() if k in t), default=1)


def _event_id(source: str, title: str, when: str) -> str:
    return hashlib.sha256(f"{source}|{title}|{when}".encode()).hexdigest()[:32]


async def fetch_fred_releases(limit: int = 50) -> List[dict]:
    """Upcoming/recent data release dates from FRED."""
    if not settings.FRED_API_KEY:
        return []
    data = await cached_get_json(
        "https://api.stlouisfed.org/fred/releases/dates",
        params={"api_key": settings.FRED_API_KEY, "file_type": "json",
                "include_release_dates_with_no_data": "true",
                "sort_order": "desc", "limit": limit},
        cache_key=f"fred:releases:{limit}", ttl=3600)
    if not data:
        return []
    events = []
    for rd in data.get("release_dates", []):
        name = rd.get("release_name", "")
        date = rd.get("date", "")
        events.append({
            "external_id": _event_id("fred", name, date),
            "title": name, "country": "US",
            "category": _categorize(name), "importance": _importance(name),
            "event_time": f"{date}T13:30:00+00:00",  # typical US release time
            "source": "FRED",
            "url": "https://fred.stlouisfed.org/releases",
        })
    return events


def _categorize(title: str) -> str:
    t = title.lower()
    for key, cat in [("consumer price", "CPI"), ("producer price", "PPI"),
                     ("employment", "NFP"), ("payroll", "NFP"),
                     ("gross domestic", "GDP"), ("interest", "RATES"),
                     ("fomc", "FOMC"), ("h.15", "RATES")]:
        if key in t:
            return cat
    return "DATA"


async def fetch_central_bank_news(limit_per_bank: int = 10) -> List[dict]:
    events = []
    for bank, (country, url) in CENTRAL_BANK_FEEDS.items():
        try:
            resp = await get_http().get(url)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Central bank feed failed %s: %s", bank, exc)
            continue
        for entry in parsed.entries[:limit_per_bank]:
            title = entry.get("title", "")
            published = entry.get("published", "") or entry.get("updated", "")
            events.append({
                "external_id": _event_id(bank, title, published),
                "title": f"[{bank.upper()}] {title}",
                "country": country,
                "category": "CENTRAL_BANK",
                "importance": _importance(title),
                "event_time": None,
                "source": bank.upper(),
                "url": entry.get("link", ""),
            })
    return events


async def collect_calendar() -> List[dict]:
    events = await fetch_fred_releases()
    events.extend(await fetch_central_bank_news())
    return events
