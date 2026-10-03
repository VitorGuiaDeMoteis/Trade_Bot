"""Regression: the paginated paper pages must report the run's real `mode`.

`paper_routes.get_positions/get_orders/get_fills` are thin wrappers around
`read_portfolio()`, which returns a `PaperPortfolio` carrying the active run's
real `mode` (published as ALPACA_PAPER since the `paper_queries.portfolio` fix).
Each wrapper built its page with `run_id`/`step`/`items` only, so the page fell
back to its own `mode` default of "REPLAY" -- and worse, that field was pinned to
`Literal["REPLAY"]`, so the true mode could not even be passed without raising.

Result: for one and the same active alpaca_paper book,
`/api/v1/paper/portfolio` reported `mode: "ALPACA_PAPER"` while
`/api/v1/paper/orders|fills|positions` reported `mode: "REPLAY"` for the same
`run_id`. An operator or downstream consumer reconciling those payloads sees a
contradiction about which executor produced the money, and `mode` is the field
that is supposed to say so.

No Postgres and no HTTP here: `read_portfolio` is stubbed and the route
functions are called directly, mirroring the broker-route regression tests.
"""

from typing import Any, cast

import pytest

from packages.contracts.paper import (
    PaperFill,
    PaperOrder,
    PaperPortfolio,
    PaperPositionResponse,
)
from services.api import paper_routes
from services.api.paper_routes import get_fills, get_orders, get_positions

NOW = "2026-10-03T00:00:00+00:00"


def _order() -> PaperOrder:
    from uuid import uuid4

    return PaperOrder(
        order_id=uuid4(),
        run_id=uuid4(),
        signal_id=uuid4(),
        risk_decision_id=uuid4(),
        symbol="AAPL",
        side="BUY",
        quantity="1",
        # `PaperOrder.status` is a required field with NO default (contracts
        # paper.py), so the fixture must set it or pydantic rejects the row
        # before any assertion runs.
        status="FILLED",
        requested_at=NOW,
        idempotency_key=uuid4(),
        reason="test",
    )


def _fill(order: PaperOrder) -> PaperFill:
    from uuid import uuid4

    return PaperFill(
        fill_id=uuid4(),
        order_id=order.order_id,
        price="100",
        reference_price="100",
        quantity="1",
        filled_at=NOW,
    )


def _position() -> PaperPositionResponse:
    return PaperPositionResponse(
        symbol="AAPL",
        quantity="1",
        average_price="100",
        current_price="101",
        market_value="101",
        updated_at=NOW,
    )


def _portfolio(mode: str) -> PaperPortfolio:
    """A portfolio as `read_portfolio` would return it for the active run."""
    from decimal import Decimal
    from uuid import uuid4

    order = _order()
    return PaperPortfolio(
        mode=cast(Any, mode),
        provider="alpaca",
        run_id=uuid4(),
        status="ACTIVE",
        cash=Decimal("10000"),
        market_value=Decimal("101"),
        equity=Decimal("10101"),
        step=42,
        positions=[_position()],
        orders=[order],
        fills=[_fill(order)],
    )


@pytest.fixture
def stub_read_portfolio(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Capture the page the routes build, without a database behind them."""

    def _install(mode: str) -> dict[str, Any]:
        captured: dict[str, Any] = {}
        # ONE book per install: the routes each call read_portfolio, and a
        # freshly minted portfolio per call would carry a different run_id each
        # time, so no page could ever agree with the book it was built from.
        book = _portfolio(mode)
        captured["book"] = book

        def _fake(request: Any, response: Any, limit: int = 50) -> PaperPortfolio:
            captured["limit"] = limit
            return book

        monkeypatch.setattr(paper_routes, "read_portfolio", _fake)
        return captured

    return _install


def _call(route: Any, captured: dict[str, Any], *args: Any) -> Any:
    # Stubs stand in for the real Request/Response the FastAPI signature takes;
    # the routes are called directly so the annotations are widened.
    return route(cast(Any, None), cast(Any, None), *args)


@pytest.mark.parametrize("mode", ["ALPACA_PAPER", "REPLAY"])
def test_pages_publish_the_portfolio_mode_not_a_hardcoded_default(
    stub_read_portfolio: Any, mode: str
) -> None:
    """Every page must carry the mode of the book it was built from.

    Parametrised over both legal `paper_runs.mode` values so the test cannot
    pass by stamping one constant: a REPLAY run and an ALPACA_PAPER run must be
    distinguishable on the page exactly as they are on the portfolio.
    """
    captured = stub_read_portfolio(mode)

    positions = _call(get_positions, captured)
    orders = _call(get_orders, captured, 7)
    fills = _call(get_fills, captured, 7)

    assert positions.mode == mode
    assert orders.mode == mode
    assert fills.mode == mode
    # The pre-fix payload claimed REPLAY on every one of these three endpoints.
    assert orders.mode != ("ALPACA_PAPER" if mode == "REPLAY" else "REPLAY")


def test_pages_keep_the_run_id_step_and_items_they_already_carried(
    stub_read_portfolio: Any,
) -> None:
    """The mode fix must not disturb the fields these pages already published."""
    captured = stub_read_portfolio("ALPACA_PAPER")
    book = captured["book"]

    positions = _call(get_positions, captured)
    orders = _call(get_orders, captured, 7)
    fills = _call(get_fills, captured, 7)

    for page in (positions, orders, fills):
        assert page.run_id == book.run_id
        assert page.step == book.step
    assert positions.items == book.positions
    assert orders.items == book.orders
    assert fills.items == book.fills
    # `limit` still reaches read_portfolio on both paged endpoints.
    assert captured["limit"] == 7


def test_mode_literal_matches_the_run_mode_constraint() -> None:
    """The pages accept exactly what `paper_runs.mode` can store.

    `ck_paper_run_mode` at migration head f2c8a51d9b10 is
    `mode IN ('REPLAY','ALPACA_PAPER')`. If the page Literal were ever widened
    or narrowed away from that pair, the endpoint would either reject a real run
    mode at serialisation time or accept a value no run can produce.
    """
    from typing import get_args

    from packages.contracts.paper import PaperFillsPage, PaperOrdersPage, PaperPositionsPage

    for model in (PaperOrdersPage, PaperFillsPage, PaperPositionsPage):
        assert set(get_args(model.model_fields["mode"].annotation)) == {"REPLAY", "ALPACA_PAPER"}