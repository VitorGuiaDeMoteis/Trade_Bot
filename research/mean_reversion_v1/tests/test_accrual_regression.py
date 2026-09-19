import importlib.util
import math
import sys

import pandas as pd

from research.mean_reversion_v1.accrual import (
    calculate_cash_accrual,
    compound_period_return,
    compute_daily_risk_free_return,
)


def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_accrual_regression() -> None:
    # Load the momentum accrual module dynamically to avoid runtime dependency in production
    momentum_accrual = load_module_from_path(
        "momentum_accrual",
        "/home/vitor/DevBox/projects/Trade_Bot_Momentum/research/momentum_v1/accrual.py",
    )

    # Create a synthetic historical fixture
    dates = pd.date_range(start="2010-01-01", periods=10, freq="B")
    data = pd.DataFrame(index=dates)
    data[("Close", "DTB3")] = [1.0, 1.1, 1.2, -0.5, 0.0, 2.0, 2.5, float("nan"), 3.0, 3.1]
    # We ffill inside extract_dtb3 but it's good to have standard input
    data.ffill(inplace=True)

    target_index = dates

    # Run both methods
    result_mean_rev = compute_daily_risk_free_return(data, target_index)
    result_momentum = momentum_accrual.compute_daily_risk_free_return(data, target_index)

    pd.testing.assert_series_equal(result_mean_rev, result_momentum)

    # Test specific properties
    # B0_return_t == rf_return_t
    # tolerance <= 1e-12
    # Just to be sure they output the exact same values
    diff = (result_mean_rev - result_momentum).abs().max()
    assert diff <= 1e-12

    # Check calculate_cash_accrual equivalence
    for y in [0.0, -1.0, 5.0, 10.0]:
        for d in [1, 3, 5, 30]:
            assert math.isclose(
                calculate_cash_accrual(y, d),
                momentum_accrual.calculate_cash_accrual(y, d),
                abs_tol=1e-12,
            )

    # Check compound_period_return
    ret = pd.Series([0.01, -0.005, 0.02, 0.0], index=pd.date_range("2010-01-02", periods=4))
    assert math.isclose(
        compound_period_return(ret, pd.Timestamp("2010-01-01"), pd.Timestamp("2010-01-10")),
        momentum_accrual.compound_period_return(
            ret, pd.Timestamp("2010-01-01"), pd.Timestamp("2010-01-10")
        ),
        abs_tol=1e-12,
    )
