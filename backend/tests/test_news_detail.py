"""The public article-detail endpoint must return 200 with tags — a regression
guard for the async lazy-load (MissingGreenlet) 500 on `article.tags`."""
from datetime import datetime, timezone

import pytest

from app.db.session import AsyncSessionLocal
from app.models import Article, ArticleStatus, Tag


@pytest.mark.asyncio
async def test_article_detail_returns_200_with_tags(client):
    async with AsyncSessionLocal() as db:
        art = Article(
            title="Kraken seeks final judgment", slug="kraken-final-judgment",
            summary="s", content="## What happened\n\nbody", status=ArticleStatus.PUBLISHED,
            seo_title="t", seo_description="d", seo_keywords="k",
            featured_image_url="/api/v1/media/og-image?label=KRAKEN&category=exchanges",
            is_auto_generated=True, source_name="coindesk", source_url="https://x/a",
            source_hash="h1", sentiment=0.1, symbols="KRAKEN",
            published_at=datetime.now(timezone.utc))
        art.tags = [Tag(name="Kraken", slug="kraken"), Tag(name="Legal", slug="legal")]
        db.add(art)
        await db.commit()

    resp = await client.get("/api/v1/news/kraken-final-judgment")
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"].startswith("## What happened")
    assert {t["slug"] for t in body["tags"]} == {"kraken", "legal"}
