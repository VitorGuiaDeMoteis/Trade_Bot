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


def test_v1_historical_compatibility():
    # A payload that mixes domains (valid in v1, invalid in v2)
    raw = json.dumps(
        build_output(
            ["The backtest showed a 10% profit."],  # leak
            ["The backtest profit matches the paper profit."],  # mix
        )
    ).encode()

    # In v2 (default), it must fail
    with pytest.raises(ValueError, match="observer_regime_evidence_leak"):
        parse_output(raw)

    # In v1, it must pass (historical data is allowed to have semantic violations of v2)
    parsed = parse_output(raw, version="observer-v1")
    assert parsed.schema_version == "1.0"

    # But v1 STILL enforces core safety (no control chars, no disallowed content)
    unsafe_raw = json.dumps(build_output(["Here is my secret .env password."], [])).encode()
    with pytest.raises(ValueError, match="observer_disallowed_content"):
        parse_output(unsafe_raw, version="observer-v1")


def test_invalid_prompt_version():
    raw = json.dumps(build_output(["Safe text"], ["Safe text"])).encode()
    with pytest.raises(ValueError, match="invalid_prompt_version"):
        parse_output(raw, version="observer-v3")
