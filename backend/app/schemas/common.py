"""Pydantic schemas shared across the API surface."""
from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int


# ------------------------------------------------------------------- auth

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_\-]+$")
    password: str = Field(min_length=10, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v) or not any(c.isalpha() for c in v):
            raise ValueError("Password must contain both letters and digits")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class TwoFactorSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class TwoFactorVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class UserOut(ORMModel):
    id: str
    email: EmailStr
    username: str
    role: str
    is_active: bool
    totp_enabled: bool
    demo_balance: float
    risk_per_trade_pct: float
    max_open_positions: int
    created_at: datetime


class UserUpdateRequest(BaseModel):
    risk_per_trade_pct: Optional[float] = Field(None, ge=0.1, le=10)
    max_open_positions: Optional[int] = Field(None, ge=1, le=50)


class AdminUserUpdateRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    demo_balance: Optional[float] = Field(None, ge=0)


# ----------------------------------------------------------------- trading

class OpenTradeRequest(BaseModel):
    symbol: str = Field(min_length=5, max_length=20)
    side: str = Field(pattern="^(long|short)$")
    mode: str = Field(default="demo", pattern="^(demo|live)$")
    risk_pct: Optional[float] = Field(None, ge=0.1, le=10)
    quantity: Optional[float] = Field(None, gt=0)
    stop_loss: Optional[float] = Field(None, gt=0)
    take_profit: Optional[float] = Field(None, gt=0)
    trailing_stop_pct: Optional[float] = Field(None, ge=0.1, le=50)
    signal_id: Optional[str] = None
    notes: str = ""


class TradeOut(ORMModel):
    id: str
    mode: str
    status: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    trailing_stop_pct: Optional[float]
    risk_pct: float
    fee_paid: float
    realized_pnl: Optional[float]
    realized_pnl_pct: Optional[float]
    close_reason: Optional[str]
    opened_at: datetime
    closed_at: Optional[datetime]
    notes: str


class SignalOut(ORMModel):
    id: str
    strategy_id: Optional[str]
    symbol: str
    timeframe: str
    action: str
    price_at_signal: float
    probability: float
    confidence: float
    risk_reward: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    trailing_stop_pct: Optional[float]
    sentiment_score: Optional[float]
    rationale: str
    ai_provider: str
    evaluated: bool
    was_correct: Optional[bool]
    outcome_return_pct: Optional[float]
    created_at: datetime


class StrategyIn(BaseModel):
    name: str = Field(min_length=3, max_length=128)
    description: str = ""
    params: dict = Field(default_factory=dict)
    timeframe: str = Field(default="1h", pattern="^(1m|5m|15m|30m|1h|4h|1d|1w)$")
    is_active: bool = True


class StrategyOut(ORMModel):
    id: str
    name: str
    description: str
    timeframe: str
    is_active: bool
    is_validated: bool
    total_signals: int
    win_rate: float
    profit_factor: float
    sharpe_ratio: float
    max_drawdown_pct: float
    rank_score: float
    created_at: datetime


class BacktestRequest(BaseModel):
    symbol: str = Field(min_length=5, max_length=20)
    timeframe: str = Field(default="1h", pattern="^(1m|5m|15m|30m|1h|4h|1d|1w)$")
    limit: int = Field(default=1000, ge=100, le=1000)
    initial_balance: float = Field(default=10_000, ge=100)
    strategy_id: Optional[str] = None
    params: dict = Field(default_factory=dict)
    allow_short: bool = True


# --------------------------------------------------------------------- cms

class ArticleIn(BaseModel):
    title: str = Field(min_length=5, max_length=300)
    summary: str = ""
    content: str = ""
    status: str = Field(default="draft", pattern="^(draft|scheduled|published|archived)$")
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    seo_title: str = ""
    seo_description: str = ""
    seo_keywords: str = ""
    featured_image_url: str = ""
    scheduled_for: Optional[datetime] = None


class ArticleOut(ORMModel):
    id: str
    title: str
    slug: str
    summary: str
    content: str
    status: str
    seo_title: str
    seo_description: str
    seo_keywords: str
    featured_image_url: str
    is_auto_generated: bool
    source_name: str
    source_url: str
    sentiment: Optional[float]
    symbols: str
    published_at: Optional[datetime]
    view_count: int
    created_at: datetime


class WatchlistIn(BaseModel):
    symbol: str = Field(min_length=2, max_length=20)
    asset_type: str = Field(default="crypto", pattern="^(crypto|stock|forex)$")
    is_favorite: bool = False


class AlertIn(BaseModel):
    symbol: str = Field(min_length=2, max_length=20)
    condition: str = Field(pattern="^(above|below)$")
    target_price: float = Field(gt=0)


class ApiKeyIn(BaseModel):
    exchange: str = Field(default="binance", max_length=32)
    label: str = Field(default="default", max_length=64)
    api_key: str = Field(min_length=10, max_length=256)
    api_secret: str = Field(min_length=10, max_length=256)
    is_testnet: bool = True
