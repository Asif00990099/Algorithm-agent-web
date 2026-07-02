"""QuantPulse — AI Automated Trading Platform API."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.core.cache import rate_limit_check
from app.core.config import settings
from app.core.deps import client_ip
from app.db.init_db import init_db
from app.services.market.http import close_http

from app.api.v1 import admin, auth, content, intel, market, signals, trading, users, ws

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("%s started (%s)", settings.APP_NAME, settings.ENVIRONMENT)
    yield
    await close_http()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Enterprise AI trading platform: real-time market data, AI signals, "
                "automated news, portfolio management, backtesting and automated trading.",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers_and_rate_limit(request: Request, call_next):
    # global per-IP rate limit (auth endpoints add their own stricter one)
    if request.url.path.startswith(settings.API_V1_PREFIX):
        allowed = await rate_limit_check(f"global:{client_ip(request)}",
                                         settings.RATE_LIMIT_PER_MINUTE)
        if not allowed:
            return ORJSONResponse({"detail": "Rate limit exceeded"},
                                  status_code=status.HTTP_429_TOO_MANY_REQUESTS)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security",
                                    "max-age=63072000; includeSubDomains")
    return response


API = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=API)
app.include_router(users.router, prefix=API)
app.include_router(market.router, prefix=API)
app.include_router(trading.router, prefix=API)
app.include_router(signals.router, prefix=API)
app.include_router(signals.strategies_router, prefix=API)
app.include_router(signals.backtest_router, prefix=API)
app.include_router(content.router, prefix=API)
app.include_router(content.cms_router, prefix=API)
app.include_router(content.media_router, prefix=API)
app.include_router(intel.router, prefix=API)
app.include_router(admin.router, prefix=API)
app.include_router(ws.router, prefix=API)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENVIRONMENT}
