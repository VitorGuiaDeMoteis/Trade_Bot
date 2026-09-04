"""Local paper accounting. Money never passes through binary floating point."""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Literal

ZERO = Decimal("0")
UNIT = Decimal("0.0000000001")


def money(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("invalid_decimal_money")
    return value.quantize(UNIT, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class PaperConfig:
    initial_cash: Decimal = Decimal("10000")
    fee_bps: Decimal = Decimal("1")
    slippage_bps: Decimal = Decimal("5")

    def __post_init__(self) -> None:
        if not ZERO < money(self.initial_cash) <= Decimal("1000000000"):
            raise ValueError("invalid_initial_cash")
        if self.initial_cash != money(self.initial_cash):
            raise ValueError("paper_initial_cash_storage_precision")
        for value in (self.fee_bps, self.slippage_bps):
            if not ZERO <= money(value) <= Decimal("100"):
                raise ValueError("invalid_paper_bps")
            if value != value.quantize(Decimal("0.000001")):
                raise ValueError("paper_bps_storage_precision")


@dataclass
class PaperPosition:
    symbol: str
    quantity: int = 0
    average_price: Decimal = ZERO
    realized_pnl: Decimal = ZERO  # gross closed-trade P&L; fees reported separately


@dataclass
class PaperBook:
    initial_cash: Decimal
    cash: Decimal
    fees: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    positions: dict[str, PaperPosition] = field(default_factory=dict)
    marks: dict[str, Decimal] = field(default_factory=dict)

    @property
    def market_value(self) -> Decimal:
        return money(
            sum(
                (p.quantity * self.marks[p.symbol] for p in self.positions.values() if p.quantity),
                ZERO,
            )
        )

    @property
    def unrealized_pnl(self) -> Decimal:
        return money(
            sum(
                (
                    (self.marks[p.symbol] - p.average_price) * p.quantity
                    for p in self.positions.values()
                    if p.quantity
                ),
                ZERO,
            )
        )

    @property
    def equity(self) -> Decimal:
        return money(self.cash + self.market_value)

    @property
    def total_pnl(self) -> Decimal:
        return money(self.equity - self.initial_cash)

    def reconcile(self) -> None:
        if self.cash < ZERO or any(p.quantity < 0 for p in self.positions.values()):
            raise ValueError("paper_negative_balance_or_position")
        if self.equity != money(
            self.initial_cash + self.realized_pnl + self.unrealized_pnl - self.fees
        ):
            raise ValueError("paper_reconciliation_failed")


@dataclass(frozen=True)
class PaperResult:
    status: Literal["FILLED", "REJECTED", "NO_ACTION"]
    reason: str
    quantity: int = 0
    price: Decimal = ZERO
    fee: Decimal = ZERO
    slippage: Decimal = ZERO  # total monetary impact versus reference, not bps
    realized_pnl: Decimal = ZERO
