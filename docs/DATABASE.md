# Database schema

PostgreSQL 16, SQLAlchemy 2 async models in `backend/app/models/`. All primary
keys are UUID strings; all timestamps are timezone-aware UTC. Naming conventions
are Alembic-compatible.

## Users & access

### users
| Column | Type | Notes |
|---|---|---|
| id | uuid pk | |
| email | varchar(255) | unique, indexed |
| username | varchar(64) | unique, indexed |
| hashed_password | varchar(255) | bcrypt |
| role | enum | admin / editor / trader / viewer |
| is_active, is_verified | bool | |
| totp_secret | varchar(64) | nullable |
| totp_enabled | bool | |
| demo_balance, demo_equity_high | float | paper account |
| risk_per_trade_pct, max_open_positions | float/int | risk prefs |
| last_login_at | timestamptz | |

### exchange_api_keys
User exchange credentials — `encrypted_key` / `encrypted_secret` are Fernet
ciphertext (AES-128-CBC + HMAC), never stored or returned in plaintext.
FK `user_id → users` (cascade), flags `is_testnet`, `is_active`.

### watchlist_items / price_alerts / notifications
Per-user market follows, above/below price triggers (worker-evaluated), and an
inbox (`kind`: info/signal/trade/alert/system, `is_read`).

### audit_logs
Append-only: `created_at` (indexed), `user_id`, `action` (indexed), `resource`,
`detail`, `ip_address`. Written on auth events and admin mutations.

## Trading & AI

### strategies
Name, description, owner, `params` (JSON: ensemble weights, thresholds, ATR
multipliers, trailing %), timeframe, `is_active`, `is_validated` (admin gate for
live trading), plus rolling performance: total/correct signals, win_rate,
profit_factor, sharpe_ratio, max_drawdown_pct, rank_score.

### signals
FK strategy; symbol (indexed), timeframe, action (buy/sell/hold),
price_at_signal, probability, confidence, risk_reward, stop_loss, take_profit,
trailing_stop_pct, `indicators_snapshot` (full JSON of all indicators at signal
time), sentiment_score, rationale, ai_provider, and the evaluation block:
evaluated, outcome_price, outcome_return_pct, was_correct, evaluated_at.

### trades
FK user/signal/strategy; mode (demo/live), status (open/closed/cancelled,
indexed), symbol (indexed), side, quantity, entry/exit price, SL/TP,
trailing_stop_pct + trailing_high_water, risk_pct, fee_paid, realized_pnl(_pct),
close_reason (tp/sl/trailing/manual/auto), exchange_order_id, opened/closed_at.

### backtest_runs
Symbol, timeframe, date range, initial balance, status, `report` JSON (metrics +
equity curve) and error text.

### model_evaluations
Learning-pipeline snapshots: strategy FK, window_hours, signals_evaluated,
accuracy, avg_return_pct.

## Content & intelligence

### articles
Title, unique slug (indexed), summary, markdown `content`, status enum
(draft/scheduled/published/archived, indexed), author/category FKs, full SEO
block (seo_title/description/keywords, featured_image_url), provenance
(`is_auto_generated`, source_name/url, unique `source_hash` for dedupe),
sentiment (-1..1), comma-separated symbols, scheduled_for, published_at
(indexed), view_count.

### categories / tags / article_tags
Slugged taxonomies; `article_tags` is the M2M join table.

### media_assets
CMS media library rows (filename, url, mime, size, uploader).

### sentiment_snapshots
Time series (created_at + symbol indexed): source (reddit/twitter/news/rss/
aggregate), score, positive/negative/neutral counts, sample_size. Partition by
month at scale.

### economic_events
Unique external_id; title, country, category (CPI/FOMC/NFP/GDP/RATES/
CENTRAL_BANK/DATA), importance 1–3, event_time (indexed), actual/forecast/
previous, source, url.

### prompt_templates / app_settings
Admin-editable AI prompts (unique key) and a key/value runtime settings store
(allow-listed keys such as `news_auto_publish`, `maintenance_mode`).

## Indexing & scale notes

- Hot paths are covered: signals(symbol, created_at), trades(user_id, status),
  articles(status, published_at), sentiment(symbol, created_at),
  audit_logs(created_at, action).
- For hundreds of millions of rows: monthly `PARTITION BY RANGE (created_at)` on
  signals, trades, sentiment_snapshots and audit_logs; move `indicators_snapshot`
  JSON to JSONB with compression; archive evaluated signals older than 90 days to
  cold storage.
- Dev bootstraps via `Base.metadata.create_all`; production should manage schema
  with Alembic (`alembic revision --autogenerate`).
