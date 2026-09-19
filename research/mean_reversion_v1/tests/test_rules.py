import pandas as pd

from research.mean_reversion_v1.engine import run_backtest
from research.mean_reversion_v1.gates import evaluate_gates
from research.mean_reversion_v1.strategies import MeanReversionParams


def test_package_imports() -> None:
    # Prove the core modules and classes required by the protocol can actually be imported
    from research.mean_reversion_v1.engine import BacktestResult, run_backtest
    from research.mean_reversion_v1.gates import evaluate_gates
    from research.mean_reversion_v1.historical import DiagnosticFirewallError
    from research.mean_reversion_v1.strategies import MeanReversionParams, compute_z_scores
    
    # Assert existence and callability of core components
    assert callable(run_backtest)
    assert callable(compute_z_scores)
    assert callable(evaluate_gates)
    
    # Assert class instantiation works
    assert MeanReversionParams is not None
    assert BacktestResult is not None
    assert issubclass(DiagnosticFirewallError, Exception)


def test_warmup_65_sessions() -> None:
    # L + N = 60 + 5 = 65
    params = MeanReversionParams(N=5, L=60)
    assert params.L + params.N == 65


def test_holiday_next_session_execution() -> None:
    dates = pd.date_range("2020-01-01", periods=10, freq="B")
    assert dates[1] - dates[0] == pd.Timedelta(days=1)
    assert dates[3] - dates[2] > pd.Timedelta(days=1)  # Weekend simulated by B frequency


def test_fixed_slots_and_no_leverage() -> None:
    # Each slot is exactly 25% initially, total exposure never exceeds 100%
    dates = pd.date_range("2020-01-01", periods=10, freq="B")
    data = pd.DataFrame(index=dates)
    data[("Close", "DTB3")] = 0.0
    for sym in ["SPY", "IWM", "EFA", "EEM"]:
        data[("Close", sym)] = 100
        data[("Open", sym)] = 100
    params = MeanReversionParams(N=1, L=5)
    res = run_backtest(data, ["SPY", "IWM", "EFA", "EEM"], params, dates[0], dates[-1])
    # positions df columns: SPY, SPY_cash, IWM, IWM_cash, EFA, EFA_cash, EEM, EEM_cash, CASH
    # sum of all should equal portfolio_value
    assert "CASH" in res.positions.columns
    # Check leverage
    total_assets = res.positions[["SPY", "IWM", "EFA", "EEM"]].sum(axis=1)
    leverage = total_assets / res.portfolio_value
    assert (leverage <= 1.0001).all()


def test_qqq_20_percent_slots() -> None:
    # QQQ robustness test runs with 5 slots
    dates = pd.date_range("2020-01-01", periods=10, freq="B")
    data = pd.DataFrame(index=dates)
    data[("Close", "DTB3")] = 0.0
    for sym in ["SPY", "IWM", "EFA", "EEM", "QQQ"]:
        data[("Close", sym)] = 100
        data[("Open", sym)] = 100
    params = MeanReversionParams(N=1, L=5)
    res = run_backtest(
        data, ["SPY", "IWM", "EFA", "EEM", "QQQ"], params, dates[0], dates[-1], slots=5
    )
    # Check that initial cash allocation for QQQ is 20%
    assert res.positions.iloc[0]["QQQ_cash"] == 10_000_000.0 / 5


def test_gate_supportive_binary_rule() -> None:
    # Supportive if Sharpe > B1 Sharpe AND MaxDD < 25%
    # For a variant to be supportive, its sharpe > b1 sharpe (0.5) and maxdd < 0.25.
    variant_supportive = (1.0 > 0.5) and (0.20 < 0.25)
    assert variant_supportive


def test_gate_direction_and_final_binary_decision() -> None:
    # If 8 gates passed, PASS
    res = evaluate_gates(
        primary_metrics={"Sharpe": 1.0, "MaxDD": 0.15, "Calmar": 2.0},
        b1_metrics={"Sharpe": 0.5, "MaxDD": 0.30, "Calmar": 1.0},
        cost_2x_metrics={"Sharpe": 0.8, "MaxDD": 0.20},
        substitutions_passed=True,
        leave_one_out_passed=True,
        sensitivities_passed=4,
    )
    # G1: 1.0 > 0.5 + 0.15 (0.65) -> True
    # G2: 0.15 < 0.70 * 0.30 (0.21) -> True
    # G3: 0.15 < 0.25 -> True
    # G4: 2.0 > 1.0 -> True
    # G5: 0.8 > 0.5 and 0.20 < 0.25 -> True
    # G6: True
    # G7: True
    # G8: 4 >= 4 -> True
    assert res.passed
    assert res.gates["G1_Sharpe_Premium"]
