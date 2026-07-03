"""AI signals & strategy management + on-demand analysis and backtesting."""
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_admin, require_trader
from app.db.session import get_db
from app.models import BacktestRun, Signal, SignalAction, Strategy, User
from app.schemas.common import BacktestRequest, SignalOut, StrategyIn, StrategyOut
from app.services.ai.agent import analyze_symbol
from app.services.backtest.engine import run_backtest
from app.services.market.binance import get_klines, klines_to_ohlcv

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=list[SignalOut])
async def list_signals(symbol: Optional[str] = None, action: Optional[str] = None,
                       limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                       db: AsyncSession = Depends(get_db)):
    q = select(Signal)
    if symbol:
        q = q.where(Signal.symbol == symbol.upper())
    if action in ("buy", "sell", "hold"):
        q = q.where(Signal.action == SignalAction(action))
    rows = (await db.execute(q.order_by(Signal.created_at.desc()).limit(limit).offset(offset))
            ).scalars().all()
    return rows


@router.post("/analyze/{symbol}")
async def analyze(symbol: str, timeframe: str = Query("1h", pattern="^(5m|15m|30m|1h|4h|1d)$"),
                  persist: bool = True,
                  user: User = Depends(require_trader),
                  db: AsyncSession = Depends(get_db)):
    """Run the full AI agent pipeline on demand for any symbol."""
    decision = await analyze_symbol(symbol.upper(), timeframe)
    if decision is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f"Unable to analyze {symbol}: no live candle data")
    if persist:
        sig = Signal(
            symbol=decision.symbol, timeframe=decision.timeframe,
            action=SignalAction(decision.action), price_at_signal=decision.price,
            probability=decision.probability, confidence=decision.confidence,
            risk_reward=decision.risk_reward, stop_loss=decision.stop_loss,
            take_profit=decision.take_profit, trailing_stop_pct=decision.trailing_stop_pct,
            indicators_snapshot=json.dumps(decision.indicators, default=str),
            sentiment_score=decision.sentiment_score, rationale=decision.rationale,
            ai_provider=decision.ai_provider)
        db.add(sig)
        await db.commit()
    return decision.to_dict()


# ------------------------------------------------------------------ strategies

strategies_router = APIRouter(prefix="/strategies", tags=["strategies"])


@strategies_router.get("", response_model=list[StrategyOut])
async def list_strategies(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Strategy).order_by(Strategy.rank_score.desc()))
            ).scalars().all()
    return rows


@strategies_router.post("", response_model=StrategyOut, status_code=201)
async def create_strategy(body: StrategyIn, user: User = Depends(require_trader),
                          db: AsyncSession = Depends(get_db)):
    exists = await db.scalar(select(Strategy).where(Strategy.name == body.name))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Strategy name already exists")
    strat = Strategy(name=body.name, description=body.description,
                     owner_id=user.id, params=json.dumps(body.params),
                     timeframe=body.timeframe, is_active=body.is_active)
    db.add(strat)
    await db.commit()
    await db.refresh(strat)
    return strat


@strategies_router.patch("/{strategy_id}", response_model=StrategyOut)
async def update_strategy(strategy_id: str, body: StrategyIn,
                          user: User = Depends(require_trader),
                          db: AsyncSession = Depends(get_db)):
    strat = await db.get(Strategy, strategy_id)
    if strat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Strategy not found")
    if strat.owner_id not in (user.id, None) and user.role.value != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your strategy")
    strat.name, strat.description = body.name, body.description
    strat.params = json.dumps(body.params)
    strat.timeframe, strat.is_active = body.timeframe, body.is_active
    await db.commit()
    await db.refresh(strat)
    return strat


@strategies_router.post("/{strategy_id}/validate", response_model=StrategyOut,
                        dependencies=[Depends(require_admin)])
async def validate_strategy(strategy_id: str, db: AsyncSession = Depends(get_db)):
    """Admin gate: only validated strategies may drive live trades."""
    strat = await db.get(Strategy, strategy_id)
    if strat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Strategy not found")
    strat.is_validated = True
    await db.commit()
    await db.refresh(strat)
    return strat


# ------------------------------------------------------------------- backtest

backtest_router = APIRouter(prefix="/backtest", tags=["backtest"])


@backtest_router.post("/run")
async def run(body: BacktestRequest, user: User = Depends(require_trader),
              db: AsyncSession = Depends(get_db)):
    params = dict(body.params)
    if body.strategy_id:
        strat = await db.get(Strategy, body.strategy_id)
        if strat is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Strategy not found")
        try:
            params = {**json.loads(strat.params or "{}"), **params}
        except json.JSONDecodeError:
            pass

    klines = await get_klines(body.symbol, body.timeframe, limit=body.limit)
    if not klines or len(klines) < 100:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f"Not enough historical data for {body.symbol} {body.timeframe}")
    ohlcv = klines_to_ohlcv(klines)
    result = run_backtest(ohlcv, initial_balance=body.initial_balance,
                          params=params, allow_short=body.allow_short)

    run_row = BacktestRun(user_id=user.id, strategy_id=body.strategy_id,
                          symbol=body.symbol.upper(), timeframe=body.timeframe,
                          initial_balance=body.initial_balance, status="done",
                          report=json.dumps(result.metrics, default=str),
                          start_date=datetime.fromtimestamp(ohlcv["time"][0], tz=timezone.utc),
                          end_date=datetime.fromtimestamp(ohlcv["time"][-1], tz=timezone.utc))
    db.add(run_row)

    # feed strategy performance back into the ranking pipeline
    if body.strategy_id:
        m = result.metrics
        strat.win_rate = m.get("win_rate", 0.0)
        strat.profit_factor = m.get("profit_factor", 0.0)
        strat.sharpe_ratio = m.get("sharpe_ratio", 0.0)
        strat.max_drawdown_pct = m.get("max_drawdown_pct", 0.0)
        strat.rank_score = round(
            m.get("profit_factor", 0) * 20 + m.get("win_rate", 0) * 0.5
            + m.get("sharpe_ratio", 0) * 10 + m.get("max_drawdown_pct", 0) * 0.5, 2)

    await db.commit()
    return {"run_id": run_row.id, **result.to_dict()}


@backtest_router.get("/runs")
async def list_runs(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(BacktestRun).where(BacktestRun.user_id == user.id)
                             .order_by(BacktestRun.created_at.desc()).limit(50))).scalars().all()
    return [{"id": r.id, "symbol": r.symbol, "timeframe": r.timeframe,
             "initial_balance": r.initial_balance, "status": r.status,
             "metrics": json.loads(r.report or "{}"), "created_at": r.created_at}
            for r in rows]
