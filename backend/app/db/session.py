"""Async SQLAlchemy engine and session factory.

Handles the connection-string quirks of managed Postgres providers (Supabase,
Neon, Heroku) so a user can paste their pooler URL verbatim into DATABASE_URL:

* ``postgres://`` / ``postgresql://`` are coerced to the asyncpg driver in
  ``config._normalize_db_url``.
* libpq query params that asyncpg does not understand (``sslmode``, ``ssl``,
  ``channel_binding``, ``pgbouncer``…) are stripped and translated into
  asyncpg ``connect_args``.
* Managed hosts require TLS, so an SSL context is attached automatically.
* PgBouncer / Supabase *transaction* pooler (port 6543) does not support the
  prepared statements asyncpg caches, so statement caching is disabled there.

The URL is parsed with SQLAlchemy's ``make_url`` rather than ``urllib.parse``:
recent CPython 3.11 security patches make ``urlsplit`` raise ValueError on
valid pooler hostnames (e.g. ``aws-1-ap-southeast-2.pooler.supabase.com``).

Resilience: on a single-service deploy (Hugging Face, one container) a bad
DATABASE_URL — wrong password, unreachable host — must not crash-loop the whole
app into a dead "Runtime error" page. At import we probe the configured Postgres
once; if it is unreachable we log ONE clear line and fall back to a local SQLite
file so the site still boots (data is not persistent until Postgres works).
"""
import asyncio
import logging
import os
import ssl
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

logger = logging.getLogger(__name__)

# asyncpg takes SSL / statement-cache settings via connect_args, NOT via the URL
# query string (those are libpq/psycopg options). Drop them from the URL here.
_ASYNCPG_STRIP = ("sslmode", "ssl", "channel_binding", "pgbouncer",
                  "options", "target_session_attrs")
_MANAGED_HOSTS = ("supabase.co", "supabase.com", "pooler.supabase.com",
                  "neon.tech", "render.com", "amazonaws.com")

# Local fallback when the managed Postgres cannot be reached. Prefer the mounted
# /data dir (Hugging Face) so the file survives soft restarts; else cwd.
_SQLITE_FALLBACK = ("sqlite+aiosqlite:////data/quantpulse.db"
                    if os.path.isdir("/data") else "sqlite+aiosqlite:///./quantpulse_fallback.db")


def _build_engine_args(raw_url: str):
    """Return a cleaned SQLAlchemy URL + engine kwargs for the target database."""
    kwargs: dict = {"echo": settings.DB_ECHO, "pool_pre_ping": True}

    if raw_url.startswith("sqlite"):
        return raw_url, kwargs

    url = make_url(raw_url)
    kwargs.update(pool_size=settings.DB_POOL_SIZE, max_overflow=settings.DB_MAX_OVERFLOW)

    query = dict(url.query)
    sslmode = str(query.get("sslmode", "")).lower()
    wants_ssl = (sslmode not in ("", "disable")) or ("ssl" in query)
    # strip libpq-only params asyncpg would choke on
    url = url.difference_update_query(_ASYNCPG_STRIP)

    host = (url.host or "").lower()
    is_managed = any(h in host for h in _MANAGED_HOSTS)
    connect_args: dict = {}

    if is_managed or wants_ssl:
        ctx = ssl.create_default_context()
        # Poolers present certs that may not match the CN/SAN from every region;
        # encryption is still enforced, we just don't verify the hostname/chain.
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ctx

    # Supabase transaction pooler (6543) + any PgBouncer front end can't reuse
    # asyncpg's prepared statements — disable the cache to avoid errors.
    if url.port == 6543 or str(query.get("pgbouncer", "")).lower() == "true":
        connect_args["statement_cache_size"] = 0

    if connect_args:
        kwargs["connect_args"] = connect_args
    return url, kwargs


def _postgres_reachable(eng) -> bool:
    """Open one connection and run SELECT 1. Returns False (with a clear log) on
    any failure so the caller can fall back to local storage. Disposes the pool
    afterwards so the app's real event loop starts with fresh connections.

    The probe runs in a dedicated thread with its own event loop: at import time
    uvicorn already has a running loop on the main thread, so ``asyncio.run``
    there would raise. A separate thread lets the probe run regardless."""
    import concurrent.futures

    def _worker():
        async def _probe():
            try:
                async with eng.connect() as conn:
                    await conn.execute(text("SELECT 1"))
            finally:
                await eng.dispose()
        asyncio.run(asyncio.wait_for(_probe(), timeout=12))

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            ex.submit(_worker).result(timeout=20)
        return True
    except Exception as exc:  # noqa: BLE001 — any failure means "not usable"
        msg = str(exc) or exc.__class__.__name__
        logger.error("=" * 70)
        logger.error("DATABASE CONNECTION FAILED: %s", msg)
        if "password" in msg.lower():
            logger.error("→ The DATABASE_URL password is wrong. Reset it in Supabase "
                         "(Settings → Database → Reset password) and update the secret.")
        elif "does not exist" in msg.lower() or "translate host" in msg.lower():
            logger.error("→ The DATABASE_URL host is wrong. Use the Supabase 'Session "
                         "pooler' string (…pooler.supabase.com), not the Direct one.")
        else:
            logger.error("→ Check the DATABASE_URL secret (host, port, password, SSL).")
        logger.error("Falling back to LOCAL SQLite (%s). The app will run, but data will "
                     "NOT persist across reboots until Postgres connects.", _SQLITE_FALLBACK)
        logger.error("=" * 70)
        return False


def _make_engine():
    _url, engine_kwargs = _build_engine_args(settings.DATABASE_URL)
    eng = create_async_engine(_url, **engine_kwargs)
    if not settings.DATABASE_URL.startswith("sqlite") and not _postgres_reachable(eng):
        eng = create_async_engine(_SQLITE_FALLBACK, echo=settings.DB_ECHO, pool_pre_ping=True)
    return eng


engine = _make_engine()

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
