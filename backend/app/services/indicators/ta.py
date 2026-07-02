"""Technical analysis library — pure NumPy, no external TA dependency.

All functions accept 1-D numpy arrays (oldest → newest) and return arrays of
the same length with np.nan for warm-up periods, so values align with candles.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np


def _as_array(x) -> np.ndarray:
    return np.asarray(x, dtype=np.float64)


# ------------------------------------------------------------- moving means

def sma(values, period: int) -> np.ndarray:
    v = _as_array(values)
    out = np.full_like(v, np.nan)
    if len(v) < period or period <= 0:
        return out
    cumsum = np.cumsum(np.insert(v, 0, 0.0))
    out[period - 1:] = (cumsum[period:] - cumsum[:-period]) / period
    return out


def ema(values, period: int) -> np.ndarray:
    v = _as_array(values)
    out = np.full_like(v, np.nan)
    if len(v) < period or period <= 0:
        return out
    alpha = 2.0 / (period + 1.0)
    out[period - 1] = v[:period].mean()
    for i in range(period, len(v)):
        out[i] = alpha * v[i] + (1 - alpha) * out[i - 1]
    return out


def wilder_smooth(values, period: int) -> np.ndarray:
    """Wilder's smoothing (RMA), used by RSI/ATR/ADX."""
    v = _as_array(values)
    out = np.full_like(v, np.nan)
    if len(v) < period or period <= 0:
        return out
    out[period - 1] = v[:period].mean()
    for i in range(period, len(v)):
        out[i] = (out[i - 1] * (period - 1) + v[i]) / period
    return out


def vwap(high, low, close, volume) -> np.ndarray:
    h, l, c, vol = map(_as_array, (high, low, close, volume))
    typical = (h + l + c) / 3.0
    cum_vol = np.cumsum(vol)
    cum_pv = np.cumsum(typical * vol)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(cum_vol > 0, cum_pv / cum_vol, np.nan)


# ------------------------------------------------------------------ momentum

