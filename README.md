# QuantPulse — AI Automated Trading Platform

An enterprise-grade, 24/7 AI trading ecosystem: real-time market monitoring across
crypto/stocks/forex, an explainable AI signal engine, automated trading (demo + live),
strategy backtesting, a continuous learning pipeline, an automated news desk with
original SEO content, social sentiment analysis, an economic calendar, a market
scanner and a full admin dashboard.

## Highlights

- **Real-time data, no fake data** — CoinGecko, Binance spot/futures public APIs,
  Alternative.me Fear & Greed, Reddit, RSS and central-bank feeds work with **zero
  API keys**. Optional free-tier keys unlock Alpha Vantage, Finnhub, FMP, FRED,
  NewsAPI, Marketaux, CryptoPanic and X. Every endpoint returns live data or an
  explicit "unavailable" — never placeholders.
- **AI agent** — a deterministic quant ensemble (trend, momentum, volatility,
  strength, sentiment, funding) computed from 20+ indicators, with optional LLM
  review (OpenAI / Claude / local Ollama-compatible). The LLM can veto trades and
  enrich rationale, but can never invent data. Signals ship with probability,
  confidence, stop-loss, take-profit, trailing stop and risk:reward.
- **Learning pipeline** — every signal is evaluated against the market after a
  4-hour horizon; strategy win rates, profit factors and rank scores update
  continuously, and only admin-validated strategies may drive live trading.
- **Automated trading** — risk-based position sizing, demo fills at live prices,
  Binance live/testnet executor with Fernet-encrypted user API keys, and a 30-second
  monitor enforcing SL/TP/trailing/auto-close.
- **Automated news desk** — aggregates dozens of sources every 10 minutes, rewrites
  each story into original content (LLM or template engine), generates SEO
  title/description/tags/category/featured image and auto-publishes. Never copies
  source text; always links attribution.
- **Everything real-time** — one WebSocket endpoint streams Binance prices plus
  platform events (signals, news, scanner, trades, alerts) fanned out via Redis
  pub/sub.

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS, TradingView Lightweight Charts |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2 (async), Pydantic v2 |
| AI | OpenAI / Anthropic Claude / local LLM (Ollama-compatible), quant ensemble core |
| Data | PostgreSQL 16, Redis 7 (cache, rate limiting, pub/sub) |
| Jobs | Celery + Celery Beat (market sync, scanner, signals, news, sentiment, calendar, trade monitor, evaluation) |
| Infra | Docker Compose, GitHub Actions CI, AWS deployment guide |

## Quick start

```bash
cp .env.example .env          # optionally add free API keys
docker compose up --build
```

- Web app: http://localhost:3000
- API docs (Swagger): http://localhost:8000/api/docs
- First admin: `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` from `.env` — change immediately.

### Local development (no Docker)

```bash
# backend
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload           # needs postgres+redis, or set
                                                  # DATABASE_URL=sqlite+aiosqlite:///dev.db
# workers (separate shells)
.venv/bin/celery -A app.workers.celery_app worker -l info
.venv/bin/celery -A app.workers.celery_app beat -l info

# frontend
cd frontend && npm install && npm run dev
```

### Tests

```bash
cd backend && .venv/bin/pytest -q     # 38 tests: indicators, backtest, sentiment, security, API
```

## Repository layout

```
backend/
  app/
    api/v1/        REST + WebSocket routers (auth, market, trading, signals,
                   strategies, backtest, news, cms, intel, admin, ws)
    core/          config, security (JWT/2FA/encryption), deps, redis cache
    db/            async engine, base models, init/seed
    models/        SQLAlchemy models (users, trading, content)
    schemas/       Pydantic request/response models
    services/
      indicators/  pure-NumPy TA library (RSI, MACD, ADX, Ichimoku, SuperTrend, …)
      market/      CoinGecko, Binance, Alpha Vantage/Finnhub/FMP/FRED, Fear&Greed
      ai/          LLM providers + trading agent (ensemble scoring, risk plans)
      news/        aggregator + original-content rewriter (SEO)
      sentiment/   lexicon analyzer + Reddit/X/RSS collectors
      trading/     sizing, demo/live execution, position monitor
      backtest/    bar-by-bar simulator + performance metrics
      scanner/     full-market sweep (gainers, whales, breakouts, listings)
      calendar/    FRED releases + Fed/ECB/BoE/BoJ feeds
    workers/       Celery app + beat schedule + tasks
    ws/            WebSocket connection manager (Binance relay + Redis pubsub)
  tests/
frontend/
  src/app/         pages: home, markets, coin/[symbol], scanner, signals,
                   trading, backtest, portfolio, news, calendar, admin, auth
  src/components/  Navbar, CandleChart, UI primitives
  src/lib/         API client (JWT refresh), hooks (polling + WebSocket), formatting
docs/              ARCHITECTURE, DATABASE, API, DEPLOYMENT
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — system design, data flow, automation cycles
- [Database schema](docs/DATABASE.md) — every table, index and relationship
- [API reference](docs/API.md) — endpoints, auth, WebSocket protocol
- [Deployment guide](docs/DEPLOYMENT.md) — Docker, AWS, hardening checklist

## Security

JWT access/refresh tokens, TOTP 2FA, bcrypt password hashing, Fernet-encrypted
exchange API keys, role-based access control (admin/editor/trader/viewer), Redis
sliding-window rate limiting (tighter on auth), strict CORS, security headers,
audit logging, SQLAlchemy parameterized queries and Pydantic input validation
throughout. Live trading is disabled by default (`LIVE_TRADING_ENABLED=false`)
and gated behind admin-validated strategies.

## Disclaimer

QuantPulse is market-analysis software. Nothing it produces is financial advice.
Trading cryptocurrencies and other instruments involves substantial risk of loss.
Always validate strategies in demo/testnet mode before considering live capital.
