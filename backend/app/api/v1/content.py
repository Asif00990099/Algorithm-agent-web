"""Public news feed + full CMS (create/edit/schedule/publish, categories,
tags, media) + a self-hosted SVG OG-image generator for featured images."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_editor
from app.db.session import get_db
from app.models import Article, ArticleStatus, Category, Tag, User
from app.schemas.common import ArticleIn, ArticleOut
from app.services.news.rewriter import slugify

router = APIRouter(prefix="/news", tags=["news"])
cms_router = APIRouter(prefix="/cms", tags=["cms"])
media_router = APIRouter(prefix="/media", tags=["media"])
meta_router = APIRouter(prefix="/meta", tags=["meta"])


@meta_router.get("/settings")
async def public_settings(db: AsyncSession = Depends(get_db)):
    """Public branding / SEO / feature-flag settings for the frontend."""
    from app.services import app_settings
    return await app_settings.public_settings(db)


# ------------------------------------------------------------------ public

@router.get("")
async def list_news(category: Optional[str] = None, tag: Optional[str] = None,
                    q: Optional[str] = None,
                    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                    db: AsyncSession = Depends(get_db)):
    query = select(Article).where(Article.status == ArticleStatus.PUBLISHED)
    if category:
        query = query.join(Category, isouter=True).where(Category.slug == category)
    if tag:
        query = query.join(Article.tags).where(Tag.slug == tag)
    if q:
        pattern = f"%{q}%"
        query = query.where(Article.title.ilike(pattern) | Article.summary.ilike(pattern))
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = (await db.execute(query.order_by(Article.published_at.desc())
                             .limit(page_size).offset((page - 1) * page_size))).scalars().unique().all()
    return {"items": [ArticleOut.model_validate(a).model_dump() for a in rows],
            "total": total, "page": page, "page_size": page_size}


@router.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Category).order_by(Category.name))).scalars().all()
    return [{"id": c.id, "name": c.name, "slug": c.slug} for c in rows]


@router.get("/{slug}")
async def get_article(slug: str, db: AsyncSession = Depends(get_db)):
    article = await db.scalar(select(Article).where(Article.slug == slug,
                                                    Article.status == ArticleStatus.PUBLISHED))
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Article not found")
    article.view_count += 1
    await db.commit()
    out = ArticleOut.model_validate(article).model_dump()
    out["tags"] = [{"name": t.name, "slug": t.slug} for t in article.tags]
    return out


# --------------------------------------------------------------------- CMS

async def _get_or_create_category(db: AsyncSession, name: str) -> Category:
    slug = slugify(name, 60)
    cat = await db.scalar(select(Category).where(Category.slug == slug))
    if cat is None:
        cat = Category(name=name, slug=slug)
        db.add(cat)
        await db.flush()
    return cat


async def _sync_tags(db: AsyncSession, names: list[str]) -> list[Tag]:
    tags = []
    for name in names[:10]:
        slug = slugify(name, 50)
        tag = await db.scalar(select(Tag).where(Tag.slug == slug))
        if tag is None:
            tag = Tag(name=name[:48], slug=slug)
            db.add(tag)
            await db.flush()
        tags.append(tag)
    return tags


@cms_router.get("/articles")
async def cms_list(status_filter: Optional[str] = Query(None, alias="status"),
                   page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                   _: User = Depends(require_editor), db: AsyncSession = Depends(get_db)):
    query = select(Article)
    if status_filter:
        query = query.where(Article.status == ArticleStatus(status_filter))
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = (await db.execute(query.order_by(Article.created_at.desc())
                             .limit(page_size).offset((page - 1) * page_size))).scalars().all()
    return {"items": [ArticleOut.model_validate(a).model_dump() for a in rows],
            "total": total, "page": page, "page_size": page_size}


@cms_router.post("/articles", response_model=ArticleOut, status_code=201)
async def cms_create(body: ArticleIn, user: User = Depends(require_editor),
                     db: AsyncSession = Depends(get_db)):
    slug = slugify(body.title)
    if await db.scalar(select(Article).where(Article.slug == slug)):
        slug = f"{slug}-{int(datetime.now().timestamp())}"
    article = Article(
        title=body.title, slug=slug, summary=body.summary, content=body.content,
        status=ArticleStatus(body.status), author_id=user.id,
        seo_title=body.seo_title or body.title,
        seo_description=body.seo_description or body.summary[:160],
        seo_keywords=body.seo_keywords, featured_image_url=body.featured_image_url,
        scheduled_for=body.scheduled_for,
        published_at=datetime.now(timezone.utc) if body.status == "published" else None)
    if body.category:
        article.category_id = (await _get_or_create_category(db, body.category)).id
    article.tags = await _sync_tags(db, body.tags)
    db.add(article)
    await db.commit()
    await db.refresh(article)
    return article


@cms_router.patch("/articles/{article_id}", response_model=ArticleOut)
async def cms_update(article_id: str, body: ArticleIn, _: User = Depends(require_editor),
                     db: AsyncSession = Depends(get_db)):
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Article not found")
    was_published = article.status == ArticleStatus.PUBLISHED
    article.title, article.summary, article.content = body.title, body.summary, body.content
    article.status = ArticleStatus(body.status)
    article.seo_title = body.seo_title or body.title
    article.seo_description = body.seo_description or body.summary[:160]
    article.seo_keywords = body.seo_keywords
    article.featured_image_url = body.featured_image_url
    article.scheduled_for = body.scheduled_for
    if body.category:
        article.category_id = (await _get_or_create_category(db, body.category)).id
    if body.tags:
        article.tags = await _sync_tags(db, body.tags)
    if article.status == ArticleStatus.PUBLISHED and not was_published:
        article.published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(article)
    return article


@cms_router.delete("/articles/{article_id}", status_code=204)
async def cms_delete(article_id: str, _: User = Depends(require_editor),
                     db: AsyncSession = Depends(get_db)):
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Article not found")
    await db.delete(article)
    await db.commit()


# ------------------------------------------------------------ OG image (SVG)

@media_router.get("/og-image")
async def og_image(label: str = Query("QP", max_length=12),
                   category: str = Query("markets", max_length=32)):
    """Deterministic branded featured image — no external image service."""
    palette = {"bitcoin": "#f7931a", "ethereum": "#627eea", "macro": "#8b5cf6",
               "regulation": "#ef4444", "stocks": "#10b981", "defi": "#06b6d4"}
    accent = palette.get(category.lower(), "#6366f1")
    safe_label = "".join(ch for ch in label.upper() if ch.isalnum() or ch in " -&")[:12] or "QP"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#0b1020"/><stop offset="1" stop-color="#131a33"/>
  </linearGradient></defs>
  <rect width="1200" height="630" fill="url(#g)"/>
  <circle cx="1050" cy="120" r="220" fill="{accent}" opacity="0.14"/>
  <circle cx="120" cy="540" r="160" fill="{accent}" opacity="0.10"/>
  <polyline points="80,470 240,420 380,450 520,360 660,395 800,300 940,330 1120,210"
    fill="none" stroke="{accent}" stroke-width="6" stroke-linecap="round" opacity="0.9"/>
  <text x="80" y="200" font-family="Arial, sans-serif" font-size="92" font-weight="800"
    fill="#f4f6ff">{safe_label}</text>
  <text x="80" y="260" font-family="Arial, sans-serif" font-size="34" fill="{accent}"
    style="text-transform:uppercase" letter-spacing="6">{category.upper()[:24]}</text>
  <text x="80" y="580" font-family="Arial, sans-serif" font-size="28" fill="#8a93b5">
    QuantPulse — AI Market Intelligence</text>
</svg>"""
    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})
