from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class PaperOrder(BaseModel):
    order_id: UUID
    run_id: UUID
    signal_id: UUID
    risk_decision_id: UUID
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: int
    status: Literal["FILLED", "REJECTED"]
    requested_at: datetime
    idempotency_key: UUID
    reason: str


class PaperFill(BaseModel):
    fill_id: UUID
    order_id: UUID
    price: Decimal
    reference_price: Decimal
    quantity: int
    fee: Decimal
    slippage: Decimal
    realized_pnl: Decimal
    filled_at: datetime


class PaperPositionResponse(BaseModel):
    symbol: str
    quantity: int
    average_price: Decimal
    current_price: Decimal
    market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    updated_at: datetime


class PaperLink(BaseModel):
    mode: Literal["LOCAL_PAPER"] = "LOCAL_PAPER"
    run_id: UUID | None = None
    status: str = "NOT_REPLAYED"
    reason: str = "not_in_active_replay"
    order: PaperOrder | None = None
    fill: PaperFill | None = None


class PaperPortfolio(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    mode: Literal["REPLAY"] = "REPLAY"
    currency: Literal["USD"] = "USD"
    run_id: UUID | None = None
    status: str = "EMPTY"
    provider: str
    paused: bool = False
    as_of: datetime | None = None
    step: int = 0
    dataset_hash: str | None = None
    dataset_count: int = 0
    initial_cash: Decimal
    cash: Decimal
    market_value: Decimal
    equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    fees: Decimal
    fee_bps: Decimal
    slippage_bps: Decimal
    pnl_basis: Literal["gross_components_net_total"] = "gross_components_net_total"
    reconciled: bool = True
    orders_count: int = 0
    fills_count: int = 0
    positions: list[PaperPositionResponse] = []
    orders: list[PaperOrder] = []
    fills: list[PaperFill] = []


class PaperOrdersPage(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    mode: Literal["REPLAY"] = "REPLAY"
    run_id: UUID | None
    step: int
    items: list[PaperOrder]


class PaperFillsPage(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    mode: Literal["REPLAY"] = "REPLAY"
    run_id: UUID | None
    step: int
    items: list[PaperFill]


class PaperPositionsPage(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    mode: Literal["REPLAY"] = "REPLAY"
    run_id: UUID | None
    step: int
    items: list[PaperPositionResponse]
