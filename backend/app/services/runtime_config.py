"""Runtime API-key resolution.

API keys can come from two places:
  1. Environment variables (loaded into `settings` at startup) — the classic path.
  2. The admin panel's "API Management" section — stored Fernet-encrypted in the
     `api_credentials` table.

DB-stored keys take precedence and are applied directly onto the live `settings`
singleton, so every service that reads `settings.COINGECKO_API_KEY` (etc.) picks
them up immediately — no redeploy, no per-service wiring. This module owns the
provider→setting mapping and the apply/reset logic.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

# Admin-facing provider id -> (settings attribute, human label, signup URL, category)
PROVIDERS: dict[str, dict[str, str]] = {
    "coingecko":     {"attr": "COINGECKO_API_KEY",   "label": "CoinGecko",        "url": "https://www.coingecko.com/en/developers/dashboard", "category": "Crypto"},
    "alpha_vantage": {"attr": "ALPHA_VANTAGE_API_KEY","label": "Alpha Vantage",    "url": "https://www.alphavantage.co/support/#api-key",     "category": "Stocks/Forex"},
    "finnhub":       {"attr": "FINNHUB_API_KEY",      "label": "Finnhub",          "url": "https://finnhub.io/register",                      "category": "Stocks"},
    "fmp":           {"attr": "FMP_API_KEY",          "label": "Financial Modeling Prep", "url": "https://site.financialmodelingprep.com/developer/docs", "category": "Stocks"},
    "fred":          {"attr": "FRED_API_KEY",         "label": "FRED (macro)",     "url": "https://fred.stlouisfed.org/docs/api/api_key.html","category": "Macro"},
    "newsapi":       {"attr": "NEWSAPI_API_KEY",      "label": "NewsAPI",          "url": "https://newsapi.org/register",                     "category": "News"},
    "marketaux":     {"attr": "MARKETAUX_API_KEY",    "label": "Marketaux",        "url": "https://www.marketaux.com",                        "category": "News"},
    "cryptopanic":   {"attr": "CRYPTOPANIC_API_KEY",  "label": "CryptoPanic",      "url": "https://cryptopanic.com/developers/api",           "category": "News"},
    "twitter":       {"attr": "TWITTER_BEARER_TOKEN", "label": "X / Twitter",      "url": "https://developer.x.com",                          "category": "Social"},
    "openai":        {"attr": "OPENAI_API_KEY",       "label": "OpenAI",           "url": "https://platform.openai.com/api-keys",             "category": "AI"},
    "anthropic":     {"attr": "ANTHROPIC_API_KEY",    "label": "Anthropic (Claude)","url": "https://console.anthropic.com/settings/keys",    "category": "AI"},
    "binance_key":   {"attr": "BINANCE_API_KEY",      "label": "Binance API key",  "url": "https://www.binance.com/en/my/settings/api-management", "category": "Trading"},
    "binance_secret":{"attr": "BINANCE_API_SECRET",   "label": "Binance API secret","url": "https://www.binance.com/en/my/settings/api-management","category": "Trading"},
}

# Snapshot the original env-provided values ONCE at import time, so deleting a
# DB override can cleanly restore whatever was set via the environment.
_ENV_DEFAULTS: dict[str, str] = {
    pid: getattr(settings, meta["attr"], "") or "" for pid, meta in PROVIDERS.items()
}


def mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}…{value[-4:]}"


async def apply_credentials_to_settings(db: AsyncSession) -> int:
    """Load every active DB credential, decrypt it and set it on `settings`.
    Returns the number of providers overridden. Called on startup and after
    each admin change."""
    from app.models import ApiCredential

    rows = (await db.execute(select(ApiCredential).where(ApiCredential.is_active.is_(True)))).scalars().all()
    applied = 0
    for row in rows:
        meta = PROVIDERS.get(row.provider)
        if not meta:
            continue
        value = decrypt_secret(row.encrypted_value)
        if value is None:
            logger.warning("Could not decrypt stored credential for %s", row.provider)
            continue
        setattr(settings, meta["attr"], value)
        applied += 1
    if applied:
        logger.info("Applied %d API credential(s) from the database", applied)
    return applied


async def set_credential(db: AsyncSession, provider: str, value: str) -> None:
    """Encrypt + upsert a provider key and apply it to the live settings."""
    from app.models import ApiCredential

    meta = PROVIDERS[provider]
    row = await db.get(ApiCredential, provider)
    if row is None:
        row = ApiCredential(provider=provider, encrypted_value=encrypt_secret(value), is_active=True)
        db.add(row)
    else:
        row.encrypted_value = encrypt_secret(value)
        row.is_active = True
    setattr(settings, meta["attr"], value)


async def delete_credential(db: AsyncSession, provider: str) -> None:
    """Remove a DB override and restore the original environment value."""
    from app.models import ApiCredential

    row = await db.get(ApiCredential, provider)
    if row is not None:
        await db.delete(row)
    setattr(settings, PROVIDERS[provider]["attr"], _ENV_DEFAULTS.get(provider, ""))


async def list_status(db: AsyncSession) -> list[dict]:
    """Report each provider's configuration status for the admin UI (masked)."""
    from app.models import ApiCredential

    db_rows = {r.provider: r for r in (await db.execute(select(ApiCredential))).scalars().all()}
    out = []
    for pid, meta in PROVIDERS.items():
        current = getattr(settings, meta["attr"], "") or ""
        in_db = pid in db_rows
        source = "database" if in_db else ("environment" if _ENV_DEFAULTS.get(pid) else "none")
        out.append({
            "provider": pid,
            "label": meta["label"],
            "category": meta["category"],
            "signup_url": meta["url"],
            "configured": bool(current),
            "masked": mask(current),
            "source": source,
        })
    return out
