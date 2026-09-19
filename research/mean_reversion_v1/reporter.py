import pandas as pd

from research.mean_reversion_v1.engine import MeanReversionParams, run_backtest
from research.mean_reversion_v1.metrics import calculate_metrics


def evaluate_combined_stress(
    data: pd.DataFrame,
    orig_universe: list[str],
    sub_universe: list[str],
    params: MeanReversionParams,
    sub_start: pd.Timestamp,
    end_date: pd.Timestamp,
    orig_cost: float,
    sub_cost: float,
    rf: pd.Series,
    spy: pd.Series,
) -> dict:
    # Must use EXACT same window
    common_data = data.loc[sub_start:end_date]
    common_rf = rf.loc[sub_start:end_date]
    common_spy = spy.loc[sub_start:end_date]

    orig_res = run_backtest(
        common_data,
        orig_universe,
        params,
        str(sub_start.date()),
        str(end_date.date()),
        cost_bps=orig_cost,
    )
    sub_res = run_backtest(
        common_data,
        sub_universe,
        params,
        str(sub_start.date()),
        str(end_date.date()),
        cost_bps=sub_cost,
    )

    orig_m = calculate_metrics(orig_res, common_rf, common_spy)
    sub_m = calculate_metrics(sub_res, common_rf, common_spy)

    return {
        "START_DATE": str(sub_start.date()),
        "END_DATE": str(end_date.date()),
        "ORIGINAL_UNIVERSE": orig_universe,
        "SUBSTITUTED_UNIVERSE": sub_universe,
        "ORIGINAL_COST_BPS": orig_cost,
        "SUBSTITUTED_COST_BPS": sub_cost,
        "ORIGINAL": {"Sharpe": orig_m["Sharpe"], "MaxDD": orig_m["MaxDD"], "CAGR": orig_m["CAGR"]},
        "STRESSED": {"Sharpe": sub_m["Sharpe"], "MaxDD": sub_m["MaxDD"], "CAGR": sub_m["CAGR"]},
        "DELTA_SHARPE": float(sub_m["Sharpe"]) - float(orig_m["Sharpe"])
        if isinstance(sub_m["Sharpe"], (int, float)) and isinstance(orig_m["Sharpe"], (int, float))
        else 0.0,
    }
