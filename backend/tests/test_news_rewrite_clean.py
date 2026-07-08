"""Rewritten articles must not contain raw HTML from RSS source descriptions."""
import pytest

from app.services.news.rewriter import rewrite_article, strip_html


def test_strip_html_flattens_markup():
    out = strip_html('<p><a href="x">Bitcoin Magazine</a><br/><img src="y.jpg"/>Terms&#8217;s</p>')
    assert "<" not in out and ">" not in out
    assert "Bitcoin Magazine" in out


@pytest.mark.asyncio
async def test_rewrite_strips_html_from_source():
    raw = {
        "title": "Cantor SPAC and Adam Back",
        "description": '<p>Cantor-backed SPAC <a href="z">scrapped</a> terms.</p><img src="i.jpg"/>',
        "url": "https://x/a", "source": "bitcoinmagazine",
        "symbols": ["BTC"], "source_hash": "h1",
    }
    r = await rewrite_article(raw)
    assert r is not None
    assert "<" not in r["content"] and "<" not in r["summary"]
    assert "scrapped terms" in r["content"]
