from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Literal

from packages.domain.paper import PaperBook, PaperResult
from packages.domain.risk import RiskDecision


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
