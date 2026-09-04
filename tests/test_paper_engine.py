from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal as D
from uuid import uuid4

import pytest

from packages.domain.paper import PaperBook, PaperConfig, PaperPosition, money
from packages.domain.risk import RiskDecision
from services.paper_executor.engine import PaperExecutor
from services.risk_engine.paper_sizing import entry_quantity


def risk() -> RiskDecision:
    return RiskDecision(uuid4(), uuid4(), "APPROVED", "valid", datetime.now(UTC))


def test_buy_sell_fee_slippage_and_pnl() -> None:
    book = PaperBook(D("10000"), D("10000"), marks={"SPY": D("100")})
    executor = PaperExecutor(PaperConfig())
    quantity = entry_quantity(book.equity, executor.fill_price(D("100"), "BUY"), D("1"))
    assert quantity == 9
    buy = executor.execute(book, "SPY", "BUY", D("100"), quantity, risk())
    assert buy.price == D("100.05") and buy.fee == D(".090045")
    assert buy.slippage == D(".45") and book.cash == D("9099.459955")
    assert book.unrealized_pnl == D("-.45")
    book.marks["SPY"] = D("90")
    assert book.unrealized_pnl == D("-90.45")
    book.reconcile()
    book.marks["SPY"] = D("110")
    assert book.unrealized_pnl == D("89.55")
    sell = executor.execute(book, "SPY", "SELL", D("110"), 0, risk())
    assert sell.price == D("109.945") and sell.fee == D(".0989505")
    assert book.realized_pnl == D("89.055")
    assert book.cash == book.equity == D("10088.8660045")
    assert book.total_pnl == book.realized_pnl - book.fees
    assert book.positions["SPY"].quantity == 0
    book.reconcile()


def test_no_pyramiding_no_short_and_insufficient_cash() -> None:
    executor = PaperExecutor(PaperConfig())
    book = PaperBook(D("10000"), D("10000"), marks={"SPY": D("100")})
    assert executor.execute(book, "SPY", "SELL", D("100"), 0, risk()).reason == "no_long_position"
    executor.execute(book, "SPY", "BUY", D("100"), 9, risk())
    cash = book.cash
    assert (
        executor.execute(book, "SPY", "BUY", D("100"), 9, risk()).reason == "position_already_open"
    )
    assert book.cash == cash
    poor = PaperBook(
        D("10000"),
        D("0"),
        positions={"AAPL": PaperPosition("AAPL", 100, D("100"))},
        marks={"AAPL": D("100"), "SPY": D("100")},
    )
    assert (
        executor.execute(poor, "SPY", "BUY", D("100"), 9, risk()).reason
        == "insufficient_simulated_cash"
    )
    assert poor.cash == 0 and "SPY" not in poor.positions


def test_allocation_and_fractional_shares_are_blocked() -> None:
    executor = PaperExecutor(PaperConfig())
    book = PaperBook(D("10000"), D("10000"), marks={"SPY": D("100")})
    assert (
        executor.execute(book, "SPY", "BUY", D("100"), 100, risk()).reason
        == "insufficient_simulated_cash"
    )
    assert (
        executor.execute(book, "SPY", "BUY", D("100"), 11, risk()).reason
        == "position_allocation_exceeded"
    )
    assert entry_quantity(D("100"), D("650"), D("1")) == 0
    assert (
        executor.execute(book, "SPY", "BUY", D("100"), 0, risk()).reason
        == "position_size_below_one_share"
    )
    assert book.cash == D("10000")


def test_unapproved_risk_never_executes_and_corruption_is_visible() -> None:
    book = PaperBook(D("10000"), D("10000"), marks={"SPY": D("100")})
    with pytest.raises(ValueError, match="unapproved"):
        PaperExecutor(PaperConfig()).execute(
            book, "SPY", "BUY", D("100"), 9, replace(risk(), decision="REJECTED")
        )
    book.cash -= D("1")
    with pytest.raises(ValueError, match="reconciliation"):
        book.reconcile()


@pytest.mark.parametrize("cash", ["0", "-1", "NaN", "Infinity"])
def test_invalid_config(cash: str) -> None:
    with pytest.raises(ValueError):
        PaperConfig(initial_cash=D(cash))


def test_binary_float_rejected() -> None:
    with pytest.raises(ValueError):
        money(0.1)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field,value",
    [
        ("initial_cash", "10000.00000000004"),
        ("fee_bps", "1.1234567"),
        ("slippage_bps", "5.1234567"),
    ],
)
def test_paper_config_cannot_be_silently_rounded_by_postgres(field: str, value: str) -> None:
    with pytest.raises(ValueError, match="precision"):
        PaperConfig(**{field: D(value)})
