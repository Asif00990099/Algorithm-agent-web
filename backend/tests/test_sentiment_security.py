"""Tests for the sentiment analyzer, security primitives and position sizing."""
import pytest

from app.core.security import (
    create_access_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    verify_password,
)
from app.services.sentiment.analyzer import aggregate, analyze_text
from app.services.trading.engine import TradingError, compute_position_size

# ------------------------------------------------------------------ sentiment

def test_positive_headline():
    r = analyze_text("Bitcoin surges to record high as ETF approval sparks rally")
    assert r.label == "positive"
    assert r.score > 0.2


def test_negative_headline():
    r = analyze_text("Exchange hacked: massive selloff and liquidations as market crashes")
    assert r.label == "negative"
    assert r.score < -0.3


def test_neutral_text():
    r = analyze_text("The committee will meet on Tuesday to discuss the agenda")
    assert r.label == "neutral"


def test_negation_flips_direction():
    plain = analyze_text("bullish rally").score
    negated = analyze_text("not a bullish rally").score
    assert negated < plain


def test_aggregate_counts():
    agg = aggregate(["Bitcoin rally continues", "Market crash deepens", "Meeting on Tuesday"])
    assert agg["sample_size"] == 3
    assert agg["positive"] >= 1 and agg["negative"] >= 1


# ------------------------------------------------------------------ security

def test_password_hash_roundtrip():
    hashed = hash_password("CorrectHorse9")
    assert verify_password("CorrectHorse9", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_roundtrip():
    token = create_access_token("user-123", "trader")
    payload = decode_token(token, "access")
    assert payload["sub"] == "user-123"
    assert payload["role"] == "trader"
    assert decode_token(token, "refresh") is None  # wrong type rejected


def test_encryption_roundtrip():
    secret = "binance-api-secret-XYZ"
    assert decrypt_secret(encrypt_secret(secret)) == secret
    assert decrypt_secret("garbage") is None


# ------------------------------------------------------------- position size

def test_position_size_risk_based():
    # 1% of 10_000 = 100 risk; entry 100 stop 95 -> 5/unit -> 20 units
    s = compute_position_size(10_000, 100.0, 95.0, 1.0)
    assert s.quantity == pytest.approx(20.0)
    assert s.risk_amount == pytest.approx(100.0)


def test_position_size_caps_at_balance():
    s = compute_position_size(1_000, 100.0, 99.9, 5.0)  # tiny stop → huge qty
    assert s.notional <= 1_000 * 0.95 + 1e-6


def test_position_size_rejects_dust():
    with pytest.raises(TradingError):
        compute_position_size(20, 100.0, 95.0, 1.0)  # < 10 USDT notional
