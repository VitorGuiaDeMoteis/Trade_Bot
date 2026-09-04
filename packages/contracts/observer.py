"""Observer-only DTOs. No configuration objects, execution capabilities or raw prose inputs."""

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

MAX_INPUT_BYTES = 65536
MAX_OUTPUT_BYTES = 16384
MAX_SYMBOLS = 4
MAX_CANDLES_PER_SYMBOL = 32
Symbol = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9.-]{0,15}$")]
Hash = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Money = Annotated[str, StringConstraints(pattern=r"^-?[0-9]{1,18}(\.[0-9]{1,10})?$", max_length=30)]
Text = Annotated[str, StringConstraints(min_length=1, max_length=240)]


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("observer_utc_required")
    return value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)


class ObserverCandle(Strict):
    symbol: Symbol
    open_time: datetime
    close_time: datetime
    open: Money
    high: Money
    low: Money
    close: Money
    volume: int = Field(ge=0, le=2**63 - 1)
    is_closed: Literal[True] = True

    _utc = field_validator("open_time", "close_time")(utc)

    @model_validator(mode="after")
    def valid_bar(self) -> "ObserverCandle":
        o, h, lo, c = (Decimal(v) for v in (self.open, self.high, self.low, self.close))
        if not 0 < lo <= min(o, c) <= max(o, c) <= h:
            raise ValueError("observer_invalid_ohlc")
        if self.close_time - self.open_time != timedelta(hours=1):
            raise ValueError("observer_hour_required")
        return self


class ObserverSignal(Strict):
    symbol: Symbol
    generated_at: datetime
    strategy_version: Literal["v1-deterministic"]
    signal_type: Literal["BUY", "SELL", "HOLD"]
    _utc = field_validator("generated_at")(utc)


class ObserverRisk(Strict):
    symbol: Symbol
    decided_at: datetime
    decision: Literal["APPROVED", "REJECTED"]
    _utc = field_validator("decided_at")(utc)


class ObserverPosition(Strict):
    symbol: Symbol
    quantity: int = Field(ge=1)
    average_price: Money


class ObserverPaper(Strict):
    as_of_utc: datetime
    paused: bool
    cash: Money
    equity: Money
    total_pnl: Money
    positions: tuple[ObserverPosition, ...] = Field(max_length=MAX_SYMBOLS)
    _utc = field_validator("as_of_utc")(utc)


class ObserverBacktest(Strict):
    result_hash: Hash
    return_pct: Money
    max_drawdown_pct: Money
    closed_trades: int = Field(ge=0)
    profit_factor: Money | None


class AIObserverSnapshot(Strict):
    schema_version: Literal["1.0"] = "1.0"
    as_of_utc: datetime
    provider: Literal["alpaca", "simulator"]
    session_state: Literal["connected", "market_closed", "delayed", "degraded", "offline"]
    symbols: tuple[Symbol, ...] = Field(min_length=1, max_length=MAX_SYMBOLS)
    timeframe: Literal["1h"] = "1h"
    candles: tuple[ObserverCandle, ...] = Field(max_length=MAX_SYMBOLS * MAX_CANDLES_PER_SYMBOL)
    signals: tuple[ObserverSignal, ...] = Field(max_length=MAX_SYMBOLS)
    risk_decisions: tuple[ObserverRisk, ...] = Field(max_length=MAX_SYMBOLS)
    paper: ObserverPaper | None
    accepted_backtest: ObserverBacktest | None
    _utc = field_validator("as_of_utc")(utc)

    @model_validator(mode="after")
    def chronology(self) -> "AIObserverSnapshot":
        if tuple(sorted(set(self.symbols))) != self.symbols:
            raise ValueError("observer_symbols_not_canonical")
        keys = [(c.open_time, c.symbol) for c in self.candles]
        if keys != sorted(set(keys)):
            raise ValueError("observer_candles_not_canonical")
        for symbol in self.symbols:
            if sum(c.symbol == symbol for c in self.candles) > MAX_CANDLES_PER_SYMBOL:
                raise ValueError("observer_series_too_large")
        for rows, time_key in (
            (self.candles, "close_time"),
            (self.signals, "generated_at"),
            (self.risk_decisions, "decided_at"),
        ):
            for row in rows:
                if row.symbol not in self.symbols or getattr(row, time_key) > self.as_of_utc:
                    raise ValueError("observer_future_or_unknown_series")
        for rows in (self.signals, self.risk_decisions):
            if [r.symbol for r in rows] != sorted({r.symbol for r in rows}):
                raise ValueError("observer_duplicate_decision")
        if self.paper and self.paper.as_of_utc > self.as_of_utc:
            raise ValueError("observer_future_paper")
        return self

    def payload(self) -> bytes:
        result = canonical(self.model_dump(mode="json"))
        if len(result) > MAX_INPUT_BYTES:
            raise ValueError("observer_snapshot_too_large")
        return result

    @property
    def input_hash(self) -> str:
        return hashlib.sha256(self.payload()).hexdigest()


class Regime(Strict):
    label: Literal["TRENDING", "RANGING", "VOLATILE", "UNCERTAIN"]
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    evidence: tuple[Text, ...] = Field(max_length=8)


class RiskFlag(Strict):
    code: Literal["DATA_STALE", "DATA_QUALITY", "VOLATILITY", "CONCENTRATION", "LOW_LIQUIDITY"]
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    message: Text


class AIObserverOutput(Strict):
    schema_version: Literal["1.0"]
    regime: Regime
    risk_flags: tuple[RiskFlag, ...] = Field(max_length=8)
    observations: tuple[Text, ...] = Field(max_length=12)

    @model_validator(mode="after")
    def safe_prose(self) -> "AIObserverOutput":
        texts = [*self.regime.evidence, *self.observations, *(f.message for f in self.risk_flags)]
        for value in texts:
            if any(unicodedata.category(c).startswith("C") for c in value):
                raise ValueError("observer_control_character")
            if re.search(
                r"(?i)https?[:/]|[a-z]:[\\/]|[/\\]|\.env|api.?key|secret|token|password|postgres|\b(BUY|SELL|order|resume|reset|submit_order)\b",
                value,
            ):
                raise ValueError("observer_disallowed_content")

        # Semantic domain separation checks
        for evidence in self.regime.evidence:
            if re.search(r"(?i)\b(backtest|paper|strategy|risk)\b", evidence):
                raise ValueError("observer_regime_evidence_leak")

        any(re.search(r"(?i)\b(paper.*pnl|pnl.*paper|paper.*profit)\b", obs) for obs in self.observations)  # noqa: E501
        any(re.search(r"(?i)\b(backtest.*pnl|pnl.*backtest|backtest.*profit)\b", obs) for obs in self.observations)  # noqa: E501
        if any(re.search(r"(?i)\b(backtest.*paper|paper.*backtest)\b", obs) for obs in self.observations):  # noqa: E501
            raise ValueError("observer_domain_mix")

        return self


def parse_output(payload: bytes) -> AIObserverOutput:
    if len(payload) > MAX_OUTPUT_BYTES:
        raise ValueError("observer_output_too_large")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("observer_duplicate_json_key")
            result[key] = value
        return result

    # Enforce one complete UTF-8 JSON document, including duplicate-key rejection.
    json.loads(payload.decode("utf-8"), object_pairs_hook=unique)
    return AIObserverOutput.model_validate_json(payload)
