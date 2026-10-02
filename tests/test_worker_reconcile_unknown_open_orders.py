"""Reconciliation must fail the whole cycle closed on ANY broker/local divergence.

`AlpacaPaperWorker._assert_open_orders_known` runs on EVERY cycle
(worker.py:150), between order reconciliation and the broker snapshot save.
Its contract is inverted from most of the codebase: it never repairs anything,
it only raises. Any divergence between an order the broker still considers open
and the local `paper_orders`/`broker_orders` rows raises a `RuntimeError`, which
`_run` turns into `_enter_degraded` -- and a degraded worker releases NO new
execution for the rest of the process lifetime.

So each branch below is a trading-safety guarantee, not a diagnostic:

- an open order with no local row at all means the bot's picture of what is
  exposed is incomplete, and sizing new orders on top of it could oversell;
- symbol/side divergence means the broker holds an order the bot believes is
  something else, so the position it derives is wrong;
- status divergence means the broker still holds a live order for a row the bot
  already considers terminal (FILLED/CANCELLED/REJECTED) -- the classic
  double-exposure shape;
- notional/quantity divergence means the order actually working at the broker
  has a different size than the one the risk decision approved;
- a missing remote numeric is treated as divergence, never as "equal", because
  an unsourceable size must not be assumed to match.

Nothing here needs Postgres, the broker or a real engine: the method performs a
single read and then compares already-materialised rows, so a scripted
connection returning canned local rows is enough to drive every branch.
"""

from decimal import Decimal
from typing import Any

import pytest

from services.alpaca_paper.worker import AlpacaPaperWorker

BROKER_ID = "b-123"
CLIENT_ID = "c-123"


def _local_row(
    *,
    broker_order_id: str | None = BROKER_ID,
    client_order_id: str | None = CLIENT_ID,
    symbol: str = "AAPL",
    side: str = "BUY",
    status: str = "NEW",
    requested_notional: Any = None,
    requested_quantity: Any = None,
) -> dict[str, Any]:
    """One row of the broker_orders JOIN paper_orders read the worker performs."""
    return {
        "broker_order_id": broker_order_id,
        "client_order_id": client_order_id,
        "requested_notional": requested_notional,
        "requested_quantity": requested_quantity,
        "symbol": symbol,
        "side": side,
        "status": status,
    }


def _remote_order(
    *,
    order_id: str | None = BROKER_ID,
    client_order_id: str | None = CLIENT_ID,
    symbol: str = "AAPL",
    side: str = "BUY",
    notional: Any = None,
    qty: Any = None,
) -> dict[str, Any]:
    """An order as returned by the broker's open-orders endpoint."""
    return {
        "id": order_id,
        "client_order_id": client_order_id,
        "symbol": symbol,
        "side": side,
        "notional": notional,
        "qty": qty,
    }


class _ScriptedResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def mappings(self) -> "_ScriptedResult":
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


class _ScriptedConnection:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def execute(self, statement, *args, **kwargs) -> _ScriptedResult:
        return _ScriptedResult(self._rows)

    def __enter__(self) -> "_ScriptedConnection":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


class _ScriptedEngine:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def connect(self) -> _ScriptedConnection:
        return _ScriptedConnection(self.rows)


def _assert(local_rows: list[dict[str, Any]], open_orders: list[dict[str, Any]]) -> None:
    worker = AlpacaPaperWorker(_ScriptedEngine(local_rows), None, None)  # type: ignore[arg-type]
    worker._assert_open_orders_known(open_orders)


def test_no_open_orders_never_raises_even_with_local_rows():
    """The empty case is the normal one: nothing working at the broker."""
    _assert([_local_row(requested_notional=Decimal("100"))], [])


def test_matching_buy_notional_passes():
    """A BUY is sized by notional, so that is the field compared."""
    _assert(
        [_local_row(requested_notional=Decimal("100"))],
        [_remote_order(notional="100")],
    )


def test_matching_sell_quantity_passes():
    _assert(
        [
            _local_row(
                side="SELL",
                status="PARTIALLY_FILLED",
                requested_quantity=Decimal("10"),
            )
        ],
        [_remote_order(side="SELL", qty="10")],
    )


def test_match_by_client_order_id_when_broker_id_not_stored_yet():
    """The broker id is written after submission; the client id exists first."""
    _assert(
        [_local_row(broker_order_id=None, requested_notional=Decimal("100"))],
        [_remote_order(order_id="b-new", notional="100")],
    )


def test_remote_symbol_and_side_are_case_insensitive():
    """Alpaca returns lowercase sides; a case-only difference is not divergence."""
    _assert(
        [_local_row(requested_notional=Decimal("100"))],
        [_remote_order(symbol="aapl", side="buy", notional="100")],
    )


