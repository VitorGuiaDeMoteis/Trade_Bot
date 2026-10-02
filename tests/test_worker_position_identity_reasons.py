"""REGRESSION: the worker's position-identity tripwire must name WHICH cause.

`_validate_positions` used to raise `broker_position_identity_unknown` both for a
row whose symbol is missing and for a symbol the broker reported on more than
one row. Those are different broker realities with different remediations: the
first cannot be attributed at all, the second means the position was split
across rows. `degraded_reason` is the only string an operator gets, so the two
causes must stay distinguishable.
"""

import pytest

from services.alpaca_paper.worker import AlpacaPaperWorker


def _position(symbol: str, qty: str = "0.1", market_value: str = "20.00") -> dict:
    return {
        "symbol": symbol,
        "qty": qty,
        "market_value": market_value,
        "avg_entry_price": "200.00",
        "current_price": "200.00",
    }


def _validate(positions: list[dict]) -> None:
    # _validate_positions only reaches self._decimal, a staticmethod: build the
    # instance without __init__ so no engine or broker is constructed.
    AlpacaPaperWorker._validate_positions(
        AlpacaPaperWorker.__new__(AlpacaPaperWorker), positions
    )


def test_missing_symbol_stays_an_identity_failure():
    with pytest.raises(RuntimeError, match="broker_position_identity_unknown"):
        _validate([_position("")])


def test_absent_symbol_stays_an_identity_failure():
    row = _position("AAPL")
    del row["symbol"]
    with pytest.raises(RuntimeError, match="broker_position_identity_unknown"):
        _validate([row])


def test_symbol_split_across_rows_names_the_symbol():
    """REGRESSION: a duplicate row must NOT report the unattributable-row cause."""
    with pytest.raises(RuntimeError) as split:
        _validate([_position("AAPL"), _position("AAPL")])
    assert "broker_position_split_across_rows:AAPL" in str(split.value)
    assert "broker_position_identity_unknown" not in str(split.value)


def test_split_detection_is_case_insensitive():
    """A case-only difference is still the SAME symbol reported twice."""
    with pytest.raises(RuntimeError, match="broker_position_split_across_rows:AAPL"):
        _validate([_position("aapl"), _position("AAPL")])


def test_unmanaged_symbol_is_still_reported_as_unmanaged():
    with pytest.raises(RuntimeError, match="unmanaged_broker_position:MSFT"):
        _validate([_position("MSFT")])


def test_negative_quantity_is_still_reported_as_short():
    with pytest.raises(RuntimeError, match="short_broker_position_forbidden:AAPL"):
        _validate([_position("AAPL", qty="-0.1", market_value="-20.00")])


def test_distinct_managed_symbols_still_pass():
    _validate([_position("AAPL"), _position("SPY"), _position("TSLA")])