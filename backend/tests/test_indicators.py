"""Unit tests for the technical analysis library."""
import numpy as np
import pytest

from app.services.indicators import ta


@pytest.fixture
def trending_up():
    rng = np.random.default_rng(42)
    base = np.linspace(100, 200, 300) + rng.normal(0, 1.5, 300)
    high = base + rng.uniform(0.5, 2.0, 300)
    low = base - rng.uniform(0.5, 2.0, 300)
    volume = rng.uniform(1000, 5000, 300)
    return high, low, base, volume


def test_sma_basic():
    values = [1, 2, 3, 4, 5]
    result = ta.sma(values, 3)
    assert np.isnan(result[0]) and np.isnan(result[1])
    assert result[2] == pytest.approx(2.0)
    assert result[4] == pytest.approx(4.0)


def test_ema_converges_to_constant():
    result = ta.ema([10.0] * 50, 10)
    assert result[-1] == pytest.approx(10.0)


def test_rsi_bounds_and_direction():
    up = list(range(1, 60))
    down = list(range(60, 1, -1))
    rsi_up = ta.rsi(np.array(up, dtype=float))[-1]
    rsi_down = ta.rsi(np.array(down, dtype=float))[-1]
    assert 0 <= rsi_down < 30
    assert 70 < rsi_up <= 100


def test_macd_shapes(trending_up):
    _, _, close, _ = trending_up
    line, signal, hist = ta.macd(close)
    assert len(line) == len(close) == len(signal) == len(hist)
    # in a steady uptrend MACD line should be positive at the end
    assert line[-1] > 0


def test_atr_positive(trending_up):
    high, low, close, _ = trending_up
    result = ta.atr(high, low, close)
    assert result[-1] > 0


def test_bollinger_ordering(trending_up):
    _, _, close, _ = trending_up
    upper, mid, lower = ta.bollinger_bands(close)
    assert upper[-1] > mid[-1] > lower[-1]


def test_adx_range(trending_up):
    high, low, close, _ = trending_up
    adx, plus_di, minus_di = ta.adx(high, low, close)
    assert 0 <= adx[-1] <= 100
    # uptrend: +DI should dominate
    assert plus_di[-1] > minus_di[-1]


def test_supertrend_direction_uptrend(trending_up):
    high, low, close, _ = trending_up
    _, direction = ta.supertrend(high, low, close)
    assert direction[-1] == 1


def test_vwap_between_extremes(trending_up):
    high, low, close, volume = trending_up
    result = ta.vwap(high, low, close, volume)
    assert low.min() <= result[-1] <= high.max()


def test_ichimoku_keys(trending_up):
    high, low, close, _ = trending_up
    ichi = ta.ichimoku(high, low, close)
    assert set(ichi) == {"tenkan", "kijun", "senkou_a", "senkou_b", "chikou"}
    assert not np.isnan(ichi["kijun"][-1])


def test_fibonacci_levels():
    levels = ta.fibonacci_levels(200.0, 100.0)
    assert levels["0.0"] == 200.0
    assert levels["1.0"] == 100.0
    assert levels["0.5"] == 150.0


def test_support_resistance_sides(trending_up):
    high, low, close, _ = trending_up
    support, resistance = ta.support_resistance(high, low, close)
    price = close[-1]
    assert all(s < price for s in support)
    assert all(r > price for r in resistance)


def test_snapshot_serializable(trending_up):
    high, low, close, volume = trending_up
    snap = ta.compute_snapshot(high, low, close, volume)
    d = snap.to_dict()
    assert d["price"] == pytest.approx(close[-1])
    assert d["rsi_14"] is not None
    assert 0 <= d["trend_strength"] <= 100
    assert -100 <= d["momentum"] <= 100
    import json
    json.dumps(d)  # must be JSON-safe (no NaN)
