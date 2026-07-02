"""Lexicon-based financial sentiment analyzer.

Fast, deterministic and dependency-free — used to score every headline, tweet
and Reddit post. When an LLM provider is configured the AI agent can refine
scores, but this baseline always works with zero API keys."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List

POSITIVE = {
    "surge": 2, "soar": 2, "rally": 2, "bullish": 2, "breakout": 2, "moon": 2,
    "gain": 1, "gains": 1, "rise": 1, "rises": 1, "up": 1, "high": 1, "record": 1,
    "adoption": 1, "approval": 2, "approved": 2, "partnership": 1, "upgrade": 1,
    "buy": 1, "accumulate": 1, "inflow": 1, "inflows": 1, "growth": 1, "profit": 1,
    "beat": 1, "beats": 1, "outperform": 2, "strong": 1, "boom": 2, "positive": 1,
    "win": 1, "support": 1, "institutional": 1, "etf": 1, "halving": 1, "burn": 1,
    "recovery": 1, "rebound": 2, "milestone": 1, "all-time": 1, "ath": 2,
}
NEGATIVE = {
    "crash": -3, "plunge": -2, "dump": -2, "bearish": -2, "collapse": -3,
    "fall": -1, "falls": -1, "drop": -1, "drops": -1, "down": -1, "low": -1,
    "hack": -3, "hacked": -3, "exploit": -3, "scam": -3, "fraud": -3, "lawsuit": -2,
    "sec": -1, "ban": -2, "banned": -2, "crackdown": -2, "regulation": -1,
    "sell": -1, "selloff": -2, "sell-off": -2, "outflow": -1, "outflows": -1,
    "liquidation": -2, "liquidations": -2, "loss": -1, "losses": -1, "fear": -1,
    "recession": -2, "inflation": -1, "default": -2, "bankruptcy": -3, "bankrupt": -3,
    "warning": -1, "risk": -1, "weak": -1, "miss": -1, "misses": -1, "delist": -2,
    "delisting": -2, "halt": -1, "halted": -1, "investigation": -2, "negative": -1,
}
NEGATORS = {"not", "no", "never", "without", "isn't", "wasn't", "won't", "don't", "doesn't"}
INTENSIFIERS = {"very": 1.5, "extremely": 2.0, "massive": 1.8, "huge": 1.6, "major": 1.4}

_token_re = re.compile(r"[a-zA-Z][a-zA-Z\-']*")


@dataclass
class SentimentResult:
    score: float           # -1..1
    label: str             # positive | negative | neutral
    positive_hits: int
    negative_hits: int

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def analyze_text(text: str) -> SentimentResult:
    tokens = [t.lower() for t in _token_re.findall(text or "")]
    raw = 0.0
    pos_hits = neg_hits = 0
    for i, tok in enumerate(tokens):
        weight = POSITIVE.get(tok, 0) or NEGATIVE.get(tok, 0)
        if not weight:
            continue
        multiplier = 1.0
        window = tokens[max(0, i - 2): i]
        if any(w in NEGATORS for w in window):
            weight = -weight * 0.8
        for w in window:
            multiplier *= INTENSIFIERS.get(w, 1.0)
        raw += weight * multiplier
        if weight > 0:
            pos_hits += 1
        elif weight < 0:
            neg_hits += 1
    # squash to -1..1 (tanh-like without importing math for clarity)
    score = max(-1.0, min(1.0, raw / 6.0))
    label = "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"
    return SentimentResult(round(score, 4), label, pos_hits, neg_hits)


def aggregate(texts: Iterable[str]) -> dict:
    results: List[SentimentResult] = [analyze_text(t) for t in texts if t]
    if not results:
        return {"score": 0.0, "label": "neutral", "positive": 0, "negative": 0,
                "neutral": 0, "sample_size": 0}
    pos = sum(1 for r in results if r.label == "positive")
    neg = sum(1 for r in results if r.label == "negative")
    neu = len(results) - pos - neg
    avg = sum(r.score for r in results) / len(results)
    label = "positive" if avg > 0.1 else "negative" if avg < -0.1 else "neutral"
    return {"score": round(avg, 4), "label": label, "positive": pos,
            "negative": neg, "neutral": neu, "sample_size": len(results)}
