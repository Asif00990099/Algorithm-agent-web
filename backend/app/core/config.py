"""Application configuration loaded from environment variables / .env file."""
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Application ---
    APP_NAME: str = "QuantPulse AI Trading Platform"
    ENVIRONMENT: str = "development"  # development | staging | production
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Security ---
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    # Fernet key for encrypting stored exchange API keys (openssl rand -base64 32)
    ENCRYPTION_KEY: str = ""
    RATE_LIMIT_PER_MINUTE: int = 120
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://quantpulse:quantpulse@localhost:5432/quantpulse"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_ECHO: bool = False

    # --- Redis / Celery ---
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # --- Initial admin (seeded on first boot) ---
    FIRST_ADMIN_EMAIL: str = "admin@quantpulse.local"
    FIRST_ADMIN_PASSWORD: str = "ChangeMe!12345"

    # --- Market data API keys (all optional; free tiers) ---
    COINGECKO_API_KEY: str = ""          # demo key raises rate limits
    BINANCE_API_KEY: str = ""            # only needed for live trading
    BINANCE_API_SECRET: str = ""
    BINANCE_BASE_URL: str = "https://api.binance.com"
    BINANCE_TESTNET_BASE_URL: str = "https://testnet.binance.vision"
    ALPHA_VANTAGE_API_KEY: str = ""
    FINNHUB_API_KEY: str = ""
    FMP_API_KEY: str = ""
    FRED_API_KEY: str = ""

    # --- News / social API keys (optional) ---
    NEWSAPI_API_KEY: str = ""
    MARKETAUX_API_KEY: str = ""
    CRYPTOPANIC_API_KEY: str = ""
    TWITTER_BEARER_TOKEN: str = ""
    REDDIT_USER_AGENT: str = "QuantPulse/1.0 (market research bot)"

    # --- AI providers (optional; platform degrades to quant-only mode) ---
    AI_PROVIDER: str = "none"            # openai | anthropic | local | none
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-5"
    LOCAL_LLM_BASE_URL: str = "http://localhost:11434/v1"  # Ollama-compatible
    LOCAL_LLM_MODEL: str = "llama3.1"

    # --- Trading defaults ---
    LIVE_TRADING_ENABLED: bool = False
    DEMO_STARTING_BALANCE: float = 100_000.0
    MAX_RISK_PER_TRADE_PCT: float = 2.0
    MAX_OPEN_POSITIONS: int = 10
    DEFAULT_QUOTE_ASSET: str = "USDT"

    # --- Worker cadence (seconds) ---
    MARKET_SYNC_INTERVAL: int = 60
    SCANNER_INTERVAL: int = 60
    SIGNAL_INTERVAL: int = 300
    NEWS_INTERVAL: int = 600
    SENTIMENT_INTERVAL: int = 600
    CALENDAR_INTERVAL: int = 3600
    TRADE_MONITOR_INTERVAL: int = 30

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @field_validator("SECRET_KEY")
    @classmethod
    def _warn_default_secret(cls, v: str) -> str:
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
