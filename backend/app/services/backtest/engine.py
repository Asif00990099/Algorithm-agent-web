"""Backtesting engine.

Replays historical OHLCV bar-by-bar through the same signal ensemble the live
agent uses (indicator components only — sentiment/funding are not available
historically), simulates fills with fees, applies SL/TP/trailing rules, and
produces a full performance report: profit factor, Sharpe, max drawdown, win
rate, average trade, monthly returns and the equity curve.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import numpy as np

from app.services.indicators import ta

FEE = 0.001  # taker fee per side


@dataclass
class BTTrade:
    side: str
    entry_time: int
    entry_price: float
    exit_time: int = 0
    exit_price: float = 0.0
    quantity: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    reason: str = ""


@dataclass
class BacktestResult:
    metrics: dict = field(default_factory=dict)
    trades: List[dict] = field(default_factory=list)
    equity_curve: List[dict] = field(default_factory=list)
    monthly_returns: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"metrics": self.metrics, "trades": self.trades,
                "equity_curve": self.equity_curve, "monthly_returns": self.monthly_returns}


def _signal_at(i: int, close, ema9, ema21, ema50, rsi14, macd_hist, st_dir,
               adx14, plus_di, minus_di, thresholds: dict) -> str:
    """Same component logic as the live agent, evaluated on bar i (no lookahead:
    only uses values up to and including bar i)."""
    score = 0.0
    p = close[i]
    if not (math.isnan(ema9[i]) or math.isnan(ema21[i]) or math.isnan(ema50[i])):
        if p > ema9[i] > ema21[i] > ema50[i]:
            score += 0.6 * 0.35
        elif p < ema9[i] < ema21[i] < ema50[i]:
            score -= 0.6 * 0.35
        elif p > ema21[i]:
            score += 0.2 * 0.35
        else:
            score -= 0.2 * 0.35
    if not math.isnan(st_dir[i]):
        score += 0.25 * 0.35 * (1 if st_dir[i] > 0 else -1)
    if not math.isnan(rsi14[i]):
        if rsi14[i] < 30:
            score += 0.45 * 0.3
        elif rsi14[i] > 70:
            score -= 0.45 * 0.3
        else:
            score += (rsi14[i] - 50) / 50 * 0.3 * 0.3
    if not math.isnan(macd_hist[i]) and p > 0:
        score += max(-0.35, min(0.35, macd_hist[i] / p * 800)) * 0.3
    if not (math.isnan(adx14[i]) or math.isnan(plus_di[i]) or math.isnan(minus_di[i])):
        direction = 1.0 if plus_di[i] > minus_di[i] else -1.0
        score += direction * min(1.0, adx14[i] / 50.0) * 0.2
    if score >= thresholds.get("buy", 0.22):
        return "buy"
    if score <= thresholds.get("sell", -0.22):
        return "sell"
    return "hold"


def run_backtest(ohlcv: dict, initial_balance: float = 10_000.0,
                 params: Optional[dict] = None, allow_short: bool = True) -> BacktestResult:
    """`ohlcv` is the dict shape produced by binance.klines_to_ohlcv."""
    params = params or {}
    thresholds = {**{"buy": 0.22, "sell": -0.22}, **params.get("thresholds", {})}
    sl_mult = float(params.get("sl_atr_mult", 1.5))
    tp_mult = float(params.get("tp_atr_mult", 3.0))
    trailing_pct = params.get("trailing_stop_pct")  # optional
    risk_frac = float(params.get("risk_per_trade_pct", 2.0)) / 100.0

    t = ohlcv["time"]
    o, h, l, c = (np.asarray(ohlcv[k], dtype=float) for k in ("open", "high", "low", "close"))
    n = len(c)
    if n < 60:
        return BacktestResult(metrics={"error": "not enough data", "bars": n})

    ema9, ema21, ema50 = ta.ema(c, 9), ta.ema(c, 21), ta.ema(c, 50)
    rsi14 = ta.rsi(c)
    _, _, macd_hist = ta.macd(c)
    _, st_dir = ta.supertrend(h, l, c)
    adx14, plus_di, minus_di = ta.adx(h, l, c)
    atr14 = ta.atr(h, l, c)

    balance = initial_balance
    equity_curve: List[dict] = []
    trades: List[BTTrade] = []
    position: Optional[BTTrade] = None
    stop = target = high_water = None

    for i in range(55, n - 1):
        price = c[i]
        # ---- manage open position on this bar ----
        if position is not None:
            long = position.side == "long"
            exit_price = exit_reason = None
            if long:
                if stop is not None and l[i] <= stop:
                    exit_price, exit_reason = stop, "sl"
                elif target is not None and h[i] >= target:
                    exit_price, exit_reason = target, "tp"
            else:
                if stop is not None and h[i] >= stop:
                    exit_price, exit_reason = stop, "sl"
                elif target is not None and l[i] <= target:
                    exit_price, exit_reason = target, "tp"
            if exit_price is None and trailing_pct and high_water is not None:
                if long:
                    high_water = max(high_water, h[i])
                    trail_level = high_water * (1 - trailing_pct / 100)
                    if l[i] <= trail_level and trail_level > position.entry_price:
                        exit_price, exit_reason = trail_level, "trailing"
                else:
                    high_water = min(high_water, l[i])
                    trail_level = high_water * (1 + trailing_pct / 100)
                    if h[i] >= trail_level and trail_level < position.entry_price:
                        exit_price, exit_reason = trail_level, "trailing"
            if exit_price is None:
                sig = _signal_at(i, c, ema9, ema21, ema50, rsi14, macd_hist,
                                 st_dir, adx14, plus_di, minus_di, thresholds)
                if (long and sig == "sell") or (not long and sig == "buy"):
                    exit_price, exit_reason = price, "signal_flip"
            if exit_price is not None:
                direction = 1.0 if long else -1.0
                gross = (exit_price - position.entry_price) * position.quantity * direction
                fees = (position.entry_price + exit_price) * position.quantity * FEE
                position.pnl = gross - fees
                position.pnl_pct = position.pnl / (position.entry_price * position.quantity) * 100
                position.exit_time, position.exit_price = t[i], round(exit_price, 8)
                position.reason = exit_reason
                balance += position.pnl
                trades.append(position)
                position = None
                stop = target = high_water = None

        # ---- open new position on signal ----
        if position is None and balance > 0:
            sig = _signal_at(i, c, ema9, ema21, ema50, rsi14, macd_hist,
                             st_dir, adx14, plus_di, minus_di, thresholds)
            if sig == "buy" or (sig == "sell" and allow_short):
                atr = atr14[i] if not math.isnan(atr14[i]) else price * 0.02
                entry = o[i + 1]  # fill at next bar open — no lookahead
                if sig == "buy":
                    stop, target = entry - sl_mult * atr, entry + tp_mult * atr
                else:
                    stop, target = entry + sl_mult * atr, entry - tp_mult * atr
                per_unit_risk = abs(entry - stop)
                qty = (balance * risk_frac) / per_unit_risk if per_unit_risk > 0 else 0
                qty = min(qty, balance * 0.95 / entry)
                if qty * entry >= 10:
                    position = BTTrade(side="long" if sig == "buy" else "short",
                                       entry_time=t[i + 1], entry_price=round(entry, 8),
                                       quantity=qty)
                    high_water = entry
                else:
                    stop = target = None

        mark = balance
        if position is not None:
            direction = 1.0 if position.side == "long" else -1.0
            mark += (price - position.entry_price) * position.quantity * direction
        equity_curve.append({"time": t[i], "equity": round(mark, 2)})

    # force-close at the end
    if position is not None:
        direction = 1.0 if position.side == "long" else -1.0
        gross = (c[-1] - position.entry_price) * position.quantity * direction
        fees = (position.entry_price + c[-1]) * position.quantity * FEE
        position.pnl = gross - fees
        position.pnl_pct = position.pnl / (position.entry_price * position.quantity) * 100
        position.exit_time, position.exit_price, position.reason = t[-1], round(float(c[-1]), 8), "end"
        balance += position.pnl
        trades.append(position)

    return BacktestResult(
        metrics=compute_metrics(trades, equity_curve, initial_balance, balance),
        trades=[tr.__dict__ for tr in trades],
        equity_curve=equity_curve[-500:],
        monthly_returns=monthly_returns(equity_curve),
    )


def compute_metrics(trades: List[BTTrade], equity_curve: List[dict],
                    initial: float, final: float) -> dict:
    wins = [tr for tr in trades if tr.pnl > 0]
    losses = [tr for tr in trades if tr.pnl <= 0]
    gross_profit = sum(tr.pnl for tr in wins)
    gross_loss = abs(sum(tr.pnl for tr in losses))

    equity = np.array([e["equity"] for e in equity_curve]) if equity_curve else np.array([initial])
    peak = np.maximum.accumulate(equity)
    drawdowns = (equity - peak) / peak
    max_dd = float(drawdowns.min()) if len(drawdowns) else 0.0

    rets = np.diff(equity) / equity[:-1] if len(equity) > 1 else np.array([])
    sharpe = 0.0
    if len(rets) > 1 and rets.std() > 0:
        sharpe = float(rets.mean() / rets.std() * math.sqrt(365 * 24))  # hourly bars annualized

    return {
        "initial_balance": round(initial, 2),
        "final_balance": round(final, 2),
        "total_return_pct": round((final - initial) / initial * 100, 2),
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        "loss_rate": round(len(losses) / len(trades) * 100, 2) if trades else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else (
            round(gross_profit, 3) if gross_profit > 0 else 0.0),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "avg_trade_pnl": round(float(np.mean([tr.pnl for tr in trades])), 4) if trades else 0.0,
        "avg_win": round(float(np.mean([tr.pnl for tr in wins])), 4) if wins else 0.0,
        "avg_loss": round(float(np.mean([tr.pnl for tr in losses])), 4) if losses else 0.0,
        "best_trade_pct": round(max((tr.pnl_pct for tr in trades), default=0.0), 3),
        "worst_trade_pct": round(min((tr.pnl_pct for tr in trades), default=0.0), 3),
    }


def monthly_returns(equity_curve: List[dict]) -> dict:
    """Month-keyed % returns from the equity curve (unix-second timestamps)."""
    if not equity_curve:
        return {}
    by_month: dict[str, list[float]] = {}
    for point in equity_curve:
        dt = datetime.fromtimestamp(point["time"], tz=timezone.utc)
        by_month.setdefault(dt.strftime("%Y-%m"), []).append(point["equity"])
    out = {}
    prev_close: Optional[float] = None
    for month in sorted(by_month):
        series = by_month[month]
        start = prev_close if prev_close is not None else series[0]
        out[month] = round((series[-1] - start) / start * 100, 2) if start else 0.0
        prev_close = series[-1]
    return out
