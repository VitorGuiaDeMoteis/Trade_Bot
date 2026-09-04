"""Explicit projection: raw source/configuration is never forwarded to a model."""

from collections.abc import Mapping
from typing import Any

from packages.contracts.observer import (
    AIObserverSnapshot,
    ObserverBacktest,
    ObserverCandle,
    ObserverPaper,
    ObserverPosition,
    ObserverRisk,
    ObserverSignal,
    canonical,
)


def project(raw: Mapping[str, Any]) -> AIObserverSnapshot:
    def fields(value: Mapping[str, Any], names: Any) -> dict[str, Any]:
        return {key: value[key] for key in names if key in value}

    payload = fields(raw, AIObserverSnapshot.model_fields)
    for name, model in (
        ("candles", ObserverCandle),
        ("signals", ObserverSignal),
        ("risk_decisions", ObserverRisk),
    ):
        rows = raw.get(name, [])
        if len(rows) > 128:
            raise ValueError("observer_input_too_large")
        payload[name] = [fields(row, model.model_fields) for row in rows]
    payload["symbols"] = sorted(set(raw["symbols"]))
    payload["candles"].sort(key=lambda c: (c["open_time"], c["symbol"]))
    for name in ("signals", "risk_decisions"):
        payload[name].sort(key=lambda row: row["symbol"])
    if raw.get("paper") is not None:
        paper = fields(raw["paper"], ObserverPaper.model_fields)
        paper["positions"] = sorted(
            [fields(p, ObserverPosition.model_fields) for p in raw["paper"]["positions"]],
            key=lambda p: p["symbol"],
        )
        payload["paper"] = paper
    if raw.get("accepted_backtest") is not None:
        payload["accepted_backtest"] = fields(
            raw["accepted_backtest"], ObserverBacktest.model_fields
        )
    snapshot = AIObserverSnapshot.model_validate_json(canonical(payload))
    snapshot.payload()
    return snapshot
