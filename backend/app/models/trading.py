"""Strategies, AI signals, trades (paper + live) and backtest runs."""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (Boolean, DateTime, Enum, Float, ForeignKey, Integer,
                        String, Text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SignalAction(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class TradeMode(str, enum.Enum):
    DEMO = "demo"
    LIVE = "live"


class TradeStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class Strategy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A tradeable strategy configuration. `params` is a JSON blob interpreted
    by the signal engine (indicator weights, thresholds, risk settings)."""
    __tablename__ = "strategies"

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    params: Mapped[str] = mapped_column(Text, default="{}", nullable=False)  # JSON
    timeframe: Mapped[str] = mapped_column(String(8), default="1h", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # gate for live trading

    # Rolling performance (updated by the evaluation pipeline)
    total_signals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_signals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    profit_factor: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sharpe_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rank_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    signals: Mapped[list["Signal"]] = relationship(back_populates="strategy")


class Signal(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """AI/quant generated trading signal with full risk plan and later outcome
    evaluation (feeds the learning pipeline)."""
    __tablename__ = "signals"

    strategy_id: Mapped[Optional[str]] = mapped_column(ForeignKey("strategies.id", ondelete="SET NULL"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), default="1h", nullable=False)
    action: Mapped[SignalAction] = mapped_column(Enum(SignalAction), nullable=False)

    price_at_signal: Mapped[float] = mapped_column(Float, nullable=False)
    probability: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)   # 0..1
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)    # 0..100
    risk_reward: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    stop_loss: Mapped[Optional[float]] = mapped_column(Float)
    take_profit: Mapped[Optional[float]] = mapped_column(Float)
    trailing_stop_pct: Mapped[Optional[float]] = mapped_column(Float)

    indicators_snapshot: Mapped[str] = mapped_column(Text, default="{}", nullable=False)  # JSON
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ai_provider: Mapped[str] = mapped_column(String(32), default="quant", nullable=False)

    # Outcome evaluation (learning loop)
    evaluated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    outcome_price: Mapped[Optional[float]] = mapped_column(Float)
    outcome_return_pct: Mapped[Optional[float]] = mapped_column(Float)
    was_correct: Mapped[Optional[bool]] = mapped_column(Boolean)
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    strategy: Mapped[Optional["Strategy"]] = relationship(back_populates="signals")


class Trade(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A position (demo or live). OPEN rows are monitored by the trade monitor
    worker which applies SL/TP/trailing-stop and auto-close rules."""
    __tablename__ = "trades"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    signal_id: Mapped[Optional[str]] = mapped_column(ForeignKey("signals.id", ondelete="SET NULL"))
    strategy_id: Mapped[Optional[str]] = mapped_column(ForeignKey("strategies.id", ondelete="SET NULL"))

    mode: Mapped[TradeMode] = mapped_column(Enum(TradeMode), default=TradeMode.DEMO, nullable=False)
    status: Mapped[TradeStatus] = mapped_column(Enum(TradeStatus), default=TradeStatus.OPEN, index=True, nullable=False)

    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)          # long | short
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[Optional[float]] = mapped_column(Float)

    stop_loss: Mapped[Optional[float]] = mapped_column(Float)
    take_profit: Mapped[Optional[float]] = mapped_column(Float)
    trailing_stop_pct: Mapped[Optional[float]] = mapped_column(Float)
    trailing_high_water: Mapped[Optional[float]] = mapped_column(Float)   # best price seen since entry

    risk_pct: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    fee_paid: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    realized_pnl: Mapped[Optional[float]] = mapped_column(Float)
    realized_pnl_pct: Mapped[Optional[float]] = mapped_column(Float)
    close_reason: Mapped[Optional[str]] = mapped_column(String(32))       # tp|sl|trailing|manual|auto|liquidation

    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(64))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)


class BacktestRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "backtest_runs"

    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    strategy_id: Mapped[Optional[str]] = mapped_column(ForeignKey("strategies.id", ondelete="SET NULL"))
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    initial_balance: Mapped[float] = mapped_column(Float, default=10_000.0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending|running|done|failed
    report: Mapped[str] = mapped_column(Text, default="{}", nullable=False)             # JSON metrics + equity curve
    error: Mapped[Optional[str]] = mapped_column(Text)


class ModelEvaluation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Daily snapshot of prediction accuracy per strategy — the AI learning
    pipeline uses these to re-rank strategies and tune signal weights."""
    __tablename__ = "model_evaluations"

    strategy_id: Mapped[Optional[str]] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"), index=True)
    window_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    signals_evaluated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accuracy: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_return_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
