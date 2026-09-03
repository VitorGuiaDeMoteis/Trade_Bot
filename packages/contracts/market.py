from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from packages.domain.market import Regime

SimulatorState = Literal["starting", "running", "stopped", "degraded", "stalled"]
ProviderState = Literal[
    "connecting",
    "connected",
    "reconnecting",
    "market_closed",
    "delayed",
    "degraded",
    "offline",
    "configuration_error",
    "starting",
    "stopped",
    "stalled",
]


class CandleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    candle_id: UUID
    stream_id: UUID
    sequence: int = Field(ge=1)
    symbol: str = "TEST"
    timeframe: str = "1h"
    provider: str = "simulator"
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = Field(ge=0)
    regime: Regime | None
    is_closed: bool


class CandleEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["event"] = "event"
    schema_version: Literal["2.0"] = "2.0"
    event_id: UUID
    event_type: Literal["market.candle.closed"] = "market.candle.closed"
    occurred_at: datetime
    correlation_id: UUID
    stream_id: UUID
    sequence: int
    payload: CandleResponse


class MarketDataStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: ProviderState
    provider: str | None = None
    feed: str | None = None
    symbols: list[str] | None = None
    last_persisted_at: datetime | None = None
    error: str | None = None
    timeframe: str = "1h"
    session: str | None = None
    last_message_at: datetime | None = None
    last_bar_at: datetime | None = None
    accelerated: bool = False
    interval_seconds: float | None = None


class MarketSnapshot(BaseModel):
    schema_version: Literal["2.0"] = "2.0"
    stream_id: UUID
    symbol: str = "TEST"
    timeframe: str = "1h"
    candles: list[CandleResponse]
    cursor: int
    high_watermark: int
    has_more: bool
    last_updated_at: datetime | None
    market_data: MarketDataStatus
    correlation_id: UUID
