from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

# One source of truth for every payload that names its executor. The paginated
# pages used to declare `Literal["REPLAY"]` of their own, so a live alpaca_paper
# run was published as REPLAY by /paper/orders|fills|positions while
# /paper/portfolio -- built from the same `portfolio()` call -- reported
# ALPACA_PAPER for the same book. `paper_runs.mode` is CHECK-constrained to
# exactly these two values, so widening the page Literal accepts the run's real
# mode instead of hardcoding the default.
PaperMode = Literal["REPLAY", "ALPACA_PAPER"]


class PaperOrder(BaseModel):
    order_id: UUID
    run_id: UUID
    signal_id: UUID
    risk_decision_id: UUID
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    filled_quantity: Decimal = Decimal(0)
    status: Literal[
        "SUBMITTING",
        "NEW",
        "ACCEPTED",
        "PENDING_NEW",
        "PARTIALLY_FILLED",
        "FILLED",
        "PENDING_CANCEL",
        "CANCELED",
        "REJECTED",
        "EXPIRED",
        "REPLACED",
        "UNKNOWN",
    ]
    requested_at: datetime
    idempotency_key: UUID
    reason: str
    client_order_id: str | None = None
    broker_order_id: str | None = None
    broker_status: str | None = None
    last_reconciled_at: datetime | None = None


class PaperFill(BaseModel):
    fill_id: UUID
    order_id: UUID
    broker_fill_id: str | None = None
    price: Decimal
    reference_price: Decimal
    quantity: Decimal
    fee: Decimal | None = None
    slippage: Decimal | None = None
    realized_pnl: Decimal | None = None
    filled_at: datetime


class PaperPositionResponse(BaseModel):
    symbol: str
    quantity: Decimal
    average_price: Decimal
    current_price: Decimal
    market_value: Decimal
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
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
    mode: PaperMode = "REPLAY"
    currency: Literal["USD"] = "USD"
    run_id: UUID | None = None
    status: str = "EMPTY"
    provider: str
    paused: bool = False
    as_of: datetime | None = None
    step: int = 0
    dataset_hash: str | None = None
    dataset_count: int = 0
    initial_cash: Decimal | None = None
    cash: Decimal
    market_value: Decimal
    equity: Decimal
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    total_pnl: Decimal | None = None
    fees: Decimal | None = None
    fee_bps: Decimal | None = None
    slippage_bps: Decimal | None = None
    pnl_basis: Literal["gross_components_net_total"] = "gross_components_net_total"
    reconciled: bool = True
    last_reconciled_at: datetime | None = None
    degraded: bool = False
    orders_count: int = 0
    fills_count: int = 0
    positions: list[PaperPositionResponse] = []
    orders: list[PaperOrder] = []
    fills: list[PaperFill] = []


class PaperOrdersPage(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    mode: PaperMode = "REPLAY"
    run_id: UUID | None
    step: int
    items: list[PaperOrder]


class PaperFillsPage(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    mode: PaperMode = "REPLAY"
    run_id: UUID | None
    step: int
    items: list[PaperFill]


class PaperPositionsPage(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    mode: PaperMode = "REPLAY"
    run_id: UUID | None
    step: int
    items: list[PaperPositionResponse]
