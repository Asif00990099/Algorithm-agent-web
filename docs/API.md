# API reference

Base URL: `/api/v1` · Interactive docs: `/api/docs` (Swagger) · Health: `/api/health`

Authentication: `Authorization: Bearer <access_token>`. Access tokens live 30
minutes; exchange the refresh token at `/auth/refresh`. Global rate limit is 120
req/min/IP (10/min on auth endpoints).

## Auth
| Method | Path | Notes |
|---|---|---|
| POST | /auth/register | email, username, password (≥10 chars, letters+digits) |
| POST | /auth/login | + optional `totp_code` when 2FA enabled → access/refresh tokens |
| POST | /auth/refresh | rotate tokens |
| POST | /auth/2fa/setup 🔒 | returns TOTP secret + otpauth:// URI |
| POST | /auth/2fa/verify 🔒 | activate 2FA with a valid code |
| POST | /auth/2fa/disable 🔒 | requires valid code |

## Users (🔒)
| Method | Path | Notes |
|---|---|---|
| GET/PATCH | /users/me | profile; risk %, max positions |
| GET | /users/me/portfolio | equity, unrealized/realized PnL, open positions marked live |
| GET/POST/DELETE | /users/me/watchlist[/{id}] | |
| GET/POST/DELETE | /users/me/alerts[/{id}] | above/below price triggers |
| GET/POST/DELETE | /users/me/api-keys[/{id}] | exchange keys (stored encrypted; metadata only returned) |
| GET | /users/me/notifications | `?unread_only=true` |
| POST | /users/me/notifications/{id}/read | |

## Market data (public)
| Method | Path | Notes |
|---|---|---|
| GET | /market/overview | global stats + top coins + fear/greed + trending |
| GET | /market/coins | `?page&per_page&vs_currency` (rank, price, mcap, volume, 24h/7d/30d, sparkline, ATH/ATL) |
| GET | /market/coins/{id} | full CoinGecko detail |
| GET | /market/coins/{id}/chart | `?days` price/volume series |
| GET | /market/search?q= | |
| GET | /market/klines/{symbol} | Binance OHLCV `?interval&limit` |
| GET | /market/indicators/{symbol} | full snapshot: SMA/EMA/VWAP, RSI, MACD, Stoch RSI, ATR, ADX, Bollinger, Ichimoku, SuperTrend, S/R, fib, trend strength, momentum |
| GET | /market/ticker/{symbol} | 24h stats |
| GET | /market/orderbook/{symbol} | book + spread/liquidity/imbalance metrics |
| GET | /market/derivatives/{symbol} | funding rate + open interest |
| GET | /market/fear-greed | history `?limit` |
| GET | /market/macro | FRED series (CPI, PPI, NFP, rates, GDP, unemployment) |
| GET | /market/stocks/{symbol} | Finnhub quote/profile + Alpha Vantage daily |
| GET | /market/forex/{pair} | e.g. EURUSD |
| GET | /market/scanner | gainers, losers, most active, volume, volatility, breakouts/downs, whale prints, new listings |

## Signals, strategies, backtesting
| Method | Path | Notes |
|---|---|---|
| GET | /signals | `?symbol&action&limit&offset`, includes outcome evaluation |
| POST 🔒 | /signals/analyze/{symbol} | run the AI agent on demand (`?timeframe`) |
| GET | /strategies | leaderboard, ranked |
| POST/PATCH 🔒 | /strategies[/{id}] | params JSON: weights, thresholds, ATR multipliers |
| POST 🔒(admin) | /strategies/{id}/validate | gate for live trading |
| POST 🔒 | /backtest/run | symbol, timeframe, limit ≤1000, balance, strategy_id → metrics, trades, equity curve, monthly returns |
| GET 🔒 | /backtest/runs | history |

## Trading (🔒 trader role)
| Method | Path | Notes |
|---|---|---|
| POST | /trading/trades | symbol, side long/short, mode demo/live, risk_pct or quantity, SL/TP/trailing |
| POST | /trading/trades/{id}/close | manual close at live price |
| GET | /trading/trades | `?status&mode&limit&offset` |
| GET | /trading/performance | win rate, profit factor, expectancy, drawdown, equity curve |

## News & CMS
| Method | Path | Notes |
|---|---|---|
| GET | /news | published articles `?category&tag&q&page` |
| GET | /news/categories | |
| GET | /news/{slug} | article + tags, increments views |
| GET/POST/PATCH/DELETE 🔒(editor) | /cms/articles[/{id}] | full CMS incl. scheduling + SEO |
| GET | /media/og-image?label=&category= | branded SVG featured image |

## Intelligence
| Method | Path | Notes |
|---|---|---|
| GET | /intel/sentiment/{symbol} | stored snapshots (48h) |
| GET | /intel/social/reddit?subreddit= | live posts + per-post & aggregate sentiment |
| GET | /intel/social/twitter?q= | requires TWITTER_BEARER_TOKEN |
| GET | /intel/social/rss?feed= | CoinDesk, Cointelegraph, Decrypt, Reuters, CNBC… |
| GET | /intel/calendar | `?country&importance` — FOMC/CPI/NFP/central banks |

## Admin (🔒 admin role)
`/admin/stats`, `/admin/users` (+PATCH role/active/balance), `/admin/audit-logs`,
`/admin/prompts` (+PUT upsert), `/admin/settings/{key}` (allow-listed runtime settings).

## WebSocket

`ws(s)://host/api/v1/ws/stream`

```jsonc
→ {"op": "subscribe", "topics": ["prices:BTCUSDT", "signals", "news", "scanner", "trades", "alerts"]}
← {"op": "subscribed", "topics": [...]}
← {"topic": "prices:BTCUSDT", "data": {"symbol": "BTCUSDT", "price": "97123.40", ...}}
← {"topic": "signals", "data": {"type": "new_signal", "symbol": "ETHUSDT", "action": "buy", ...}}
→ {"op": "ping"}  ← {"op": "pong"}
```

Errors are JSON: `{"detail": "message"}` with appropriate HTTP status
(401 unauthenticated, 403 forbidden, 404 missing, 409 conflict, 422 validation,
429 rate-limited, 503 upstream data source unavailable).