def rsi(values, period: int = 14) -> np.ndarray:
    v = _as_array(values)
    out = np.full_like(v, np.nan)
    if len(v) <= period:
        return out
    delta = np.diff(v)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    avg_gain = wilder_smooth(gains, period)
    avg_loss = wilder_smooth(losses, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
        rsi_vals = np.where(avg_loss == 0, 100.0, 100.0 - 100.0 / (1.0 + rs))
    out[1:] = rsi_vals
    return out


def macd(values, fast: int = 12, slow: int = 26, signal: int = 9
         ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    v = _as_array(values)
    macd_line = ema(v, fast) - ema(v, slow)
    valid = ~np.isnan(macd_line)
    signal_line = np.full_like(v, np.nan)
    if valid.sum() >= signal:
        signal_line[valid] = ema(macd_line[valid], signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def stochastic_rsi(values, period: int = 14, k_smooth: int = 3, d_smooth: int = 3
                   ) -> Tuple[np.ndarray, np.ndarray]:
    r = rsi(values, period)
    n = len(r)
    stoch = np.full(n, np.nan)
    for i in range(period * 2, n):
        window = r[i - period + 1: i + 1]
        if np.isnan(window).any():
            continue
        lo, hi = window.min(), window.max()
        stoch[i] = 0.0 if hi == lo else (r[i] - lo) / (hi - lo) * 100.0
    valid = ~np.isnan(stoch)
    k = np.full(n, np.nan)
    d = np.full(n, np.nan)
    if valid.sum() >= k_smooth:
        k[valid] = sma(stoch[valid], k_smooth)
    kv = ~np.isnan(k)
    if kv.sum() >= d_smooth:
        d[kv] = sma(k[kv], d_smooth)
    return k, d


# ---------------------------------------------------------------- volatility

def true_range(high, low, close) -> np.ndarray:
    h, l, c = map(_as_array, (high, low, close))
    prev_close = np.concatenate(([np.nan], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_close), np.abs(l - prev_close)))
    tr[0] = h[0] - l[0]
    return tr


def atr(high, low, close, period: int = 14) -> np.ndarray:
    return wilder_smooth(true_range(high, low, close), period)


def bollinger_bands(values, period: int = 20, num_std: float = 2.0
                    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    v = _as_array(values)
    mid = sma(v, period)
    std = np.full_like(v, np.nan)
    for i in range(period - 1, len(v)):
        std[i] = v[i - period + 1: i + 1].std(ddof=0)
    return mid + num_std * std, mid, mid - num_std * std


def adx(high, low, close, period: int = 14) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (adx, +DI, -DI)."""
    h, l, c = map(_as_array, (high, low, close))
    n = len(h)
    nanarr = np.full(n, np.nan)
    if n <= 2 * period:
        return nanarr, nanarr.copy(), nanarr.copy()

    up_move = np.diff(h)
    down_move = -np.diff(l)
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = true_range(h, l, c)[1:]

    atr_s = wilder_smooth(tr, period)
    plus_s = wilder_smooth(plus_dm, period)
    minus_s = wilder_smooth(minus_dm, period)

    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100.0 * plus_s / atr_s
        minus_di = 100.0 * minus_s / atr_s
        dx = 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di)

    dx_valid = np.where(np.isnan(dx), 0.0, dx)
    adx_vals = wilder_smooth(dx_valid, period)
    # re-mask warm-up: dx itself needs `period` bars first
    adx_vals[: 2 * period - 1] = np.nan

    out_adx, out_p, out_m = nanarr.copy(), nanarr.copy(), nanarr.copy()
    out_adx[1:], out_p[1:], out_m[1:] = adx_vals, plus_di, minus_di
    return out_adx, out_p, out_m


def supertrend(high, low, close, period: int = 10, multiplier: float = 3.0
               ) -> Tuple[np.ndarray, np.ndarray]:
    """Returns (supertrend_line, direction) where direction is +1 bullish / -1 bearish."""
    h, l, c = map(_as_array, (high, low, close))
    n = len(c)
    atr_vals = atr(h, l, c, period)
    hl2 = (h + l) / 2.0
    upper = hl2 + multiplier * atr_vals
    lower = hl2 - multiplier * atr_vals

    st = np.full(n, np.nan)
    direction = np.full(n, np.nan)
    trend = 1
    for i in range(n):
        if np.isnan(atr_vals[i]):
            continue
        if not np.isnan(st[i - 1]) if i > 0 else False:
            # adjust bands so they only ratchet in trend direction
            if trend == 1:
                lower[i] = max(lower[i], lower[i - 1]) if c[i - 1] > lower[i - 1] else lower[i]
            else:
                upper[i] = min(upper[i], upper[i - 1]) if c[i - 1] < upper[i - 1] else upper[i]
        prev_st = st[i - 1] if i > 0 and not np.isnan(st[i - 1]) else lower[i]
        if trend == 1:
            if c[i] < prev_st:
                trend = -1
                st[i] = upper[i]
            else:
                st[i] = max(lower[i], prev_st) if not np.isnan(prev_st) else lower[i]
        else:
            if c[i] > prev_st:
                trend = 1
                st[i] = lower[i]
            else:
                st[i] = min(upper[i], prev_st) if not np.isnan(prev_st) else upper[i]
        direction[i] = trend
    return st, direction


# ------------------------------------------------------------------ ichimoku

def ichimoku(high, low, close, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52
             ) -> Dict[str, np.ndarray]:
    h, l = _as_array(high), _as_array(low)
    n = len(h)

    def midline(period: int) -> np.ndarray:
        out = np.full(n, np.nan)
        for i in range(period - 1, n):
            out[i] = (h[i - period + 1: i + 1].max() + l[i - period + 1: i + 1].min()) / 2.0
        return out

    tenkan_sen = midline(tenkan)
    kijun_sen = midline(kijun)
    span_a = (tenkan_sen + kijun_sen) / 2.0
    span_b = midline(senkou_b)
    chikou = np.full(n, np.nan)
    chikou[: n - kijun] = _as_array(close)[kijun:]
    return {"tenkan": tenkan_sen, "kijun": kijun_sen, "senkou_a": span_a,
            "senkou_b": span_b, "chikou": chikou}


# ------------------------------------------------- levels: fib / support-res

def fibonacci_levels(high_price: float, low_price: float) -> Dict[str, float]:
    diff = high_price - low_price
    ratios = {"0.0": 0.0, "0.236": 0.236, "0.382": 0.382, "0.5": 0.5,
              "0.618": 0.618, "0.786": 0.786, "1.0": 1.0}
    return {k: round(high_price - diff * r, 8) for k, r in ratios.items()}


def support_resistance(high, low, close, lookback: int = 100, num_levels: int = 4
                       ) -> Tuple[List[float], List[float]]:
    """Pivot-based S/R: cluster swing highs/lows over the lookback window."""
    h, l, c = map(_as_array, (high, low, close))
    n = len(c)
    start = max(2, n - lookback)
    pivots_high, pivots_low = [], []
    for i in range(start, n - 2):
        if h[i] == h[i - 2: i + 3].max():
            pivots_high.append(h[i])
        if l[i] == l[i - 2: i + 3].min():
            pivots_low.append(l[i])

    def cluster(levels: List[float]) -> List[float]:
        if not levels:
            return []
        levels = sorted(levels)
        clusters: List[List[float]] = [[levels[0]]]
        tolerance = 0.005  # 0.5 % proximity merges into one level
        for lv in levels[1:]:
            if abs(lv - clusters[-1][-1]) / max(clusters[-1][-1], 1e-12) <= tolerance:
                clusters[-1].append(lv)
            else:
                clusters.append([lv])
        merged = [float(np.mean(cl)) for cl in sorted(clusters, key=len, reverse=True)]
        return merged[:num_levels]

    price = c[-1]
    resistance = sorted([lv for lv in cluster(pivots_high) if lv > price])[:num_levels]
    support = sorted([lv for lv in cluster(pivots_low) if lv < price], reverse=True)[:num_levels]
    return support, resistance


def volume_profile(close, volume, bins: int = 12) -> List[Dict[str, float]]:
    c, v = _as_array(close), _as_array(volume)
    if len(c) == 0:
        return []
    lo, hi = float(c.min()), float(c.max())
    if hi <= lo:
        return [{"price_low": lo, "price_high": hi, "volume": float(v.sum())}]
    edges = np.linspace(lo, hi, bins + 1)
    idx = np.clip(np.digitize(c, edges) - 1, 0, bins - 1)
    out = []
    for b in range(bins):
        out.append({"price_low": round(float(edges[b]), 8),
                    "price_high": round(float(edges[b + 1]), 8),
                    "volume": round(float(v[idx == b].sum()), 4)})
    return out


# --------------------------------------------------------------- composites

@dataclass
class IndicatorSnapshot:
    """Latest value of every indicator, JSON-serializable for signals/API."""
    price: float
    sma_20: Optional[float]
    sma_50: Optional[float]
    sma_200: Optional[float]
    ema_9: Optional[float]
    ema_21: Optional[float]
    ema_50: Optional[float]
    vwap: Optional[float]
    rsi_14: Optional[float]
    macd: Optional[float]
    macd_signal: Optional[float]
    macd_hist: Optional[float]
    stoch_rsi_k: Optional[float]
    stoch_rsi_d: Optional[float]
    atr_14: Optional[float]
    adx_14: Optional[float]
    plus_di: Optional[float]
    minus_di: Optional[float]
    bb_upper: Optional[float]
    bb_middle: Optional[float]
    bb_lower: Optional[float]
    supertrend: Optional[float]
    supertrend_dir: Optional[float]
    ichimoku_tenkan: Optional[float]
    ichimoku_kijun: Optional[float]
    ichimoku_span_a: Optional[float]
    ichimoku_span_b: Optional[float]
    support: List[float]
    resistance: List[float]
    fibonacci: Dict[str, float]
    trend_strength: float          # 0..100 (from ADX + MA alignment)
    momentum: float                # -100..100 composite

    def to_dict(self) -> dict:
        def clean(x):
            if isinstance(x, float) and (np.isnan(x) or np.isinf(x)):
                return None
            return x
        return {k: (v if isinstance(v, (list, dict)) else clean(v))
                for k, v in self.__dict__.items()}


def _last(arr: np.ndarray) -> Optional[float]:
    if arr is None or len(arr) == 0:
        return None
    val = arr[-1]
    return None if np.isnan(val) else round(float(val), 8)


def compute_snapshot(high, low, close, volume) -> IndicatorSnapshot:
    h, l, c, v = map(_as_array, (high, low, close, volume))
    macd_line, macd_sig, macd_hist = macd(c)
    k, d = stochastic_rsi(c)
    adx_v, plus_di, minus_di = adx(h, l, c)
    bb_u, bb_m, bb_l = bollinger_bands(c)
    st, st_dir = supertrend(h, l, c)
    ichi = ichimoku(h, l, c)
    support, resistance = support_resistance(h, l, c)
    window = c[-min(len(c), 200):]
    fib = fibonacci_levels(float(window.max()), float(window.min()))

    rsi_v = _last(rsi(c))
    adx_last = _last(adx_v) or 0.0
    price = float(c[-1])

    # Trend strength: ADX scaled, boosted when EMAs align with price
    ema9, ema21, ema50 = _last(ema(c, 9)), _last(ema(c, 21)), _last(ema(c, 50))
    alignment = 0.0
    if ema9 and ema21 and ema50:
        if price > ema9 > ema21 > ema50 or price < ema9 < ema21 < ema50:
            alignment = 25.0
        elif (price > ema21 > ema50) or (price < ema21 < ema50):
            alignment = 12.0
    trend_strength = round(min(100.0, adx_last * 1.5 + alignment), 2)

    # Momentum composite: RSI distance from 50 + MACD histogram sign
    momentum = 0.0
    if rsi_v is not None:
        momentum += (rsi_v - 50.0) * 1.6
    hist_last = _last(macd_hist)
    if hist_last is not None and price > 0:
        momentum += float(np.clip(hist_last / price * 10_000, -20, 20))
    momentum = round(float(np.clip(momentum, -100, 100)), 2)

    return IndicatorSnapshot(
        price=price,
        sma_20=_last(sma(c, 20)), sma_50=_last(sma(c, 50)), sma_200=_last(sma(c, 200)),
        ema_9=ema9, ema_21=ema21, ema_50=ema50,
        vwap=_last(vwap(h, l, c, v)),
        rsi_14=rsi_v,
        macd=_last(macd_line), macd_signal=_last(macd_sig), macd_hist=hist_last,
        stoch_rsi_k=_last(k), stoch_rsi_d=_last(d),
        atr_14=_last(atr(h, l, c)),
        adx_14=_last(adx_v), plus_di=_last(plus_di), minus_di=_last(minus_di),
        bb_upper=_last(bb_u), bb_middle=_last(bb_m), bb_lower=_last(bb_l),
        supertrend=_last(st), supertrend_dir=_last(st_dir),
        ichimoku_tenkan=_last(ichi["tenkan"]), ichimoku_kijun=_last(ichi["kijun"]),
        ichimoku_span_a=_last(ichi["senkou_a"]), ichimoku_span_b=_last(ichi["senkou_b"]),
        support=[round(s, 8) for s in support],
        resistance=[round(r, 8) for r in resistance],
        fibonacci=fib,
        trend_strength=trend_strength,
        momentum=momentum,
    )
