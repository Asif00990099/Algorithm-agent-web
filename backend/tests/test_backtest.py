"""Backtest engine tests using synthetic OHLCV."""
import numpy as np

from app.services.backtest.engine import compute_metrics, run_backtest, BTTrade


def make_ohlcv(n=600, seed=7, drift=0.15):
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift / 100, 0.01, n)
    close = 100 * np.exp(np.cumsum(returns))
    open_ = np.concatenate(([100.0], close[:-1]))
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.005, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.005, n))
    time = [1700000000 + i * 3600 for i in range(n)]
    return {"time": time, "open": open_.tolist(), "high": high.tolist(),
            "low": low.tolist(), "close": close.tolist(),
            "volume": rng.uniform(1000, 9000, n).tolist()}


def test_backtest_produces_report():
    result = run_backtest(make_ohlcv(), initial_balance=10_000)
    m = result.metrics
    assert m["initial_balance"] == 10_000
    assert "profit_factor" in m and "sharpe_ratio" in m and "max_drawdown_pct" in m
    assert m["total_trades"] == m["wins"] + m["losses"]
    assert len(result.equity_curve) > 0
    assert isinstance(result.monthly_returns, dict)


def test_backtest_not_enough_data():
    result = run_backtest({"time": [1], "open": [1], "high": [1],
                           "low": [1], "close": [1], "volume": [1]})
    assert "error" in result.metrics


def test_metrics_win_rate():
    trades = [BTTrade("long", 0, 100, 1, 110, 1, pnl=10, pnl_pct=10),
              BTTrade("long", 2, 100, 3, 95, 1, pnl=-5, pnl_pct=-5),
              BTTrade("long", 4, 100, 5, 108, 1, pnl=8, pnl_pct=8)]
    equity = [{"time": i, "equity": e} for i, e in enumerate([100, 110, 105, 113])]
    m = compute_metrics(trades, equity, 100, 113)
    assert m["total_trades"] == 3
    assert m["wins"] == 2
    assert m["win_rate"] == 66.67
    assert m["profit_factor"] == 3.6  # 18 / 5


def test_balance_conservation():
    """Final balance must equal initial + sum of trade PnL."""
    result = run_backtest(make_ohlcv(seed=11), initial_balance=5_000)
    total_pnl = sum(t["pnl"] for t in result.trades)
    assert abs(result.metrics["final_balance"] - (5_000 + total_pnl)) < 0.01
