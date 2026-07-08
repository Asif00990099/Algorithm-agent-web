"""Create tables (dev convenience — production uses Alembic) and seed the
first admin, default strategies and prompt templates."""
import json
import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models import PromptTemplate, Strategy, User, UserRole

logger = logging.getLogger(__name__)

DEFAULT_STRATEGIES = [
    {
        "name": "Trend Rider",
        "description": "EMA-alignment trend following with SuperTrend confirmation. "
                       "Best in strong directional markets.",
        "timeframe": "4h",
        "params": {"weights": {"trend": 0.45, "momentum": 0.15, "strength": 0.25,
                               "volatility": 0.05, "sentiment": 0.05, "funding": 0.05},
                   "thresholds": {"buy": 0.25, "sell": -0.25},
                   "sl_atr_mult": 2.0, "tp_atr_mult": 4.0},
    },
    {
        "name": "Mean Reversion",
        "description": "Bollinger + RSI oversold/overbought reversion for ranging markets.",
        "timeframe": "1h",
        "params": {"weights": {"trend": 0.10, "momentum": 0.40, "volatility": 0.30,
                               "strength": 0.05, "sentiment": 0.10, "funding": 0.05},
                   "thresholds": {"buy": 0.20, "sell": -0.20},
                   "sl_atr_mult": 1.2, "tp_atr_mult": 2.0},
    },
    {
        "name": "Momentum Breakout",
        "description": "MACD + ADX breakout continuation with trailing stop.",
        "timeframe": "1h",
        "params": {"weights": {"trend": 0.30, "momentum": 0.30, "strength": 0.25,
                               "volatility": 0.05, "sentiment": 0.05, "funding": 0.05},
                   "thresholds": {"buy": 0.28, "sell": -0.28},
                   "sl_atr_mult": 1.5, "tp_atr_mult": 3.5, "trailing_stop_pct": 2.5},
    },
    {
        "name": "Sentiment Contrarian",
        "description": "Fades extreme fear/greed and crowded funding when momentum diverges.",
        "timeframe": "4h",
        "params": {"weights": {"trend": 0.15, "momentum": 0.20, "volatility": 0.10,
                               "strength": 0.10, "sentiment": 0.25, "funding": 0.20},
                   "thresholds": {"buy": 0.18, "sell": -0.18},
                   "sl_atr_mult": 1.8, "tp_atr_mult": 3.0},
    },
]

DEFAULT_PROMPTS = [
    {"key": "signal_analysis",
     "description": "System prompt for LLM signal review",
     "content": "You are a risk-focused trading analyst. Review the quantitative evidence "
                "and either endorse or veto the proposed trade. Never invent data."},
    {"key": "news_rewrite",
     "description": "System prompt for the automated news rewriter",
     "content": "You are a financial news editor. Rewrite the given story as fully original "
                "content. Stay strictly factual to the provided material."},
]


async def init_db(create_all: bool = True) -> None:
    if create_all:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # Bootstrap admin keyed on FIRST_ADMIN_EMAIL. If it exists we re-assert
        # admin role + active and re-sync the password to FIRST_ADMIN_PASSWORD,
        # so a locked-out admin can always be recovered by setting that secret
        # and rebooting. (This only affects the bootstrap account.)
        admin_email = settings.FIRST_ADMIN_EMAIL.lower()
        admin = await db.scalar(select(User).where(User.email == admin_email))
        if admin is None:
            db.add(User(email=admin_email, username="admin",
                        hashed_password=hash_password(settings.FIRST_ADMIN_PASSWORD),
                        role=UserRole.ADMIN, is_verified=True, is_active=True,
                        demo_balance=settings.DEMO_STARTING_BALANCE,
                        demo_equity_high=settings.DEMO_STARTING_BALANCE))
            logger.info("Seeded first admin user %s", admin_email)
        else:
            admin.role = UserRole.ADMIN
            admin.is_active = True
            admin.hashed_password = hash_password(settings.FIRST_ADMIN_PASSWORD)
            logger.info("Re-synced bootstrap admin %s (role + password)", admin_email)

        for spec in DEFAULT_STRATEGIES:
            exists = await db.scalar(select(Strategy).where(Strategy.name == spec["name"]))
            if exists is None:
                db.add(Strategy(name=spec["name"], description=spec["description"],
                                timeframe=spec["timeframe"],
                                params=json.dumps(spec["params"]), is_active=True))

        for spec in DEFAULT_PROMPTS:
            exists = await db.scalar(select(PromptTemplate).where(PromptTemplate.key == spec["key"]))
            if exists is None:
                db.add(PromptTemplate(**spec))

        await db.commit()
