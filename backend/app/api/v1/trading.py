"""Trading endpoints: open/close positions (demo & live), history and
performance stats. Signals & strategies live in signals.py."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_trader
from app.db.session import get_db
from app.models import Trade, TradeMode, TradeStatus, User
from app.schemas.common import OpenTradeRequest, TradeOut
from app.services.trading.engine import TradingError, close_trade, open_trade

router = APIRouter(prefix="/trading", tags=["trading"])


@router.post("/trades", response_model=TradeOut, status_code=201)
async def create_trade(body: OpenTradeRequest, user: User = Depends(require_trader),
                       db: AsyncSession = Depends(get_db)):
    try:
        trade = await open_trade(
            db, user, symbol=body.symbol, side=body.side,
            mode=TradeMode(body.mode), risk_pct=body.risk_pct,
            quantity=body.quantity, stop_loss=body.stop_loss,
            take_profit=body.take_profit, trailing_stop_pct=body.trailing_stop_pct,
            signal_id=body.signal_id, notes=body.notes)
    except TradingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await db.commit()
    await db.refresh(trade)
    return trade


@router.post("/trades/{trade_id}/close", response_model=TradeOut)
async def close_position(trade_id: str, user: User = Depends(require_trader),
                         db: AsyncSession = Depends(get_db)):
    trade = await db.get(Trade, trade_id)
    if trade is None or trade.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trade not found")
    try:
        trade = await close_trade(db, user, trade, reason="manual")
    except TradingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await db.commit()
    await db.refresh(trade)
    return trade


@router.get("/trades", response_model=list[TradeOut])
async def list_trades(status_filter: Optional[str] = Query(None, alias="status"),
                      mode: Optional[str] = None,
                      limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                      user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    q = select(Trade).where(Trade.user_id == user.id)
    if status_filter in ("open", "closed", "cancelled"):
        q = q.where(Trade.status == TradeStatus(status_filter))
    if mode in ("demo", "live"):
        q = q.where(Trade.mode == TradeMode(mode))
    rows = (await db.execute(q.order_by(Trade.opened_at.desc()).limit(limit).offset(offset))
            ).scalars().all()
    return rows


@router.get("/performance")
async def performance(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Win rate, profit factor, expectancy and drawdown across closed trades."""
    closed = (await db.execute(
        select(Trade).where(Trade.user_id == user.id, Trade.status == TradeStatus.CLOSED)
        .order_by(Trade.closed_at))).scalars().all()
    if not closed:
        return {"closed_trades": 0, "message": "No closed trades yet"}

    pnls = [t.realized_pnl or 0.0 for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    equity = user.demo_balance
    curve, running = [], 0.0
    peak = dd = 0.0
    for t in closed:
        running += t.realized_pnl or 0.0
        peak = max(peak, running)
        dd = min(dd, running - peak)
        curve.append({"time": t.closed_at, "cumulative_pnl": round(running, 2)})

    by_reason: dict[str, int] = {}
    for t in closed:
        by_reason[t.close_reason or "unknown"] = by_reason.get(t.close_reason or "unknown", 0) + 1

    return {
        "closed_trades": len(closed),
        "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(closed) * 100, 2),
        "total_pnl": round(sum(pnls), 2),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else round(gross_profit, 3),
        "expectancy": round(sum(pnls) / len(pnls), 4),
        "avg_win": round(sum(wins) / len(wins), 4) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 4) if losses else 0.0,
        "max_drawdown": round(dd, 2),
        "close_reasons": by_reason,
        "equity_curve": curve[-200:],
        "current_demo_balance": round(equity, 2),
    }
