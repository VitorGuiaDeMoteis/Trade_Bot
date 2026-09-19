import pytest

from research.mean_reversion_v1.forward import ForwardPaperEngine, ForwardState
from research.mean_reversion_v1.historical import (
    DiagnosticFirewallError,
    verify_historical_diagnostic_access,
)
from research.mean_reversion_v1.micro_replay import MicroReplayEngine
from research.mean_reversion_v1.robustness import (
    generate_leave_one_out_universes,
    get_qqq_robustness_universe,
    get_substitutions,
)


def test_forward_state_transitions() -> None:
    engine = ForwardPaperEngine()
    assert engine.state == ForwardState.NOT_STARTED

    engine.months_elapsed = 13
    engine.trades_executed = 10
    engine.evaluate_state()
    assert engine.state == ForwardState.NOT_STARTED  # Need 20 trades minimum

    engine.months_elapsed = 25
    engine.evaluate_state()
    assert engine.state == ForwardState.TOO_SPARSE


def test_operational_failure() -> None:
    engine = ForwardPaperEngine()
    engine.operational_failure = True
    engine.evaluate_state()
    assert engine.state == ForwardState.INVALIDATED


def test_micro_replay_fractional_rounding() -> None:
    engine = MicroReplayEngine(capital=50.0, min_order=1.0, precision=6)
    # price = 3.3333333, target = 10.0
    # qty = 10.0 / 3.3333333 = 3.00000003
    qty = engine.calculate_order(3.3333333, 10.0)
    assert qty == 3.0


def test_minimum_order_behavior() -> None:
    engine = MicroReplayEngine(capital=50.0, min_order=1.0, precision=6)
    qty = engine.calculate_order(100.0, 0.5)
    assert qty == 0.0


def test_historical_diagnostic_firewall() -> None:
    with pytest.raises(DiagnosticFirewallError):
        verify_historical_diagnostic_access(seal_valid=False, dev_passed=True, val_passed=True)

    with pytest.raises(DiagnosticFirewallError):
        verify_historical_diagnostic_access(seal_valid=True, dev_passed=False, val_passed=True)

    # Should pass without exception
    verify_historical_diagnostic_access(seal_valid=True, dev_passed=True, val_passed=True)


def test_robustness_universes() -> None:
    subs = get_substitutions()
    assert subs["SPY"] == "VOO"

    qqq_u = get_qqq_robustness_universe()
    assert "QQQ" in qqq_u
    assert len(qqq_u) == 5

    loo = generate_leave_one_out_universes(["A", "B", "C"])
    assert len(loo) == 3
    assert loo[0] == ["B", "C"]
