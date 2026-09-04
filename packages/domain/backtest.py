"""Frozen backtest inputs and deterministic serialization; no I/O or engines."""

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from packages.domain.market import Candle
from packages.domain.market_bar import MarketBar
from packages.domain.paper import PaperConfig, money

ENGINE_VERSION = "m4-core-v1"
STRATEGY_VERSION = "v1-deterministic"
RISK_VERSION = "m2-expiry-1h"


def encode(value: Any) -> str:
    def scalar(item: Any) -> str:
        if isinstance(item, Decimal):
            if not item.is_finite():
                raise ValueError("backtest_nonfinite_decimal")
            return format(item, "f")
        if isinstance(item, datetime):
            return item.isoformat()
        if isinstance(item, UUID):
            return str(item)
        raise TypeError("unsupported_backtest_value")

    return json.dumps(value, default=scalar, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(encode(value).encode()).hexdigest()


@dataclass(frozen=True)
class Dataset:
    candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        normalized = []
        for candle in self.candles:
            MarketBar(**{name: getattr(candle, name) for name in MarketBar.__dataclass_fields__})
            if not candle.is_closed or candle.timeframe != "1h":
                raise ValueError("backtest_closed_hour_required")
            normalized.append(
                replace(
                    candle,
                    open=money(candle.open),
                    high=money(candle.high),
                    low=money(candle.low),
                    close=money(candle.close),
                )
            )
        ordered = tuple(sorted(normalized, key=lambda c: (c.open_time, c.symbol)))
        keys = [(c.open_time, c.symbol) for c in ordered]
        if len(set(keys)) != len(keys) or len({c.candle_id for c in ordered}) != len(ordered):
            raise ValueError("backtest_duplicate_candle")
        if len({c.provider for c in ordered}) > 1:
            raise ValueError("backtest_mixed_providers")
        previous: Candle | None = None
        for candle in ordered:
            if (
                previous
                and candle.open_time != previous.open_time
                and candle.open_time < previous.close_time
            ):
                raise ValueError("backtest_overlapping_cross_asset_intervals")
            previous = candle
        object.__setattr__(self, "candles", ordered)

    @property
    def hash(self) -> str:
        return digest([asdict(c) for c in self.candles])


def manifest(dataset: Dataset, config: PaperConfig) -> dict[str, Any]:
    # Normalize equivalent decimal spellings, including configuration defaults.
    payload = {
        "schema_version": "1.0",
        "mode": "BACKTEST",
        "engine_version": ENGINE_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "risk_version": RISK_VERSION,
        "dataset_hash": dataset.hash,
        "candles": [asdict(c) for c in dataset.candles],
        "config": {key: money(value) for key, value in asdict(config).items()},
    }
    return {**payload, "manifest_hash": digest(payload)}
