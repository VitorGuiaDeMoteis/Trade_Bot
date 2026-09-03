from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from packages.domain.market import Regime

SimulatorState = Literal["starting", "running", "stopped", "degraded", "stalled"]


class CandleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    candle_id: UUID
    stream_id: UUID
    sequence: int = Field(ge=1)
    symbol: Literal["TEST"] = "TEST"
    timeframe: Literal["1h"] = "1h"
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = Field(ge=0)
    regime: Regime


class CandleEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["event"] = "event"
    schema_version: Literal["1.0"] = "1.0"
    event_id: UUID
    event_type: Literal["market.candle.closed"] = "market.candle.closed"
    occurred_at: datetime
    correlation_id: UUID
    stream_id: UUID
    sequence: int
    payload: CandleResponse


class SimulationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: SimulatorState
    seed: int
    start: datetime
    interval_seconds: float
    accelerated: bool
    last_persisted_at: datetime | None = None
    error: str | None = None


class MarketSnapshot(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    stream_id: UUID
    symbol: Literal["TEST"] = "TEST"
    timeframe: Literal["1h"] = "1h"
    candles: list[CandleResponse]
    cursor: int
    high_watermark: int
    has_more: bool
    last_updated_at: datetime | None
    simulator: SimulationStatus
    correlation_id: UUID
