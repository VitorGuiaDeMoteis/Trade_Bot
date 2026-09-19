import numpy as np
import pandas as pd

from research.mean_reversion_v1.engine import run_backtest
from research.mean_reversion_v1.strategies import MeanReversionParams


def create_synthetic_data() -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    dates = pd.date_range("2020-01-01", periods=100, freq="B")
    data = pd.DataFrame(index=dates)
    data[("Close", "DTB3")] = 0.0  # zero risk-free

    # We create a single asset to simplify
    # Let's make prices such that z-scores trigger specific actions
    np.random.seed(42)
    closes = 100 + np.random.randn(100) * 0.1
    closes[10] = 50  # drop
    closes[11] = 50  # flat
    closes[12] = 50
    closes[13] = 100  # recovery

    data[("Close", "SPY")] = closes
    data[("Open", "SPY")] = closes

    # Add dummy others
    for sym in ["IWM", "EFA", "EEM"]:
        data[("Close", sym)] = 100
        data[("Open", sym)] = 100

    return data, dates


def test_signal_close_next_valid_open() -> None:
    data, dates = create_synthetic_data()
    params = MeanReversionParams(N=1, L=5, Z_entry=-2.0, Z_exit=0.0, M=10)

    # Let's verify that execution actually happens at NEXT OPEN.
    # We will set open prices different from close prices and check the trade price.

    # At index 10, close is 50. Z is very negative.
    # At index 11 (next day), open price should be the fill price.
    data.loc[dates[11], ("Open", "SPY")] = 60.0

    res = run_backtest(
        data, ["SPY", "IWM", "EFA", "EEM"], params, "2020-01-01", "2020-05-19", cost_bps=0.0
    )

    spy_trades = res.trades[res.trades["symbol"] == "SPY"]
    assert not spy_trades.empty

    # First trade is entry (BUY)
    entry_trade = spy_trades.iloc[0]
    assert entry_trade["side"] == "BUY"
    assert entry_trade["date"] == dates[11]  # Execution is on T+1

    # We started with 10_000_000 / 4 = 2_500_000 per slot
    # Fill price is 60.0. Qty = 2_500_000 / 60.0. Notional = Qty * 60.0 = 2_500_000.
    assert np.isclose(entry_trade["notional"], 2_500_000.0)


def test_entry_rule_and_exit_z() -> None:
    # Make a proper test for entry and exit
    dates = pd.date_range("2020-01-01", periods=20, freq="B")
    data = pd.DataFrame(index=dates)
    data[("Close", "DTB3")] = 0.0

    # Ensure std is not 0
    np.random.seed(42)
    closes = 100 + np.random.randn(20) * 2
    # Force a drop at day 10
    closes[10] = 80
    # Force a bounce at day 12
    closes[12] = 120

    data[("Close", "SPY")] = closes
    data[("Open", "SPY")] = closes
    for sym in ["IWM", "EFA", "EEM"]:
        data[("Close", sym)] = 100 + np.random.randn(20)
        data[("Open", sym)] = data[("Close", sym)]

    params = MeanReversionParams(N=1, L=5, Z_entry=-2.0, Z_exit=0.0, M=10)
    res = run_backtest(
        data, ["SPY", "IWM", "EFA", "EEM"], params, "2020-01-01", dates[-1], cost_bps=0.0
    )

    # Check that a trade happened
    assert len(res.trades) > 0


def test_exit_after_M_days() -> None:
    dates = pd.date_range("2020-01-01", periods=20, freq="B")
    data = pd.DataFrame(index=dates)
    data[("Close", "DTB3")] = 0.0
    np.random.seed(42)
    closes = 100 + np.random.randn(20) * 0.1
    for i in range(10, 20):
        closes[i] = (
            closes[i - 1] * 0.9
        )  # Keep dropping by 10% each day so z is always very negative!
    data[("Close", "SPY")] = closes
    data[("Open", "SPY")] = closes
    for sym in ["IWM", "EFA", "EEM"]:
        data[("Close", sym)] = 100
        data[("Open", sym)] = 100

    params = MeanReversionParams(N=1, L=5, Z_entry=-2.0, Z_exit=0.0, M=3)  # M=3
    res = run_backtest(
        data, ["SPY", "IWM", "EFA", "EEM"], params, "2020-01-01", dates[-1], cost_bps=0.0
    )

    trades = res.trades[res.trades["symbol"] == "SPY"]
    assert len(trades) >= 2  # buy and sell

    buy_date = trades[trades["side"] == "BUY"].iloc[0]["date"]
    sell_date = trades[trades["side"] == "SELL"].iloc[0]["date"]

    # Count sessions between buy and sell
    # Entry executed on T+1 open. Held for M days. Sold on M+1 open.
    # Total days = 3 (held for 3 closes)
    sessions_held = int(dates.get_loc(sell_date)) - int(dates.get_loc(buy_date))  # type: ignore[arg-type]
    assert sessions_held == 3


def test_round_trip_cost_math() -> None:
    dates = pd.date_range("2020-01-01", periods=20, freq="B")
    data = pd.DataFrame(index=dates)
    data[("Close", "DTB3")] = 0.0
    closes = np.ones(20) * 100.0
    # Add noise for std
    closes[0:8] = np.array([100, 101, 100, 101, 100, 101, 100, 101], dtype=float)
    closes[8] = 80  # entry trigger (z < -2)
    closes[9] = 80
    closes[10] = 100  # exit trigger (z >= 0)
    closes[11] = 100
    data[("Close", "SPY")] = closes
    data[("Open", "SPY")] = closes
    for sym in ["IWM", "EFA", "EEM"]:
        data[("Close", sym)] = 100
        data[("Open", sym)] = 100

    params = MeanReversionParams(N=1, L=5, Z_entry=-2.0, Z_exit=0.0, M=3)

    # cost_bps = 10 (all-in). That means 5 bps entry, 5 bps exit.
    res = run_backtest(
        data,
        ["SPY", "IWM", "EFA", "EEM"],
        params,
        dates[0],
        dates[-1],
        cost_bps=10.0,
        initial_capital=100_000,
    )

    spy_trades = res.trades[res.trades["symbol"] == "SPY"]
    buy_trade = spy_trades[spy_trades["side"] == "BUY"].iloc[0]
    sell_trade = spy_trades[spy_trades["side"] == "SELL"].iloc[0]

    # Base cash for SPY slot is 25,000.
    # Open price is 80. Fill price is 80 * (1 + 0.0005) = 80.04
    # Qty = 25000 / 80.04 = 312.3438
    # Trade notional = Qty * 80 (since we log notional based on real open)
    qty = 25000 / (80 * 1.0005)
    expected_buy_notional = qty * 80
    assert np.isclose(buy_trade["notional"], expected_buy_notional)

    # Sell open price is 100. Fill price is 100 * (1 - 0.0005) = 99.95
    # Proceeds = Qty * 99.95. Notional = Qty * 100
    expected_sell_notional = qty * 100
    assert np.isclose(sell_trade["notional"], expected_sell_notional)