def test_unknown_open_order_raises():
    with pytest.raises(RuntimeError, match=f"unknown_broker_open_order:{BROKER_ID}"):
        _assert([], [_remote_order(notional="100")])


def test_open_order_with_no_identifier_at_all_raises():
    """A remote order with no id and no client id cannot be matched to anything."""
    with pytest.raises(RuntimeError, match="unknown_broker_open_order:missing_id"):
        _assert([], [_remote_order(order_id=None, client_order_id=None, notional="100")])


def test_symbol_divergence_raises():
    with pytest.raises(RuntimeError, match=f"broker_order_symbol_divergence:{BROKER_ID}"):
        _assert(
            [_local_row(symbol="AAPL", requested_notional=Decimal("100"))],
            [_remote_order(symbol="MSFT", notional="100")],
        )


def test_side_divergence_raises():
    with pytest.raises(RuntimeError, match=f"broker_order_side_divergence:{BROKER_ID}"):
        _assert(
            [_local_row(side="BUY", requested_notional=Decimal("100"))],
            [_remote_order(side="SELL", qty="10")],
        )


def test_status_divergence_raises_when_local_row_is_terminal():
    """Broker still open on a row the bot considers filled: the double-exposure case."""
    with pytest.raises(RuntimeError, match=f"broker_order_status_divergence:{BROKER_ID}"):
        _assert(
            [_local_row(status="FILLED", requested_notional=Decimal("100"))],
            [_remote_order(notional="100")],
        )


def test_buy_notional_divergence_raises():
    with pytest.raises(RuntimeError, match=f"broker_order_notional_divergence:{BROKER_ID}"):
        _assert(
            [_local_row(requested_notional=Decimal("100"))],
            [_remote_order(notional="250")],
        )


def test_buy_notional_missing_on_broker_side_raises():
    """An unsourceable size must never be assumed equal to the approved one."""
    with pytest.raises(RuntimeError, match=f"broker_order_notional_divergence:{BROKER_ID}"):
        _assert([_local_row(requested_notional=Decimal("100"))], [_remote_order()])


def test_buy_notional_missing_on_local_side_raises():
    with pytest.raises(RuntimeError, match=f"broker_order_notional_divergence:{BROKER_ID}"):
        _assert([_local_row(requested_notional=None)], [_remote_order(notional="100")])


def test_sell_quantity_divergence_raises():
    with pytest.raises(RuntimeError, match=f"broker_order_quantity_divergence:{BROKER_ID}"):
        _assert(
            [_local_row(side="SELL", requested_quantity=Decimal("10"))],
            [_remote_order(side="SELL", qty="11")],
        )


def test_sell_quantity_missing_on_broker_side_raises():
    with pytest.raises(RuntimeError, match=f"broker_order_quantity_divergence:{BROKER_ID}"):
        _assert(
            [_local_row(side="SELL", requested_quantity=Decimal("10"))],
            [_remote_order(side="SELL")],
        )


def test_sell_quantity_missing_on_local_side_raises():
    """A local SELL row with no size must not be read as matching the broker.

    The SELL branch of `_assert_open_orders_known` compares the remote qty
    against `requested_quantity`, which is NULL for a notional order. Every
    execution gate here sizes a SELL from that column, so a NULL means "size
    unknown", never "size zero matches"; the raise keeps the cycle fail-closed
    rather than accepting an unverifiable open sell.
    """
    with pytest.raises(RuntimeError, match=f"broker_order_quantity_divergence:{BROKER_ID}"):
        _assert(
            [_local_row(side="SELL", requested_quantity=None)],
            [_remote_order(side="SELL", qty="10")],
        )


def test_unparsable_remote_notional_fails_closed_as_invalid_broker_field():
    """A junk size raises the parse error, still failing the cycle closed."""
    with pytest.raises(RuntimeError, match="invalid_broker_open_order_notional"):
        _assert(
            [_local_row(requested_notional=Decimal("100"))],
            [_remote_order(notional="not-a-number")],
        )


def test_one_known_order_does_not_mask_a_second_unknown_one():
    """Every remote order is checked; a known sibling must not short-circuit.

    The second remote order must be genuinely unknown, so it gets its OWN
    client id too: Alpaca assigns a unique client_order_id per order, and the
    worker falls back to that id when the broker id is not stored locally yet
    (pinned by test_match_by_client_order_id_when_broker_id_not_stored_yet).
    Sharing CLIENT_ID here would make the match-by-client-id fallback the
    correct answer and the test would assert nothing.
    """
    with pytest.raises(RuntimeError, match="unknown_broker_open_order:b-other"):
        _assert(
            [_local_row(requested_notional=Decimal("100"))],
            [
                _remote_order(notional="100"),
                _remote_order(order_id="b-other", client_order_id="c-other", notional="100"),
            ],
        )