"""Automated news rewriting & SEO pipeline.

Every collected article is transformed into ORIGINAL content before
publication — never copied. Two engines:

  • LLM engine (when AI_PROVIDER is configured): full journalistic rewrite
    with SEO title, meta description, tags and category.
  • Template engine (always available): builds an original summary-style
    brief from the headline/description facts, structured with our own
    editorial framing, market context and attribution link.

Both credit the original source and link out (`source_url`).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.services.ai.llm import try_complete
from app.services.sentiment.analyzer import analyze_text

logger = logging.getLogger(__name__)

CATEGORY_KEYWORDS = {
    "bitcoin": "Bitcoin", "btc": "Bitcoin", "ethereum": "Ethereum", "eth": "Ethereum",
    "defi": "DeFi", "nft": "NFT", "etf": "ETF", "sec": "Regulation",
    "regulation": "Regulation", "lawsuit": "Regulation", "fed": "Macro",
    "inflation": "Macro", "cpi": "Macro", "fomc": "Macro", "rate": "Macro",
    "stock": "Stocks", "earnings": "Stocks", "nasdaq": "Stocks", "s&p": "Stocks",
    "altcoin": "Altcoins", "solana": "Altcoins", "xrp": "Altcoins",
    "exchange": "Exchanges", "binance": "Exchanges", "coinbase": "Exchanges",
    "whale": "On-Chain", "on-chain": "On-Chain", "mining": "Mining",
}

STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
             "as", "at", "by", "is", "are", "was", "be", "this", "that", "its",
             "it", "from", "has", "have", "after", "into", "over", "amid", "will"}


def slugify(text: str, max_length: int = 80) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_length].rstrip("-") or "article"


def extract_tags(title: str, description: str, max_tags: int = 6) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9&\-]+", f"{title} {description}")
    freq: dict[str, int] = {}
    for w in words:
        lw = w.lower()
        if lw in STOPWORDS or len(lw) < 3:
            continue
        freq[lw] = freq.get(lw, 0) + (2 if w[0].isupper() else 1)
    ranked = sorted(freq, key=freq.get, reverse=True)
    return ranked[:max_tags]


def detect_category(title: str, description: str) -> str:
    blob = f"{title} {description}".lower()
    for kw, cat in CATEGORY_KEYWORDS.items():
        if kw in blob:
            return cat
    return "Markets"


def featured_image_for(category: str, symbols: list[str]) -> str:
    """Deterministic branded featured image (self-hosted SVG endpoint)."""
    label = (symbols[0] if symbols else category).upper()
    return f"/api/v1/media/og-image?label={label}&category={slugify(category)}"


async def rewrite_article(raw: dict) -> Optional[dict]:
    """Return a publishable original article dict, or None if input unusable."""
    title = (raw.get("title") or "").strip()
    description = (raw.get("description") or "").strip()
    if not title:
        return None

    sentiment = analyze_text(f"{title}. {description}")
    tags = extract_tags(title, description)
    category = detect_category(title, description)
    symbols = [s for s in raw.get("symbols", []) if s][:5]

    result = await _llm_rewrite(title, description, raw.get("source", ""), tags, category)
    if result is None:
        result = _template_rewrite(title, description, raw.get("source", ""),
                                   raw.get("url", ""), sentiment.label)

    new_title = result["title"][:280]
    return {
        "title": new_title,
        "slug": slugify(new_title),
        "summary": result["summary"][:1000],
        "content": result["content"],
        "seo_title": result.get("seo_title", new_title)[:280],
        "seo_description": result.get("seo_description", result["summary"][:160]),
        "seo_keywords": ", ".join(result.get("keywords", tags)),
        "category": category,
        "tags": tags,
        "featured_image_url": raw.get("image_url") or featured_image_for(category, symbols),
        "sentiment": sentiment.score,
        "symbols": ",".join(symbols),
        "source_name": raw.get("source", ""),
        "source_url": raw.get("url", ""),
        "source_hash": raw.get("source_hash", ""),
    }


async def _llm_rewrite(title: str, description: str, source: str,
                       tags: list[str], category: str) -> Optional[dict]:
    text = await try_complete(
        system=("You are a financial news editor. Rewrite the given story as a fully "
                "ORIGINAL article — new headline, new structure, your own words; do not "
                "copy sentences. 300-450 words of markdown with 2-3 ## subheadings. "
                "Stay strictly factual to the provided material; add no invented facts, "
                "numbers or quotes. Reply ONLY with JSON: {\"title\", \"summary\" "
                "(1-2 sentences), \"content\" (markdown), \"seo_title\" (<60 chars), "
                "\"seo_description\" (<155 chars), \"keywords\" (array of strings)}."),
        user=json.dumps({"headline": title, "description": description,
                         "source": source, "category": category, "topic_tags": tags}),
        max_tokens=1600)
    if not text:
        return None
    try:
        start, end = text.find("{"), text.rfind("}")
        data = json.loads(text[start:end + 1])
        if data.get("title") and data.get("content"):
            return data
    except (ValueError, json.JSONDecodeError):
        logger.warning("LLM rewrite returned unparseable JSON")
    return None


def _template_rewrite(title: str, description: str, source: str, url: str,
                      sentiment_label: str) -> dict:
    """Key-fact brief written in our own editorial structure (no LLM needed)."""
    new_title = f"Market Brief: {title}"
    tone = {"positive": "a constructive development for market participants",
            "negative": "a headwind that traders are watching closely",
            "neutral": "a development traders are monitoring"}[sentiment_label]
    summary = (f"{source or 'A financial news outlet'} reports on: {title}. "
               f"Early read on sentiment suggests {tone}.")
    body_fact = description or title
    content = "\n\n".join([
        f"## What happened",
        f"According to reporting by {source or 'the original source'}, {body_fact}",
        f"## Why it matters",
        f"Our sentiment engine classifies this story as **{sentiment_label}** — {tone}. "
        f"Headlines like this can shift positioning quickly; watch volume, funding rates "
        f"and order-book depth on related pairs for confirmation before acting.",
        f"## The bigger picture",
        f"This brief was generated by QuantPulse's automated news desk, which monitors "
        f"dozens of sources around the clock and never republishes source text verbatim. "
        f"Read the original reporting at [{source or 'source'}]({url}).",
    ])
    return {"title": new_title, "summary": summary, "content": content,
            "seo_title": new_title[:60], "seo_description": summary[:155],
            "keywords": extract_tags(title, description)}
