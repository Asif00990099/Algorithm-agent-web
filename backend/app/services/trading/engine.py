"""Trading engine: position sizing, demo (paper) execution against live
prices, live execution via Binance signed API, and the open-position monitor
that enforces SL / TP / trailing stops and auto-close.

All prices come from the live exchange feed — paper trades fill at the real
market price at execution time.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decrypt_secret
from app.models import (ExchangeApiKey, Notification, Trade, TradeMode,
                        TradeStatus, User)
from app.services.market.binance import get_price, signed_request

logger = logging.getLogger(__name__)

TAKER_FEE = 0.001  # 0.1 % — Binance spot default, applied to demo fills too


class TradingError(Exception):
    pass


@dataclass
class PositionSize:
    quantity: float
    notional: float
    risk_amount: float


def compute_position_size(balance: float, price: float, stop_loss: Optional[float],
                          risk_pct: float, max_leverage: float = 1.0) -> PositionSize:
    """Risk-based sizing: risk `risk_pct`% of balance between entry and stop.
    Falls back to fixed-fraction sizing when no stop is given."""
    if balance <= 0 or price <= 0:
        raise TradingError("Insufficient balance")
    risk_amount = balance * (risk_pct / 100.0)
    if stop_loss and stop_loss > 0 and abs(price - stop_loss) > 1e-12:
        per_unit_risk = abs(price - stop_loss)
        quantity = risk_amount / per_unit_risk
    else:
        quantity = (balance * (risk_pct / 100.0) * 10) / price  # 10x fixed-fraction proxy
    notional = quantity * price
    max_notional = balance * max_leverage * 0.95  # leave margin for fees
    if notional > max_notional:
        quantity = max_notional / price
        notional = quantity * price
    if notional < 10:  # exchange min-notional style floor
        raise TradingError("Position below minimum notional (10 USDT)")
    return PositionSize(round(quantity, 8), round(notional, 2), round(risk_amount, 2))


async def open_trade(db: AsyncSession, user: User, *, symbol: str, side: str,
                     mode: TradeMode, risk_pct: Optional[float] = None,
                     quantity: Optional[float] = None,
                     stop_loss: Optional[float] = None,
                     take_profit: Optional[float] = None,
                     trailing_stop_pct: Optional[float] = None,
                     signal_id: Optional[str] = None,
                     strategy_id: Optional[str] = None,
                     notes: str = "") -> Trade:
    if side not in ("long", "short"):
        raise TradingError("side must be 'long' or 'short'")
    if mode == TradeMode.LIVE and not settings.LIVE_TRADING_ENABLED:
        raise TradingError("Live trading is disabled on this deployment")

    open_count = await db.scalar(
        select(func.count(Trade.id)).where(Trade.user_id == user.id,
                                           Trade.status == TradeStatus.OPEN))
    if (open_count or 0) >= user.max_open_positions:
        raise TradingError(f"Max open positions reached ({user.max_open_positions})")

    price = await get_price(symbol)
    if price is None:
        raise TradingError(f"No live price available for {symbol}")

    risk = min(risk_pct or user.risk_per_trade_pct, settings.MAX_RISK_PER_TRADE_PCT)

    if quantity is None:
        balance = user.demo_balance if mode == TradeMode.DEMO else await _live_quote_balance(db, user)
        sizing = compute_position_size(balance, price, stop_loss, risk)
        quantity = sizing.quantity
    notional = quantity * price
    fee = notional * TAKER_FEE

    if mode == TradeMode.DEMO:
        if notional + fee > user.demo_balance:
            raise TradingError("Insufficient demo balance")
        user.demo_balance -= (notional + fee) if side == "long" else fee
        exchange_order_id = None
    else:
        exchange_order_id = await _live_market_order(db, user, symbol, side, quantity)

    trade = Trade(
        user_id=user.id, signal_id=signal_id, strategy_id=strategy_id,
        mode=mode, status=TradeStatus.OPEN, symbol=symbol.upper(), side=side,
        quantity=quantity, entry_price=price, stop_loss=stop_loss,
        take_profit=take_profit, trailing_stop_pct=trailing_stop_pct,
        trailing_high_water=price, risk_pct=risk, fee_paid=round(fee, 8),
        exchange_order_id=exchange_order_id,
        opened_at=datetime.now(timezone.utc), notes=notes,
    )
    db.add(trade)
    db.add(Notification(user_id=user.id, kind="trade",
                        title=f"{mode.value.upper()} {side.upper()} opened: {symbol.upper()}",
                        body=f"qty {quantity:.6f} @ {price} | SL {stop_loss} TP {take_profit}"))
    await db.flush()
    return trade


async def close_trade(db: AsyncSession, user: User, trade: Trade,
                      reason: str = "manual", price: Optional[float] = None) -> Trade:
    if trade.status != TradeStatus.OPEN:
        raise TradingError("Trade already closed")
    exit_price = price if price is not None else await get_price(trade.symbol)
    if exit_price is None:
        raise TradingError(f"No live price available for {trade.symbol}")

    if trade.mode == TradeMode.LIVE:
        close_side = "short" if trade.side == "long" else "long"
        await _live_market_order(db, user, trade.symbol, close_side, trade.quantity)

    direction = 1.0 if trade.side == "long" else -1.0
    gross = (exit_price - trade.entry_price) * trade.quantity * direction
    fee = exit_price * trade.quantity * TAKER_FEE
    pnl = gross - fee
    cost_basis = trade.entry_price * trade.quantity

    trade.status = TradeStatus.CLOSED
    trade.exit_price = exit_price
    trade.realized_pnl = round(pnl, 8)
    trade.realized_pnl_pct = round(pnl / cost_basis * 100, 4) if cost_basis else 0.0
    trade.fee_paid = round(trade.fee_paid + fee, 8)
    trade.close_reason = reason
    trade.closed_at = datetime.now(timezone.utc)

    if trade.mode == TradeMode.DEMO:
        if trade.side == "long":
            user.demo_balance += exit_price * trade.quantity - fee
        else:
            user.demo_balance += pnl
        user.demo_equity_high = max(user.demo_equity_high, user.demo_balance)

    db.add(Notification(user_id=user.id, kind="trade",
                        title=f"Position closed ({reason}): {trade.symbol}",
                        body=f"PnL {pnl:+.2f} USDT ({trade.realized_pnl_pct:+.2f}%)"))
    await db.flush()
    return trade


async def monitor_open_trade(db: AsyncSession, user: User, trade: Trade) -> Optional[str]:
    """Apply SL/TP/trailing rules against the live price. Returns the close
    reason when the position was closed, else None."""
    price = await get_price(trade.symbol)
    if price is None:
        return None

    long = trade.side == "long"
    # trailing stop: ratchet the high-water mark, close on retrace
    if trade.trailing_stop_pct:
        if trade.trailing_high_water is None:
            trade.trailing_high_water = trade.entry_price
        improved = price > trade.trailing_high_water if long else price < trade.trailing_high_water
        if improved:
            trade.trailing_high_water = price
        retrace = ((trade.trailing_high_water - price) / trade.trailing_high_water * 100 if long
                   else (price - trade.trailing_high_water) / trade.trailing_high_water * 100)
        profitable = price > trade.entry_price if long else price < trade.entry_price
        if retrace >= trade.trailing_stop_pct and profitable:
            await close_trade(db, user, trade, "trailing", price)
            return "trailing"

    if trade.stop_loss is not None:
        if (long and price <= trade.stop_loss) or (not long and price >= trade.stop_loss):
            await close_trade(db, user, trade, "sl", price)
            return "sl"
    if trade.take_profit is not None:
        if (long and price >= trade.take_profit) or (not long and price <= trade.take_profit):
            await close_trade(db, user, trade, "tp", price)
            return "tp"
    return None


# ------------------------------------------------------------ live plumbing

async def _get_live_credentials(db: AsyncSession, user: User) -> tuple[str, str, bool]:
    row = (await db.execute(
        select(ExchangeApiKey).where(ExchangeApiKey.user_id == user.id,
                                     ExchangeApiKey.exchange == "binance",
                                     ExchangeApiKey.is_active.is_(True))
        .order_by(ExchangeApiKey.created_at.desc()))).scalars().first()
    if row is None:
        raise TradingError("No active Binance API key configured")
    key = decrypt_secret(row.encrypted_key)
    secret = decrypt_secret(row.encrypted_secret)
    if not key or not secret:
        raise TradingError("Stored API credentials could not be decrypted")
    return key, secret, row.is_testnet


async def _live_quote_balance(db: AsyncSession, user: User) -> float:
    key, secret, testnet = await _get_live_credentials(db, user)
    account = await signed_request("GET", "/api/v3/account", key, secret, testnet=testnet)
    for b in account.get("balances", []):
        if b.get("asset") == settings.DEFAULT_QUOTE_ASSET:
            return float(b.get("free", 0))
    return 0.0


async def _live_market_order(db: AsyncSession, user: User, symbol: str,
                             side: str, quantity: float) -> str:
    key, secret, testnet = await _get_live_credentials(db, user)
    order = await signed_request(
        "POST", "/api/v3/order", key, secret,
        params={"symbol": symbol.upper(), "side": "BUY" if side == "long" else "SELL",
                "type": "MARKET", "quantity": f"{quantity:.8f}".rstrip("0").rstrip(".")},
        testnet=testnet)
    logger.info("Live order executed: %s", order.get("orderId"))
    return str(order.get("orderId", ""))
