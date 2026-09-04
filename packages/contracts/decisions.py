
"""Read-only, versioned observation of persisted strategy and risk decisions."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from packages.contracts.market import CandleResponse, MarketDataStatus
from packages.contracts.paper import PaperFill, PaperOrder
from packages.domain.risk import DecisionType
from packages.domain.strategy import SignalType


class SignalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: UUID
    candle_id: UUID
    stream_id: UUID
    strategy_version: str
    signal_type: SignalType
    reason: str = Field(min_length=1)
    generated_at: datetime


class RiskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: UUID
    signal_id: UUID
    decision: DecisionType
    reason: str
    decided_at: datetime




class PaperDecisionResponse(BaseModel):
    status: str
    run_id: UUID | None = None
    order: PaperOrder | None = None
    fill: PaperFill | None = None


class DecisionItem(BaseModel):
    candle: CandleResponse
    signal: SignalResponse
    risk: RiskResponse
    paper: PaperDecisionResponse | None = None


class DecisionsSnapshot(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    symbol: str
    timeframe: Literal["1h"] = "1h"
    symbols: list[str]
    items: list[DecisionItem]
    limit: int
    execution: Literal["NONE"] = "NONE"
    market_data: MarketDataStatus
    correlation_id: UUID
