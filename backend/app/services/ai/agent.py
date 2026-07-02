"""The AI trading agent.

Pipeline per symbol:
  1. Pull live OHLCV from Binance and compute the full indicator snapshot.
  2. Pull social sentiment (Reddit / X / RSS) and the Fear & Greed index.
  3. Score a weighted rule ensemble (deterministic, works with zero API keys).
  4. Optionally ask the configured LLM to review the evidence and refine the
     rationale (the LLM can veto, never invent — decisions stay bounded by
     the quant score).
  5. Emit a Signal with probability, confidence, SL/TP/trailing-stop and a
     full risk plan.

Strategy `params` JSON can override every weight/threshold, which is how the
learning pipeline tunes strategies over time.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings
from app.services.ai.llm import try_complete
from app.services.indicators.ta import IndicatorSnapshot, compute_snapshot
from app.services.market.binance import get_funding_rate, get_klines, klines_to_ohlcv
from app.services.market.macro import get_fear_greed
from app.services.sentiment.analyzer import aggregate
from app.services.sentiment.sources import collect_symbol_texts

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {
    "trend": 0.30,       # EMA alignment + SuperTrend + Ichimoku
    "momentum": 0.25,    # RSI + MACD + Stoch RSI
    "volatility": 0.10,  # Bollinger position
    "strength": 0.15,    # ADX / DI
    "sentiment": 0.12,   # social + fear/greed
    "funding": 0.08,     # futures funding-rate contrarian tilt
}
DEFAULT_THRESHOLDS = {"buy": 0.22, "sell": -0.22}


@dataclass
class AgentDecision:
    symbol: str
    timeframe: str
    action: str                     # buy | sell | hold
    price: float
    score: float                    # -1..1 composite
    probability: float              # 0..1
    confidence: float               # 0..100
    stop_loss: Optional[float]
    take_profit: Optional[float]
    trailing_stop_pct: Optional[float]
    risk_reward: float
    sentiment_score: Optional[float]
    rationale: str
    ai_provider: str
    components: dict = field(default_factory=dict)
    indicators: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _score_trend(snap: IndicatorSnapshot) -> float:
    s = 0.0
    p = snap.price
    if snap.ema_9 and snap.ema_21 and snap.ema_50:
        if p > snap.ema_9 > snap.ema_21 > snap.ema_50:
            s += 0.6
        elif p < snap.ema_9 < snap.ema_21 < snap.ema_50:
            s -= 0.6
        elif p > snap.ema_21:
            s += 0.2
        elif p < snap.ema_21:
            s -= 0.2
    if snap.supertrend_dir is not None:
        s += 0.25 * (1 if snap.supertrend_dir > 0 else -1)
    if snap.ichimoku_span_a and snap.ichimoku_span_b:
        cloud_top = max(snap.ichimoku_span_a, snap.ichimoku_span_b)
        cloud_bot = min(snap.ichimoku_span_a, snap.ichimoku_span_b)
        if p > cloud_top:
            s += 0.15
        elif p < cloud_bot:
            s -= 0.15
    return max(-1.0, min(1.0, s))


def _score_momentum(snap: IndicatorSnapshot) -> float:
    s = 0.0
    if snap.rsi_14 is not None:
        if snap.rsi_14 < 30:
            s += 0.45          # oversold — mean-reversion buy bias
        elif snap.rsi_14 > 70:
            s -= 0.45
        else:
            s += (snap.rsi_14 - 50) / 50 * 0.3
    if snap.macd_hist is not None and snap.price > 0:
        s += max(-0.35, min(0.35, snap.macd_hist / snap.price * 800))
    if snap.stoch_rsi_k is not None and snap.stoch_rsi_d is not None:
        if snap.stoch_rsi_k < 20 and snap.stoch_rsi_k > snap.stoch_rsi_d:
            s += 0.2
        elif snap.stoch_rsi_k > 80 and snap.stoch_rsi_k < snap.stoch_rsi_d:
            s -= 0.2
    return max(-1.0, min(1.0, s))


def _score_volatility(snap: IndicatorSnapshot) -> float:
    if not (snap.bb_upper and snap.bb_lower and snap.bb_upper > snap.bb_lower):
        return 0.0
    pos = (snap.price - snap.bb_lower) / (snap.bb_upper - snap.bb_lower)  # 0..1
    if pos < 0.1:
        return 0.5
    if pos > 0.9:
        return -0.5
    return (0.5 - pos) * 0.4


def _score_strength(snap: IndicatorSnapshot) -> float:
    if snap.adx_14 is None or snap.plus_di is None or snap.minus_di is None:
        return 0.0
    direction = 1.0 if snap.plus_di > snap.minus_di else -1.0
    magnitude = min(1.0, snap.adx_14 / 50.0)
    return direction * magnitude


def _score_funding(funding_rate: Optional[float]) -> float:
    """Extreme positive funding = crowded longs (bearish tilt) and vice versa."""
    if funding_rate is None:
        return 0.0
    return max(-1.0, min(1.0, -funding_rate * 2000))


async def analyze_symbol(symbol: str, timeframe: str = "1h",
                         params: Optional[dict] = None,
                         include_sentiment: bool = True,
                         use_llm: bool = True) -> Optional[AgentDecision]:
    params = params or {}
    weights = {**DEFAULT_WEIGHTS, **params.get("weights", {})}
    thresholds = {**DEFAULT_THRESHOLDS, **params.get("thresholds", {})}

    klines = await get_klines(symbol, timeframe, limit=300)
    if not klines or len(klines) < 60:
        logger.warning("Not enough candles for %s %s", symbol, timeframe)
        return None
    ohlcv = klines_to_ohlcv(klines)
    snap = compute_snapshot(ohlcv["high"], ohlcv["low"], ohlcv["close"], ohlcv["volume"])

    # --- sentiment inputs -------------------------------------------------
    sentiment_score: Optional[float] = None
    if include_sentiment:
        base_asset = symbol.upper().replace("USDT", "").replace("USDC", "").replace("BUSD", "")
        texts = await collect_symbol_texts(base_asset)
        agg = aggregate(texts["reddit"] + texts["twitter"] + texts["rss"])
        if agg["sample_size"] > 0:
            sentiment_score = agg["score"]
        fng = await get_fear_greed(1)
        if fng:
            try:
                fng_norm = (float(fng[0]["value"]) - 50.0) / 50.0  # -1..1
                sentiment_score = (fng_norm if sentiment_score is None
                                   else 0.7 * sentiment_score + 0.3 * fng_norm)
            except (KeyError, ValueError):
                pass

    funding = await get_funding_rate(symbol)
    funding_rate = None
    if funding:
        try:
            funding_rate = float(funding.get("lastFundingRate"))
        except (TypeError, ValueError):
            funding_rate = None

    # --- weighted ensemble ------------------------------------------------
    components = {
        "trend": _score_trend(snap),
        "momentum": _score_momentum(snap),
        "volatility": _score_volatility(snap),
        "strength": _score_strength(snap),
        "sentiment": sentiment_score if sentiment_score is not None else 0.0,
        "funding": _score_funding(funding_rate),
    }
    score = sum(components[k] * weights.get(k, 0.0) for k in components)
    score = max(-1.0, min(1.0, score))

    action = "hold"
    if score >= thresholds["buy"]:
        action = "buy"
    elif score <= thresholds["sell"]:
        action = "sell"

    # Probability: calibrated sigmoid of |score|; confidence adds data quality
    probability = round(0.5 + abs(score) * 0.42, 4)
    data_quality = 1.0 if sentiment_score is not None else 0.85
    confidence = round(min(100.0, abs(score) * 130 * data_quality + snap.trend_strength * 0.15), 2)

    # --- risk plan (ATR-based) ---------------------------------------------
    stop_loss = take_profit = trailing = None
    risk_reward = 0.0
    atr = snap.atr_14 or snap.price * 0.02
    sl_mult = float(params.get("sl_atr_mult", 1.5))
    tp_mult = float(params.get("tp_atr_mult", 3.0))
    if action == "buy":
        stop_loss = round(snap.price - sl_mult * atr, 8)
        take_profit = round(snap.price + tp_mult * atr, 8)
        if snap.support:
            stop_loss = round(min(stop_loss, snap.support[0] * 0.998), 8)
    elif action == "sell":
        stop_loss = round(snap.price + sl_mult * atr, 8)
        take_profit = round(snap.price - tp_mult * atr, 8)
        if snap.resistance:
            stop_loss = round(max(stop_loss, snap.resistance[0] * 1.002), 8)
    if action != "hold" and stop_loss and take_profit:
        risk = abs(snap.price - stop_loss)
        reward = abs(take_profit - snap.price)
        risk_reward = round(reward / risk, 2) if risk > 0 else 0.0
        trailing = round(float(params.get("trailing_stop_pct", (atr / snap.price) * 100 * 1.2)), 4)

    rationale = _build_rationale(symbol, action, snap, components, sentiment_score, funding_rate)
    ai_provider = "quant"

    # --- optional LLM review ------------------------------------------------
    if use_llm and action != "hold":
        llm_text = await try_complete(
            system=("You are a risk-focused trading analyst. Review the quantitative "
                    "evidence and either endorse or veto the proposed trade. Reply with "
                    "a JSON object: {\"endorse\": true|false, \"rationale\": \"...\"} "
                    "in under 120 words. Never invent data not present in the evidence."),
            user=json.dumps({"symbol": symbol, "timeframe": timeframe,
                             "proposed_action": action, "score": round(score, 4),
                             "components": components,
                             "indicators": snap.to_dict(),
                             "sentiment": sentiment_score,
                             "funding_rate": funding_rate}, default=str),
            max_tokens=400)
        if llm_text:
            try:
                start, end = llm_text.find("{"), llm_text.rfind("}")
                verdict = json.loads(llm_text[start:end + 1])
                ai_provider = settings.AI_PROVIDER
                if verdict.get("rationale"):
                    rationale = f"{rationale} LLM review: {verdict['rationale']}"
                if verdict.get("endorse") is False:
                    action = "hold"
                    confidence = round(confidence * 0.5, 2)
            except (ValueError, json.JSONDecodeError):
                logger.debug("LLM verdict unparseable; keeping quant decision")

    return AgentDecision(
        symbol=symbol.upper(), timeframe=timeframe, action=action,
        price=snap.price, score=round(score, 4), probability=probability,
        confidence=confidence, stop_loss=stop_loss, take_profit=take_profit,
        trailing_stop_pct=trailing, risk_reward=risk_reward,
        sentiment_score=sentiment_score, rationale=rationale,
        ai_provider=ai_provider,
        components={k: round(v, 4) for k, v in components.items()},
        indicators=snap.to_dict(),
    )


def _build_rationale(symbol: str, action: str, snap: IndicatorSnapshot,
                     components: dict, sentiment: Optional[float],
                     funding: Optional[float]) -> str:
    parts = [f"{symbol}: composite {action.upper()} signal."]
    if snap.rsi_14 is not None:
        parts.append(f"RSI(14)={snap.rsi_14:.1f}.")
    if snap.adx_14 is not None:
        parts.append(f"ADX={snap.adx_14:.1f} (trend strength {snap.trend_strength:.0f}/100).")
    if snap.supertrend_dir is not None:
        parts.append(f"SuperTrend {'bullish' if snap.supertrend_dir > 0 else 'bearish'}.")
    if snap.macd_hist is not None:
        parts.append(f"MACD histogram {'positive' if snap.macd_hist > 0 else 'negative'}.")
    if sentiment is not None:
        parts.append(f"Social sentiment {sentiment:+.2f}.")
    if funding is not None:
        parts.append(f"Funding rate {funding:+.5f}.")
    dominant = max(components, key=lambda k: abs(components[k]))
    parts.append(f"Dominant factor: {dominant} ({components[dominant]:+.2f}).")
    return " ".join(parts)
