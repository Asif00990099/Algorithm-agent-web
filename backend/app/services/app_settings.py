"""Admin-managed application settings.

A schema-driven key/value system persisted in the `app_settings` table and
surfaced in the admin panel's Settings section. Every setting has a group,
type, label and default, so the UI can render grouped forms and the backend
can validate + coerce values. A Redis cache fronts reads so hot paths (e.g. the
maintenance-mode check in middleware) never hit the DB per request.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get, cache_set, get_redis

# type: text | textarea | bool | number | select | color
SETTINGS_SCHEMA: list[dict[str, Any]] = [
    # --- General ---
    {"key": "site_name", "group": "General", "type": "text", "label": "Site name", "default": "QuantPulse"},
    {"key": "site_tagline", "group": "General", "type": "text", "label": "Tagline", "default": "AI market intelligence"},
    {"key": "support_email", "group": "General", "type": "text", "label": "Support email", "default": ""},
    {"key": "default_theme", "group": "General", "type": "select", "label": "Default theme",
     "options": ["system", "light", "dark"], "default": "system"},

    # --- Branding ---
    {"key": "logo_url", "group": "Branding", "type": "text", "label": "Logo URL", "default": ""},
    {"key": "favicon_url", "group": "Branding", "type": "text", "label": "Favicon URL", "default": ""},
    {"key": "primary_color", "group": "Branding", "type": "color", "label": "Primary color", "default": "#6366f1"},

    # --- SEO ---
    {"key": "seo_title", "group": "SEO", "type": "text", "label": "Default SEO title", "default": "QuantPulse — AI Automated Trading Platform"},
    {"key": "seo_description", "group": "SEO", "type": "textarea", "label": "Meta description",
     "default": "Real-time markets, AI signals, automated trading and news — 24/7."},
    {"key": "seo_keywords", "group": "SEO", "type": "text", "label": "Meta keywords", "default": "AI trading, crypto signals, backtesting"},
    {"key": "og_image_url", "group": "SEO", "type": "text", "label": "Default OG image URL", "default": ""},

    # --- Email (SMTP; stored for future email delivery) ---
    {"key": "smtp_host", "group": "Email", "type": "text", "label": "SMTP host", "default": ""},
    {"key": "smtp_port", "group": "Email", "type": "number", "label": "SMTP port", "default": "587"},
    {"key": "smtp_user", "group": "Email", "type": "text", "label": "SMTP username", "default": ""},
    {"key": "email_from", "group": "Email", "type": "text", "label": "From address", "default": ""},

    # --- Security ---
    {"key": "enforce_2fa_admin", "group": "Security", "type": "bool", "label": "Require 2FA for admins", "default": "false"},
    {"key": "signup_enabled", "group": "Security", "type": "bool", "label": "Allow new sign-ups", "default": "true"},

    # --- Features (worker/behaviour toggles) ---
    {"key": "news_auto_publish", "group": "Features", "type": "bool", "label": "Auto-publish rewritten news", "default": "true"},
    {"key": "scanner_enabled", "group": "Features", "type": "bool", "label": "Market scanner enabled", "default": "true"},
    {"key": "signal_generation_enabled", "group": "Features", "type": "bool", "label": "AI signal generation enabled", "default": "true"},
    {"key": "live_trading_enabled", "group": "Features", "type": "bool", "label": "Allow live trading", "default": "false"},

    # --- Analytics ---
    {"key": "analytics_id", "group": "Analytics", "type": "text", "label": "Analytics measurement ID", "default": ""},

    # --- Maintenance ---
    {"key": "maintenance_mode", "group": "Maintenance", "type": "bool", "label": "Maintenance mode", "default": "false"},
    {"key": "maintenance_message", "group": "Maintenance", "type": "textarea", "label": "Maintenance message",
     "default": "QuantPulse is undergoing scheduled maintenance. Please check back shortly."},
]

_BY_KEY = {s["key"]: s for s in SETTINGS_SCHEMA}
_CACHE_KEY = "app_settings:all"


def _coerce(schema: dict, raw: str) -> Any:
    if schema["type"] == "bool":
        return str(raw).lower() in ("1", "true", "yes", "on")
    if schema["type"] == "number":
        try:
            return int(raw)
        except (TypeError, ValueError):
            return schema["default"]
    return raw


def validate(key: str, value: Any) -> str:
    """Validate + normalize a value to its stored string form."""
    schema = _BY_KEY.get(key)
    if schema is None:
        raise KeyError(key)
    if schema["type"] == "bool":
        return "true" if str(value).lower() in ("1", "true", "yes", "on") else "false"
    if schema["type"] == "number":
        int(value)  # raises ValueError on bad input
        return str(int(value))
    if schema["type"] == "select" and value not in schema.get("options", []):
        raise ValueError(f"{value!r} not in {schema['options']}")
    return str(value)


async def get_all(db: AsyncSession) -> dict[str, Any]:
    """All settings as {key: coerced_value}, defaults filled in."""
    from app.models import AppSetting

    rows = {r.key: r.value for r in (await db.execute(select(AppSetting))).scalars().all()}
    out: dict[str, Any] = {}
    for s in SETTINGS_SCHEMA:
        raw = rows.get(s["key"], s["default"])
        out[s["key"]] = _coerce(s, raw)
    return out


async def schema_with_values(db: AsyncSession) -> list[dict]:
    values = await get_all(db)
    return [{**s, "value": values[s["key"]]} for s in SETTINGS_SCHEMA]


async def set_many(db: AsyncSession, updates: dict[str, Any]) -> dict[str, Any]:
    from app.models import AppSetting

    applied = {}
    for key, value in updates.items():
        if key not in _BY_KEY:
            continue
        normalized = validate(key, value)
        row = await db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=normalized))
        else:
            row.value = normalized
        applied[key] = _coerce(_BY_KEY[key], normalized)
    await _bust_cache()
    return applied


async def _bust_cache() -> None:
    try:
        await get_redis().delete(_CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass


async def public_settings(db: AsyncSession) -> dict[str, Any]:
    """Non-secret settings safe to expose to the frontend (branding/SEO/flags).
    Cached in Redis; never includes SMTP or security internals."""
    cached = await cache_get(_CACHE_KEY)
    if cached is not None:
        return cached
    values = await get_all(db)
    public_groups = {"General", "Branding", "SEO", "Features", "Analytics", "Maintenance"}
    exposed = {s["key"]: values[s["key"]] for s in SETTINGS_SCHEMA if s["group"] in public_groups}
    await cache_set(_CACHE_KEY, exposed, ttl=60)
    return exposed


async def is_maintenance_mode(db: AsyncSession) -> tuple[bool, str]:
    values = await public_settings(db)
    return bool(values.get("maintenance_mode")), str(values.get("maintenance_message", ""))
