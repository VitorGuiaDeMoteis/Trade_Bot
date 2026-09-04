"""Pure local executor. No networking, database, strategy or broker dependency."""

from decimal import Decimal
from typing import Literal

from packages.domain.paper import ZERO, PaperBook, PaperConfig, PaperPosition, PaperResult, money
from packages.domain.risk import RiskDecision


class PaperExecutor:
    def __init__(self, config: PaperConfig) -> None:
        self.config = config

    def fill_price(self, reference: Decimal, side: str) -> Decimal:
        if reference <= ZERO or side not in {"BUY", "SELL"}:
            raise ValueError("invalid_fill_input")
        direction = Decimal("1") if side == "BUY" else Decimal("-1")
        return money(
            reference * (Decimal("1") + direction * self.config.slippage_bps / Decimal("10000"))
        )

    def execute(
        self,
        book: PaperBook,
        symbol: str,
        side: Literal["BUY", "SELL"],
        reference: Decimal,
        quantity: int,
        risk: RiskDecision,
    ) -> PaperResult:
        if risk.decision != "APPROVED":
            raise ValueError("unapproved_risk_cannot_execute")
        if type(quantity) is not int or quantity < 0:
            raise ValueError("integer_share_quantity_required")
        book.reconcile()
        position = book.positions.get(symbol, PaperPosition(symbol))
        if side == "BUY" and position.quantity:
            return PaperResult("NO_ACTION", "position_already_open")
        if side == "SELL" and not position.quantity:
            return PaperResult("NO_ACTION", "no_long_position")
        if side == "SELL":
            quantity = position.quantity
        if quantity < 1:
            return PaperResult("REJECTED", "position_size_below_one_share")
        price = self.fill_price(reference, side)
        notional = money(price * quantity)
        fee = money(notional * self.config.fee_bps / Decimal("10000"))
        if side == "BUY":
            if notional + fee > book.cash:
                return PaperResult("REJECTED", "insufficient_simulated_cash", quantity)
            if notional + fee > money(book.equity * Decimal("0.10")):
                return PaperResult("REJECTED", "position_allocation_exceeded", quantity)
            book.cash = money(book.cash - notional - fee)
            position.quantity = quantity
            position.average_price = price
            realized = ZERO
        else:
            realized = money((price - position.average_price) * quantity)
            book.cash = money(book.cash + notional - fee)
            position.quantity = 0
            position.average_price = ZERO
            position.realized_pnl = money(position.realized_pnl + realized)
            book.realized_pnl = money(book.realized_pnl + realized)
        book.fees = money(book.fees + fee)
        book.positions[symbol] = position
        book.reconcile()
        return PaperResult(
            "FILLED",
            "simulated_fill",
            quantity,
            price,
            fee,
            money(abs(price - reference) * quantity),
            realized,
        )
