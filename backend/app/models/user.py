"""User accounts, roles, exchange API keys, audit logs and notifications."""
import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    TRADER = "trader"
    VIEWER = "viewer"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.TRADER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 2FA
    totp_secret: Mapped[Optional[str]] = mapped_column(String(64))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Demo trading account
    demo_balance: Mapped[float] = mapped_column(Float, default=100_000.0, nullable=False)
    demo_equity_high: Mapped[float] = mapped_column(Float, default=100_000.0, nullable=False)

    # Risk preferences
    risk_per_trade_pct: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    max_open_positions: Mapped[int] = mapped_column(default=5, nullable=False)

    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    api_keys: Mapped[List["ExchangeApiKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    watchlist_items: Mapped[List["WatchlistItem"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    alerts: Mapped[List["PriceAlert"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class ExchangeApiKey(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Exchange credentials, stored encrypted with Fernet (never plaintext)."""
    __tablename__ = "exchange_api_keys"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), default="binance", nullable=False)
    label: Mapped[str] = mapped_column(String(64), default="default", nullable=False)
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    is_testnet: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship(back_populates="api_keys")


class WatchlistItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "watchlist_items"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)      # e.g. BTCUSDT
    asset_type: Mapped[str] = mapped_column(String(16), default="crypto", nullable=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship(back_populates="watchlist_items")


class PriceAlert(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "price_alerts"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    condition: Mapped[str] = mapped_column(String(8), nullable=False)    # above | below
    target_price: Mapped[float] = mapped_column(Float, nullable=False)
    is_triggered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="alerts")


class AuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_logs"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    resource: Mapped[Optional[str]] = mapped_column(String(128))
    detail: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notifications"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="info", nullable=False)  # info|signal|trade|alert|system
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
