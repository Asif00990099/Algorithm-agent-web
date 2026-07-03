# Architecture

## System overview

```
                        ┌─────────────────────────────────────────────┐
                        │                 Browser                     │
                        │   Next.js 14 · React · Tailwind · LW Charts │
                        └───────────────┬───────────────┬─────────────┘
                                REST (JWT)         WebSocket
                                        │               │
┌───────────────────────────────────────▼───────────────▼─────────────────────┐
│                              FastAPI (uvicorn)                               │
│  auth · users · market · trading · signals · strategies · backtest · news    │
│  cms · intel · admin · ws        rate-limit middleware · security headers    │
└──────┬──────────────┬───────────────────────────┬──────────────┬────────────┘
       │              │                           │              │
   PostgreSQL      Redis 7                  External APIs    Binance WS
   (SQLAlchemy   cache · pub/sub ·      CoinGecko/Binance/  (miniTicker
    async)       rate limits            AV/Finnhub/FMP/FRED  relay)
       ▲              ▲                 NewsAPI/CryptoPanic/
       │              │                 Marketaux/RSS/Reddit/X
┌──────┴──────────────┴────────────────────────────────────────────┐
│                     Celery worker + beat                          │
│  market_sync 60s · scanner 60s · signal_cycle 5m · news 10m       │
│  sentiment 10m · calendar 1h · trade_monitor 30s · evaluation 1h  │
│  publish_scheduled 5m                                             │
└───────────────────────────────────────────────────────────────────┘
```

## Data flow

### Market data
User traffic never hits external APIs directly. The `market_sync` worker warms
Redis every minute (top-100 coins, global stats, tickers, fear/greed); API
handlers read through the same `cached_get_json` layer, so a cache hit is served
in microseconds and a miss transparently refreshes. Failures return `None`
upstream → HTTP 503/404 with an explicit message, never stale fabrications.

### AI signal pipeline
1. `signal_cycle` iterates active strategies × watched symbols.
2. For each pair, the agent pulls 300 live candles, computes the full
   `IndicatorSnapshot` (20+ indicators), optionally social sentiment + funding.
3. A weighted ensemble produces a score in [-1, 1]; strategy `params` JSON
   overrides weights/thresholds — this is the tuning surface for the learning
   loop.
4. Score → action (buy/sell/hold), probability (calibrated sigmoid), confidence
   (score × data quality), and an ATR-based risk plan (SL clamped to structure
   levels, TP, trailing %, R:R).
5. Optional LLM review (OpenAI/Anthropic/local): the model may **veto** or
   annotate, never originate a trade.
6. Signals persist with a full indicator snapshot for later audit.

### Learning loop
`evaluate_signals` (hourly) scores every signal ≥ 4h old against the live price,
marks correctness, and updates per-strategy accuracy/win-rate/rank. Backtest runs
feed profit factor/Sharpe/drawdown into the same rank score. The strategy
leaderboard (UI + API) reflects this continuously. Live trading is additionally
gated on the admin-only `is_validated` flag.

### Trading engine
- **Sizing**: risk-based — `risk% × balance / |entry − stop|`, capped by balance
  and a 10-USDT min-notional floor.
- **Demo**: fills at the live Binance price, applies 0.1% taker fees, adjusts the
  user's demo balance atomically in the same transaction.
- **Live**: signed Binance spot orders (testnet by default) using the user's own
  Fernet-encrypted API keys; blocked entirely unless `LIVE_TRADING_ENABLED=true`.
- **Monitor** (30s): trailing-stop ratchet with high-water mark, SL/TP checks,
  auto-close, notifications, Redis `trades` events.

### News desk
`news_cycle` (10 min): collect from RSS (keyless) + NewsAPI/CryptoPanic/Marketaux
→ dedupe by SHA-256 of (title, url) → rewrite via LLM (strict JSON contract) or
the template engine → SEO fields, category detection, tag extraction, sentiment
score, self-hosted SVG OG image → auto-publish (toggleable via app settings) →
`news` pub/sub event. Scheduled editorial posts are released by
`publish_scheduled` every 5 minutes.

### Real-time layer
One `ConnectionManager` holds all client sockets with topic subscriptions:
- `prices:SYMBOL` — relayed from a single shared Binance `!miniTicker@arr` stream.
- `signals`, `news`, `scanner`, `trades`, `alerts` — Redis pub/sub events emitted
  by workers.
Both pumps auto-reconnect with backoff; a dead client is pruned on first failed
send.

## Scaling path

| Concern | Now | At scale |
|---|---|---|
| API | 2 uvicorn workers | Horizontal replicas behind ALB; WS sticky or move fan-out to a dedicated gateway |
| Workers | 1 worker × 4 concurrency | Queue-per-domain (market/news/trading), autoscaled |
| DB | single Postgres | Read replicas; monthly partitions on `signals`, `trades`, `sentiment_snapshots`, `audit_logs` |
| Cache | single Redis | Redis Cluster; keep rate-limit keys local to each API pod |
| Market data | shared HTTP cache | Dedicated ingest service writing to Redis Streams |

## Key design decisions

- **Quant core, LLM optional** — the platform must work with zero AI keys, and an
  LLM must never fabricate market facts. Hence deterministic scoring with LLM as
  reviewer/writer only.
- **Pure-NumPy TA** — no TA-Lib system dependency; indicators are unit-tested and
  identical between live agent and backtester (one code path, no drift).
- **No-lookahead backtests** — signals computed on bar *i* fill at bar *i+1* open;
  SL/TP evaluated intra-bar against high/low; fees on both sides.
- **Fail-open rate limiting / fail-closed trading** — Redis loss degrades limits
  (availability) but trading errors always abort the order (safety).
- **create_all in dev, Alembic in prod** — models are the schema source of truth;
  generate migrations with `alembic revision --autogenerate` when evolving prod.
