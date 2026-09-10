from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

class BrokerPosition(BaseModel):
    symbol: str
    quantity: Decimal
    average_price: Decimal
    current_price: Decimal
    market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    updated_at: datetime

class BrokerOrder(BaseModel):
    client_order_id: str
    broker_order_id: str
    symbol: str
    side: str
    status: str
    requested_notional: Decimal | None
    requested_quantity: Decimal | None
    filled_quantity: Decimal
    requested_at: datetime

class BrokerFill(BaseModel):
    broker_fill_id: str
    broker_order_id: str
    symbol: str
    price: Decimal
    quantity: Decimal
    filled_at: datetime

class BrokerPortfolio(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    mode: Literal["BROKER_PAPER"] = "BROKER_PAPER"
    currency: Literal["USD"] = "USD"
    status: str
    provider: str
    paused: bool
    as_of: datetime | None
    cash: Decimal
    market_value: Decimal
    equity: Decimal
    positions: list[BrokerPosition]
    orders: list[BrokerOrder]
    fills: list[BrokerFill]
