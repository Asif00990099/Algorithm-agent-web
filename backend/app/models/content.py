"""CMS: articles (auto-published rewritten news + editorial posts),
categories, tags, media, sentiment snapshots and economic events."""
import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (Boolean, Column, DateTime, Enum, Float, ForeignKey,
                        Integer, String, Table, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

article_tags = Table(
    "article_tags",
    Base.metadata,
    Column("article_id", ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class ArticleStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Category(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    articles: Mapped[List["Article"]] = relationship(back_populates="category")


class Tag(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)


class Article(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Original rewritten content. `source_url`/`source_name` credit the
    original reporting; `content` is always a rewrite, never a copy."""
    __tablename__ = "articles"
    __table_args__ = (UniqueConstraint("source_hash", name="uq_articles_source_hash"),)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)      # markdown

    status: Mapped[ArticleStatus] = mapped_column(Enum(ArticleStatus), default=ArticleStatus.DRAFT, index=True)
    author_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    category_id: Mapped[Optional[str]] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), index=True)

    # SEO
    seo_title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    seo_description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    seo_keywords: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    featured_image_url: Mapped[str] = mapped_column(String(600), default="", nullable=False)

    # Provenance / automation
    is_auto_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    source_url: Mapped[str] = mapped_column(String(600), default="", nullable=False)
    source_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)   # dedupe key
    sentiment: Mapped[Optional[float]] = mapped_column(Float)                    # -1..1
    symbols: Mapped[str] = mapped_column(String(255), default="", nullable=False)  # comma-separated tickers

    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    category: Mapped[Optional["Category"]] = relationship(back_populates="articles")
    tags: Mapped[List["Tag"]] = relationship(secondary=article_tags)


class MediaAsset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "media_assets"

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(600), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), default="image/png", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    uploaded_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class SentimentSnapshot(Base, UUIDPrimaryKeyMixin):
    """Aggregated social sentiment per symbol/source, written every cycle."""
    __tablename__ = "sentiment_snapshots"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)   # or "MARKET"
    source: Mapped[str] = mapped_column(String(32), nullable=False)               # reddit|twitter|news|rss|aggregate
    score: Mapped[float] = mapped_column(Float, nullable=False)                   # -1..1
    positive: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    negative: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    neutral: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class EconomicEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "economic_events"
    __table_args__ = (UniqueConstraint("external_id", name="uq_economic_events_external_id"),)

    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    country: Mapped[str] = mapped_column(String(8), default="US", nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="", nullable=False)  # CPI|FOMC|NFP|GDP|...
    importance: Mapped[int] = mapped_column(Integer, default=1, nullable=False)     # 1..3
    event_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    actual: Mapped[Optional[str]] = mapped_column(String(64))
    forecast: Mapped[Optional[str]] = mapped_column(String(64))
    previous: Mapped[Optional[str]] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    url: Mapped[str] = mapped_column(String(600), default="", nullable=False)


class PromptTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Admin-manageable prompts used by the AI agent and news rewriter."""
    __tablename__ = "prompt_templates"

    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # e.g. news_rewrite, signal_analysis
    content: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AppSetting(Base, TimestampMixin):
    """Key/value store for runtime-tunable platform settings (AI provider,
    worker toggles, feature flags) editable from the admin dashboard."""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)
