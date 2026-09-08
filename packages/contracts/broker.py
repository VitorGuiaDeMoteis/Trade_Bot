from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Literal, Optional
from dataclasses import dataclass
from datetime import datetime

from packages.domain.paper import PaperBook, PaperResult
from packages.domain.risk import RiskDecision


@dataclass
class BrokerAccount:
    currency: str
    cash: Decimal
    equity: Decimal
    buying_power: Decimal


@dataclass
class BrokerPosition:
    symbol: str
    quantity: int
    average_entry_price: Decimal
    current_price: Decimal


@dataclass
class BrokerFill:
    fill_id: str
    client_order_id: str
    quantity: int
    price: Decimal
    filled_at: datetime


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


class ExecutionBroker(ABC):
    @abstractmethod
    async def execute(
        self,
        book: PaperBook,
        symbol: str,
        side: Literal["BUY", "SELL"],
        reference: Decimal,
        quantity: int,
        risk: RiskDecision,
    ) -> PaperResult:
        pass


class ExternalBroker(ABC):
    @abstractmethod
    async def get_account(self) -> BrokerAccount:
        pass

    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]:
        pass

    @abstractmethod
    async def get_orders(self) -> list[BrokerOrder]:
        pass

    @abstractmethod
    async def get_order_by_client_order_id(self, client_order_id: str) -> Optional[BrokerOrder]:
        pass

    @abstractmethod
    async def submit_order(
        self, symbol: str, side: str, quantity: int, client_order_id: str
    ) -> BrokerOrder:
        pass
