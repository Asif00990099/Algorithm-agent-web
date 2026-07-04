# Hugging Face Space (Docker SDK) — free, no credit card.
# This single file is all a Space needs: it clones the backend from GitHub and
# runs it on port 7860 (the Space default). To update after code changes,
# "Factory reboot" the Space.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN git clone --depth 1 https://github.com/Asif00990099/Algorithm-agent-web .

WORKDIR /app/backend
RUN pip install --no-cache-dir -r requirements.txt

# Hugging Face routes traffic to port 7860
ENV PORT=7860
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -sf http://localhost:7860/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
