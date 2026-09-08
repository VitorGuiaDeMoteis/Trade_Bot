from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class BrokerAccount:
    currency: str
    equity: Decimal
    cash: Decimal
    buying_power: Decimal


@dataclass
class BrokerPosition:
    symbol: str
    quantity: int
    average_entry_price: Decimal
    current_price: Decimal


@dataclass
class BrokerOrder:
    client_order_id: str
    broker_order_id: str
    symbol: str
    side: str
    status: str
    requested_qty: int
    filled_qty: int
    filled_avg_price: Decimal
    submitted_at: datetime
    updated_at: datetime


@dataclass
class BrokerFill:
    fill_id: str
    client_order_id: str
    quantity: int
    price: Decimal
    filled_at: datetime


@dataclass
class BrokerClock:
    is_open: bool
    timestamp: datetime


class ExternalBroker:
    async def get_account(self) -> BrokerAccount:
        raise NotImplementedError

    async def get_positions(self) -> list[BrokerPosition]:
        raise NotImplementedError

    async def get_orders(self) -> list[BrokerOrder]:
        raise NotImplementedError

    async def get_order_by_client_order_id(self, client_order_id: str) -> BrokerOrder | None:
        raise NotImplementedError

    async def submit_order(
        self, symbol: str, side: str, quantity: int, client_order_id: str
    ) -> BrokerOrder:
        raise NotImplementedError

    async def get_clock(self) -> BrokerClock:
        raise NotImplementedError
