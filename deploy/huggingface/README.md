---
title: QuantPulse API
emoji: 📈
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# QuantPulse backend (Hugging Face Space)

This Space runs the QuantPulse FastAPI backend. It is created by copying the two
files in this folder (`Dockerfile` + this `README.md`) into a new **Docker** Space.

## Create the Space
1. https://huggingface.co/new-space → SDK: **Docker** → Blank → Create (free, no card).
2. Add these two files to the Space (upload or paste):
   - `Dockerfile` (from this folder)
   - `README.md` (this file — the front-matter above sets `app_port: 7860`)
3. **Settings → Variables and secrets** → add as **Secrets**:
   - `SECRET_KEY`, `ENCRYPTION_KEY`, `ENVIRONMENT=production`
   - `ALLOWED_ORIGINS=https://algorithm-agent-web.vercel.app`
   - `FIRST_ADMIN_EMAIL`, `FIRST_ADMIN_PASSWORD`
   - `DATABASE_URL` = your Supabase/Neon Postgres URL (ends with `?ssl=require`)
   - any data API keys (`COINGECKO_API_KEY`, …) — or add them later in `/admin`
4. The Space builds and starts. Its URL is `https://<user>-<space>.hf.space`.

## Connect the frontend (Vercel)
Set `NEXT_PUBLIC_API_URL=https://<user>-<space>.hf.space` and
`NEXT_PUBLIC_WS_URL=wss://<user>-<space>.hf.space/api/v1/ws/stream`, then redeploy.

To update the backend after pushing code to GitHub: open the Space →
**⋮ → Factory reboot** (it re-clones `main`).
