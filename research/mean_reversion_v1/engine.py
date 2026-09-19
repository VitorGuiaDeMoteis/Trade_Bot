from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from research.mean_reversion_v1.accrual import compute_daily_risk_free_return
from research.mean_reversion_v1.strategies import MeanReversionParams, compute_z_scores


@dataclass
class BacktestResult:
    returns: pd.Series
    portfolio_value: pd.Series
    turnover: pd.Series
    turnover_fraction: pd.Series
    positions: pd.DataFrame
    trades: pd.DataFrame
    daily_stats: pd.DataFrame


def run_backtest(
    data: pd.DataFrame,
    universe: list[str],
    params: MeanReversionParams,
    start_date: str | pd.Timestamp,
    end_date: str | pd.Timestamp,
    initial_capital: float = 10_000_000.0,
    cost_bps: float = 10.0,
    zero_cash: bool = False,
    slots: int = 4,
) -> BacktestResult:
    index = pd.DatetimeIndex(data.index).tz_localize(None).sort_values()
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    sessions = index[(index >= start) & (index <= end)]

    # Pre-calculate signals
    z_scores = {}
    for sym in universe:
        closes = data[("Close", sym)]
        z_scores[sym] = compute_z_scores(closes, params.N, params.L)

    risk_free = compute_daily_risk_free_return(data, index, zero_cash=zero_cash)

    slot_capital = initial_capital / slots

    # Track state per symbol
    # True if holding, False otherwise
    in_position = {sym: False for sym in universe}
    shares = {sym: 0.0 for sym in universe}
    cash = {sym: slot_capital for sym in universe}
    days_held = {sym: 0 for sym in universe}

    # We will generate trades to execute at NEXT open.
    # We need to look at signal at previous close, execute at current open.
    pending_entry = {sym: False for sym in universe}
    pending_exit = {sym: False for sym in universe}
    signal_entry_date: dict[str, pd.Timestamp | None] = {sym: None for sym in universe}
    signal_exit_date: dict[str, pd.Timestamp | None] = {sym: None for sym in universe}
    active_trade: dict[str, dict[str, object]] = {sym: {} for sym in universe}

    portfolio_values = []
    turnover = []
    turnover_fraction = []
    positions_list = []
    trades_list = []
    daily_stats_list = []

    entry_fee_rate = cost_bps / 2.0 / 10000.0
    exit_fee_rate = cost_bps / 2.0 / 10000.0

    prev_date = None

    for _i, current_date in enumerate(sessions):
        daily_turnover = 0.0
        active_slots = 0

        # Apply risk-free accrual to cash BEFORE open
        if prev_date is not None:
            rf = risk_free.loc[current_date]
            for sym in universe:
                cash[sym] *= 1.0 + float(rf)

        # Execute pending orders at OPEN
        for sym in universe:
            if pending_entry[sym]:
                open_price = float(data.at[current_date, ("Open", sym)])  # type: ignore[arg-type]
                fill_price = open_price * (1.0 + entry_fee_rate)
                qty = cash[sym] / fill_price
                shares[sym] += qty
                cash[sym] = 0.0
                in_position[sym] = True
                days_held[sym] = 0

                trade_notional = qty * open_price
                daily_turnover += trade_notional

                active_trade[sym] = {
                    "symbol": sym,
                    "signal_entry_date": signal_entry_date[sym],
                    "entry_execution_date": current_date,
                    "entry_price": fill_price,
                    "notional_in": trade_notional,
                    "shares": qty,
                }
                pending_entry[sym] = False

            elif pending_exit[sym]:
                open_price = float(data.at[current_date, ("Open", sym)])  # type: ignore[arg-type]
                fill_price = open_price * (1.0 - exit_fee_rate)

                trade_notional = shares[sym] * open_price
                daily_turnover += trade_notional

                proceeds = shares[sym] * fill_price
                cash[sym] += proceeds

                t = active_trade[sym]
                t["signal_exit_date"] = signal_exit_date[sym]
                t["exit_execution_date"] = current_date
                t["exit_price"] = fill_price
                t["holding_sessions"] = days_held[sym]
                t["notional_out"] = proceeds
                notional_in = float(t["notional_in"])  # type: ignore
                t["pnl"] = proceeds - notional_in
                t["return"] = proceeds / notional_in - 1.0 if notional_in > 0 else 0.0

                trades_list.append(t.copy())
                active_trade[sym] = {}

                shares[sym] = 0.0
                in_position[sym] = False
                days_held[sym] = 0
                pending_exit[sym] = False

        # Evaluate portfolio value at CLOSE
        nav_total = 0.0
        pos_dict = {}
        for sym in universe:
            sym_nav = cash[sym]
            if in_position[sym]:
                close_price = float(data.at[current_date, ("Close", sym)])  # type: ignore[arg-type]
                sym_nav += shares[sym] * close_price
                active_slots += 1
            nav_total += sym_nav
            pos_dict[sym] = sym_nav
            pos_dict[f"{sym}_cash"] = cash[sym]

        pos_dict["CASH"] = sum(cash.values())
        portfolio_values.append(nav_total)
        turnover.append(daily_turnover)
        turnover_fraction.append(daily_turnover / nav_total if nav_total > 0 else 0)
        positions_list.append(pos_dict)
        daily_stats_list.append({"active_slots": active_slots})

        # Generate signals for NEXT open based on current close
        for sym in universe:
            if in_position[sym]:
                days_held[sym] += 1
                z = z_scores[sym].loc[current_date]
                if pd.notna(z) and z >= params.Z_exit:
                    pending_exit[sym] = True
                    signal_exit_date[sym] = current_date
                elif days_held[sym] >= params.M:
                    pending_exit[sym] = True
                    signal_exit_date[sym] = current_date
            else:
                z = z_scores[sym].loc[current_date]
                if pd.notna(z) and z < params.Z_entry:
                    pending_entry[sym] = True
                    signal_entry_date[sym] = current_date

        prev_date = current_date

    pv = pd.Series(portfolio_values, index=sessions, name="portfolio_value")
    rets = pv.pct_change()
    rets.iloc[0] = pv.iloc[0] / initial_capital - 1.0

    return BacktestResult(
        returns=rets,
        portfolio_value=pv,
        turnover=pd.Series(turnover, index=sessions, name="turnover"),
        turnover_fraction=pd.Series(turnover_fraction, index=sessions, name="turnover_fraction"),
        positions=pd.DataFrame(positions_list, index=sessions),
        trades=pd.DataFrame(
            trades_list,
            columns=[
                "symbol",
                "signal_entry_date",
                "entry_execution_date",
                "entry_price",
                "signal_exit_date",
                "exit_execution_date",
                "exit_price",
                "holding_sessions",
                "notional_in",
                "shares",
                "notional_out",
                "pnl",
                "return",
            ],
        )
        if trades_list
        else pd.DataFrame(
            columns=[
                "symbol",
                "signal_entry_date",
                "entry_execution_date",
                "entry_price",
                "signal_exit_date",
                "exit_execution_date",
                "exit_price",
                "holding_sessions",
                "notional_in",
                "shares",
                "notional_out",
                "pnl",
                "return",
            ]
        ),
        daily_stats=pd.DataFrame(daily_stats_list, index=sessions),
    )
