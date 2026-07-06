"""Async SQLAlchemy engine and session factory.

Handles the connection-string quirks of managed Postgres providers (Supabase,
Neon, Heroku) so a user can paste their pooler URL verbatim into DATABASE_URL:

* ``postgres://`` / ``postgresql://`` are coerced to the asyncpg driver in
  ``config._normalize_db_url``.
* libpq query params that asyncpg does not understand (``sslmode``, ``ssl``,
  ``channel_binding``, ``pgbouncer``…) are stripped from the URL and translated
  into asyncpg ``connect_args``.
* Managed hosts require TLS, so an SSL context is attached automatically.
* PgBouncer / Supabase *transaction* pooler (port 6543) does not support the
  prepared statements asyncpg caches, so statement caching is disabled there.
"""
import ssl
from typing import AsyncGenerator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# asyncpg takes SSL / statement-cache settings via connect_args, NOT via the URL
# query string (those are libpq/psycopg options). Drop them from the URL here.
_ASYNCPG_STRIP = {"sslmode", "ssl", "channel_binding", "pgbouncer",
                  "options", "target_session_attrs"}
_MANAGED_HOSTS = ("supabase.co", "supabase.com", "pooler.supabase.com",
                  "neon.tech", "render.com", "amazonaws.com")


def _build_engine_args(url: str) -> tuple[str, dict]:
    """Return a cleaned URL + engine kwargs suited to the target database."""
    kwargs: dict = {"echo": settings.DB_ECHO, "pool_pre_ping": True}

    if url.startswith("sqlite"):
        return url, kwargs

    kwargs.update(pool_size=settings.DB_POOL_SIZE, max_overflow=settings.DB_MAX_OVERFLOW)

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    wants_ssl = query.get("sslmode", "") not in ("disable",) or bool(query.get("ssl"))
    # strip libpq-only params asyncpg would choke on
    cleaned_q = {k: v for k, v in query.items() if k.lower() not in _ASYNCPG_STRIP}
    cleaned_url = urlunsplit(parts._replace(query=urlencode(cleaned_q)))

    host = (parts.hostname or "").lower()
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
    if parts.port == 6543 or query.get("pgbouncer") == "true":
        connect_args["statement_cache_size"] = 0

    if connect_args:
        kwargs["connect_args"] = connect_args
    return cleaned_url, kwargs


_url, engine_kwargs = _build_engine_args(settings.DATABASE_URL)

engine = create_async_engine(_url, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
