from decimal import Decimal
from services.alpaca_paper.guard import ExecutionGuard

def test_no_short_allowed():
    # 1. No position, SELL -> Rejected
    approved, reason = ExecutionGuard.evaluate(
        side="SELL",
        symbol="AAPL",
        positions=[],
        snapshot={"equity": "1000"},
        last_equity=Decimal("1000")
    )
    assert not approved
    assert "SHORT" in reason

    # 2. Position with 0 quantity, SELL -> Rejected
    approved, reason = ExecutionGuard.evaluate(
        side="SELL",
        symbol="AAPL",
        positions=[{"symbol": "AAPL", "quantity": "0", "market_value": "0"}],
        snapshot={"equity": "1000"},
        last_equity=Decimal("1000")
    )
    assert not approved
    assert "SHORT" in reason

    # 3. Valid long position, SELL -> Approved
    approved, reason = ExecutionGuard.evaluate(
        side="SELL",
        symbol="AAPL",
        positions=[{"symbol": "AAPL", "quantity": "1", "market_value": "150"}],
        snapshot={"equity": "1000"},
        last_equity=Decimal("1000")
    )
    assert approved

def test_daily_loss_circuit_breaker():
    # Loss is $6 (1000 -> 994)
    # BUY should be rejected
    approved, reason = ExecutionGuard.evaluate(
        side="BUY",
        symbol="AAPL",
        positions=[],
        snapshot={"equity": "994"},
        last_equity=Decimal("1000")
    )
    assert not approved
    assert "Circuit breaker" in reason

    # SELL (closing a position) should be allowed even if circuit breaker hit
    approved, reason = ExecutionGuard.evaluate(
        side="SELL",
        symbol="AAPL",
        positions=[{"symbol": "AAPL", "quantity": "1", "market_value": "150"}],
        snapshot={"equity": "994"},
        last_equity=Decimal("1000")
    )
    assert approved

def test_max_exposure_and_pyramiding():
    # Has AAPL, trying to buy AAPL again -> Rejected (no pyramiding)
    approved, reason = ExecutionGuard.evaluate(
        side="BUY",
        symbol="AAPL",
        positions=[{"symbol": "AAPL", "quantity": "1", "market_value": "10"}],
        snapshot={"equity": "1000"},
        last_equity=Decimal("1000")
    )
    assert not approved
    assert "Máximo 1 posição" in reason

    # Has 3 positions totaling $30 -> Trying to buy a 4th symbol -> Rejected
    # Wait, ALLOWED_SYMBOLS is only SPY, AAPL, TSLA (3 max anyway).
    # But let's say total exposure is $30
    approved, reason = ExecutionGuard.evaluate(
        side="BUY",
        symbol="TSLA",
        positions=[
            {"symbol": "AAPL", "quantity": "1", "market_value": "10"},
            {"symbol": "SPY", "quantity": "1", "market_value": "20"},
        ],
        snapshot={"equity": "1000"},
        last_equity=Decimal("1000")
    )
    assert not approved
    assert "Exposição máxima total" in reason

def test_dust_residual():
    # Dust threshold is $1.00. Position with $0.05 is dust.
    # 1. Attempting to BUY when we have dust -> Approved (does not trigger pyramiding limit)
    approved, reason = ExecutionGuard.evaluate(
        side="BUY",
        symbol="AAPL",
        positions=[{"symbol": "AAPL", "quantity": "0.0001", "market_value": "0.05"}],
        snapshot={"equity": "1000"},
        last_equity=Decimal("1000")
    )
    assert not approved # Dust now blocks BUY (no pyramiding)

    # 2. Attempting to SELL when we have dust -> Approved
    approved, reason = ExecutionGuard.evaluate(
        side="SELL",
        symbol="AAPL",
        positions=[{"symbol": "AAPL", "quantity": "0.0001", "market_value": "0.05"}],
        snapshot={"equity": "1000"},
        last_equity=Decimal("1000")
    )
    assert approved

def test_lowercase_broker_symbol_still_blocks_pyramiding():
    """A position held under the broker's own casing must still block a 2nd BUY.

    `_net_positions` keys its map on the symbol string it is handed, while
    `evaluate` looks the position up under the decision's symbol. When those
    two disagreed on casing ("aapl" vs "AAPL") the netting key never matched,
    `current_pos` came back None, and BOTH position-derived rules silently
    stopped applying: the pyramiding check is guarded by `if current_pos and
    current_qty > 0`, so a held position bought a SECOND time, and the
    exposure sum never counted the position being opened on top of.
    `PaperAlpacaWorker` already upper-cases in `_validate_positions` and
    `_save_broker_snapshot`, so the guard was the odd component out.
    """
    approved, reason = ExecutionGuard.evaluate(
        side="BUY",
        symbol="AAPL",
        positions=[{"symbol": "aapl", "quantity": "1", "market_value": "10"}],
        snapshot={"equity": "1000"},
        last_equity=Decimal("1000")
    )
    assert not approved
    assert "Máximo 1 posição" in reason

def test_lowercase_broker_symbol_still_closes_an_open_position():
    """The same mismatch must not make a real position look absent to a SELL.

    This is the fail-closed direction of the same bug: with `current_pos`
    None, the SELL branch reported "qty indisponivel" and refused to close a
    position the broker actually held. The bot would leave the position open
    forever and could not stop adding exposure to the symbol.
    """
    approved, reason = ExecutionGuard.evaluate(
        side="SELL",
        symbol="AAPL",
        positions=[{"symbol": "aapl", "quantity": "1", "market_value": "10"}],
        snapshot={"equity": "1000"},
        last_equity=Decimal("1000")
    )
    assert approved

def test_net_positions_collapses_mixed_case_legs_of_one_symbol():
    """Two rows for one symbol differing only in case are ONE position.

    Before normalisation these netted as two entries, and the exposure sum
    added each leg separately while the pyramiding rule looked at a key that
    matched neither request symbol.
    """
    netted = ExecutionGuard._net_positions(
        [
            {"symbol": "AAPL", "quantity": "1", "market_value": "10"},
            {"symbol": "aapl", "quantity": "2", "market_value": "20"},
        ]
    )
    assert list(netted) == ["AAPL"]
    assert netted["AAPL"]["qty"] == Decimal("3")
    assert netted["AAPL"]["market_value"] == Decimal("30")
    assert netted["AAPL"]["qty_known"]
    assert netted["AAPL"]["market_value_known"]