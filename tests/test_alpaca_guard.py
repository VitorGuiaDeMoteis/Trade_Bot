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