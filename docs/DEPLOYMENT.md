# Deployment guide

## 0. Vercel (frontend)

The Next.js frontend deploys to Vercel as-is; the backend (FastAPI + Celery +
PostgreSQL + Redis + WebSockets) **cannot run on Vercel's serverless platform**
and must live on a container host (sections 1–2 below, or Railway/Render/Fly).

1. Import the repo in Vercel and set **Root Directory = `frontend`**
   (framework auto-detects as Next.js; no vercel.json needed).
2. Set environment variables in the Vercel project (they are baked into the
   client bundle at build time — redeploy after changing them):
   - `NEXT_PUBLIC_API_URL=https://api.your-domain.com`
   - `NEXT_PUBLIC_WS_URL=wss://api.your-domain.com/api/v1/ws/stream`
3. On the backend, add the Vercel domain to `ALLOWED_ORIGINS`
   (e.g. `https://your-app.vercel.app,https://your-domain.com`).

Until a backend URL is configured the UI deploys fine and renders graceful
"data unavailable" states — no fake data is ever shown.

## 1. Docker Compose (single host)

```bash
cp .env.example .env
# REQUIRED for anything public:
#   SECRET_KEY=$(openssl rand -hex 32)
#   ENCRYPTION_KEY=$(openssl rand -base64 32)
#   POSTGRES_PASSWORD=<strong password>
#   FIRST_ADMIN_PASSWORD=<strong password>
#   ENVIRONMENT=production
#   ALLOWED_ORIGINS=https://your-domain.com
#   NEXT_PUBLIC_API_URL=https://api.your-domain.com
#   NEXT_PUBLIC_WS_URL=wss://api.your-domain.com/api/v1/ws/stream
docker compose up -d --build
```

Services: `postgres`, `redis`, `api` (:8000), `worker`, `beat`, `web` (:3000).
Put nginx/Caddy/Traefik in front for TLS; proxy `/` → web:3000 and
`api.` subdomain (or `/api`) → api:8000 with WebSocket upgrade enabled:

```nginx
location /api/v1/ws/ {
    proxy_pass http://api:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
}
```

## 2. AWS reference architecture

| Component | Service |
|---|---|
| Containers | ECS Fargate (api ×2, worker ×1, beat ×1, web ×2) or a single EC2 + Compose to start |
| Images | ECR (`docker build backend/`, `docker build frontend/`) |
| Load balancer | ALB — HTTPS via ACM, target groups for web + api, WS idle timeout ≥ 300s, sticky sessions on the api target group (WebSockets) |
| Database | RDS PostgreSQL 16 (Multi-AZ for prod), automated backups + PITR |
| Cache/queue | ElastiCache Redis 7 |
| Secrets | Secrets Manager / SSM Parameter Store → injected as env vars (never bake keys into images) |
| Logs & metrics | CloudWatch Logs (json), alarms on 5xx rate, worker task failures, Redis/DB memory |
| DNS/CDN | Route 53 + CloudFront in front of the web target (cache `_next/static`) |

Steps:
1. Create VPC (2 AZ), RDS + ElastiCache in private subnets.
2. Push both images to ECR; create an ECS task per service with the same env
   (DATABASE_URL, REDIS_URL, CELERY_*, SECRET_KEY, ENCRYPTION_KEY, API keys).
3. Run one-off task `python -c "import asyncio; from app.db.init_db import init_db; asyncio.run(init_db())"`
   (or just let the api seed on first boot).
4. Point ALB listeners: 443 → web TG; `api.domain` 443 → api TG (health check
   `/api/health`).
5. Set the frontend build args `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_WS_URL` to the
   public API origin **at image build time** (they are compiled into the bundle).

## 3. CI/CD

`.github/workflows/ci.yml` runs on every push/PR: ruff + 38 pytest cases,
Next.js production build, and both Docker image builds. Extend for CD by adding
an ECR push + `aws ecs update-service --force-new-deployment` job gated on the
main branch.

## 4. Production hardening checklist

- [ ] `SECRET_KEY` and `ENCRYPTION_KEY` set from a secrets manager (rotating
      `ENCRYPTION_KEY` requires re-encrypting stored exchange keys)
- [ ] `ENVIRONMENT=production` (enables HSTS), `DEBUG=false`
- [ ] `ALLOWED_ORIGINS` restricted to the real frontend origin
- [ ] First admin password changed; 2FA enabled on all admin accounts
- [ ] `LIVE_TRADING_ENABLED=false` until strategies are validated on testnet
- [ ] RDS: enforce TLS, least-privilege app user, automated backups verified
- [ ] Alembic adopted for schema migrations before the first prod schema change
- [ ] Log aggregation + alerting on Celery beat gaps (no `worker:last_market_sync`
      key in Redis for >5 min means the pipeline is stalled)
- [ ] Off-site Postgres dumps (`pg_dump` nightly) and Redis AOF persistence
- [ ] External API keys are free-tier: watch 429s in logs and raise cache TTLs
      or upgrade tiers as traffic grows

## 5. Operations

- **Scale reads**: add api replicas — all market data is Redis-cached, so extra
  replicas are cheap.
- **Scale workers**: split queues (`-Q market`, `-Q news`, `-Q trading`) and run
  dedicated workers when a single one saturates; beat stays a singleton.
- **Watchlist tuning**: `WATCHED_SYMBOLS` in `app/workers/tasks.py` (or extend to
  read from app settings) controls which pairs get automated signals.
- **Interval tuning**: every cadence is an env var (`MARKET_SYNC_INTERVAL`,
  `SIGNAL_INTERVAL`, `NEWS_INTERVAL`, `TRADE_MONITOR_INTERVAL`, …).
