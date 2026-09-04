import json

import pytest

from packages.contracts.observer import parse_output


def build_output(regime_evidence, observations, risk_flags=None):
    return {
        "schema_version": "1.0",
        "regime": {"label": "TRENDING", "confidence": 0.8, "evidence": regime_evidence},
        "risk_flags": risk_flags or [],
        "observations": observations,
    }


def test_semantic_regime_leak():
    # Model trying to use backtest as proof of TRENDING
    raw = json.dumps(build_output(["The backtest showed a 10% profit."], [])).encode()
    with pytest.raises(ValueError, match="observer_regime_evidence_leak"):
        parse_output(raw)

    raw = json.dumps(build_output(["The paper account is growing."], [])).encode()
    with pytest.raises(ValueError, match="observer_regime_evidence_leak"):
        parse_output(raw)


def test_semantic_domain_mix():
    # Model mixing paper and backtest
    raw = json.dumps(
        build_output(
            ["Candles show an uptrend."], ["The backtest profit matches the paper profit."]
        )
    ).encode()
    with pytest.raises(ValueError, match="observer_domain_mix"):
        parse_output(raw)


def test_valid_semantic():
    raw = json.dumps(
        build_output(
            ["Candles show an uptrend and higher highs."],
            ["Paper equity is 10000.", "Backtest return is 1.5%."],
        )
    ).encode()
    # Should not raise
    parse_output(raw)
