from decimal import Decimal
from typing import Any
from sqlalchemy import Connection, text
from uuid import UUID

def get_session_analytics(conn: Connection, run_id: UUID | str) -> dict[str, Any]:
    run_id_str = str(run_id)
    
    run_row = conn.execute(
        text("SELECT created_at, initial_cash, provider FROM paper_runs WHERE run_id = :run_id"),
        {"run_id": run_id_str}
    ).mappings().first()
    
    if not run_row:
        raise ValueError("Run not found")
        
    start_time = run_row["created_at"]
    
    # Every broker-owned table below is keyed by provider, so each read is scoped to the
    # run's own provider: an unscoped MAX()/LIMIT 1/aggregate would mix a second provider's
    # account state into this run's P&L.
    provider = run_row["provider"]

    end_time = conn.execute(
        text(
            "SELECT MAX(last_reconciled_at) as end_time "
            "FROM broker_portfolio_snapshots WHERE provider = :provider"
        ),
        {"provider": provider},
    ).scalar() or start_time
    
    orders = conn.execute(
        text("SELECT order_id, symbol, side, quantity, filled_quantity, status, requested_at FROM paper_orders WHERE run_id = :run_id ORDER BY requested_at"),
        {"run_id": run_id_str}
    ).mappings().fetchall()
    
    positions = conn.execute(
        text(
            "SELECT symbol, quantity, average_price, current_price, market_value, "
            "unrealized_pnl, updated_at FROM broker_positions WHERE provider = :provider"
        ),
        {"provider": provider},
    ).mappings().fetchall()
    
    unrealized_pnl = sum([Decimal(str(p["unrealized_pnl"])) for p in positions])
    market_value = sum([Decimal(str(p["market_value"])) for p in positions])
    
    # broker_portfolio_snapshots holds ONE row per provider (provider is the PK and the
    # worker upserts on conflict), so it is current-state, not a time series: reading it
    # for the session opener would echo the current equity into `equity_initial` and make
    # it equal to `equity_final`. The run's own starting cash is the only correct opener.
    initial_cash = Decimal(str(run_row["initial_cash"]))

    snap = conn.execute(
        text("SELECT cash, equity FROM broker_portfolio_snapshots WHERE provider = :provider"),
        {"provider": provider},
    ).mappings().first()
    final_equity = Decimal(str(snap["equity"])) if snap else initial_cash

    fills = conn.execute(
        text('''
            SELECT f.broker_fill_id, f.quantity, f.price, f.fee, f.filled_at, p.symbol, p.side, r.decided_at, r.decision_id
            FROM broker_fills f
            JOIN broker_orders o ON f.order_id = o.order_id
            JOIN paper_orders p ON o.order_id = p.order_id
            JOIN risk_decisions r ON p.risk_decision_id = r.decision_id
            WHERE p.run_id = :run_id
            ORDER BY f.filled_at ASC
        '''),
        {"run_id": run_id_str}
    ).mappings().fetchall()

    fifo_buys: dict[str, list[dict[str, Any]]] = {}
    completed_trades = []
    unmatched_sells: dict[str, Decimal] = {}
    session_realized_pnl = Decimal("0")
    realized_after_fill: list[tuple[Any, Decimal]] = []
    total_wins = 0
    total_losses = 0
    gross_wins = Decimal("0")
    gross_losses = Decimal("0")

    for f in fills:
        sym = f["symbol"]
        if sym not in fifo_buys:
            fifo_buys[sym] = []
            
        qty = Decimal(str(f["quantity"]))
        price = Decimal(str(f["price"]))
        fee = Decimal(str(f["fee"])) if f["fee"] is not None else Decimal("0")
        
        if f["side"] == "BUY":
            fifo_buys[sym].append({"qty": qty, "price": price, "timestamp": f["filled_at"], "fee": fee})
        elif f["side"] == "SELL":
            sell_qty = qty
            while sell_qty > 0 and fifo_buys[sym]:
                buy = fifo_buys[sym][0]
                matched_qty = min(sell_qty, buy["qty"])
                
                gross_pnl = (price - buy["price"]) * matched_qty
                chunk_buy_fee = buy["fee"] * (matched_qty / buy["qty"]) if buy["qty"] > 0 else Decimal("0")
                chunk_sell_fee = fee * (matched_qty / qty) if qty > 0 else Decimal("0")
                net_pnl = gross_pnl - chunk_buy_fee - chunk_sell_fee
                
                session_realized_pnl += net_pnl
                
                if net_pnl > 0:
                    total_wins += 1
                    gross_wins += net_pnl
                elif net_pnl < 0:
                    total_losses += 1
                    gross_losses += abs(net_pnl)
                
                completed_trades.append({
                    "symbol": sym,
                    "entry_timestamp": buy["timestamp"].isoformat(),
                    "entry_qty": str(matched_qty),
                    "entry_avg_price": str(buy["price"]),
                    "exit_timestamp": f["filled_at"].isoformat(),
                    "exit_qty": str(matched_qty),
                    "exit_avg_price": str(price),
                    "gross_pnl": str(gross_pnl),
                    "fees": str(chunk_buy_fee + chunk_sell_fee),
                    "slippage": None,
                    "net_pnl": str(net_pnl)
                })
                
                sell_qty -= matched_qty
                buy["qty"] -= matched_qty
                buy["fee"] -= chunk_buy_fee
                if buy["qty"] <= 0:
                    fifo_buys[sym].pop(0)

            # A SELL with no (or not enough) BUY lot in THIS run has no known
            # cost basis, so its realized P&L cannot be computed without
            # inventing a price. Record the unmatched quantity per symbol
            # instead of dropping it, otherwise the shortfall is invisible
            # and pnl_realized silently under-reports.
            if sell_qty > 0:
                unmatched_sells[sym] = unmatched_sells.get(sym, Decimal("0")) + sell_qty

        realized_after_fill.append((f["filled_at"], session_realized_pnl))

    realized_pnl = session_realized_pnl

    # `max_drawdown`, `avg_exposure` and `max_exposure` used to be fabricated: the
    # drawdown was the literal "0.00" and BOTH exposures were the CURRENT market
    # value, so a session that peaked far above where it ended reported no
    # drawdown at all and an "average" exposure equal to its final instant.
    #
    # broker_portfolio_snapshots holds ONE row per provider (see the equity_initial
    # note above), so there is no stored equity time series to read. The curve is
    # rebuilt from this run's fills anchored on the broker's current book and walked
    # BACKWARD (a BUY added its notional, a SELL removed its own). Anchoring on the
    # book is what lets lots inherited from a previous run -- which have no fill in
    # this run and no opening timestamp -- count in every interval instead of
    # vanishing. Marks are fill prices, so the exposure and drawdown are measured at
    # fill granularity and do not see excursions between fills.
    avg_exposure = market_value
    max_exposure = market_value
    max_drawdown = Decimal("0")

    if fills and end_time:
        curve_end = max(end_time, fills[-1]["filled_at"])
        if curve_end > start_time:
            exposure = market_value
            before: list[tuple[Any, Decimal]] = []
            for f in reversed(fills):
                notional = Decimal(str(f["quantity"])) * Decimal(str(f["price"]))
                exposure = exposure - notional if f["side"] == "BUY" else exposure + notional
                before.append((f["filled_at"], exposure))
            before.reverse()
            # Each backward step yields the exposure in force BEFORE that fill, i.e.
            # over the interval ENDING at its timestamp. So a value belongs to the
            # NEXT fill's timestamp, not its own -- pairing it with its own timestamp
            # shifts every segment one interval late and understates the average.
            exposure_series: list[tuple[Any, Any]] = [(start_time, before[0][1])]
            exposure_series.extend(
                (before[index][0], before[index + 1][1]) for index in range(len(before) - 1)
            )
            # After the LAST fill the anchor itself is what is in force until the end.
            exposure_series.append((before[-1][0], market_value))

            span = Decimal(str((curve_end - start_time).total_seconds()))
            weighted = Decimal("0")
            peak_exposure = Decimal("0")
            for index, (ts, value) in enumerate(exposure_series):
                nxt = (
                    exposure_series[index + 1][0]
                    if index + 1 < len(exposure_series)
                    else curve_end
                )
                weighted += value * Decimal(str((nxt - ts).total_seconds()))
                if value > peak_exposure:
                    peak_exposure = value
            avg_exposure = weighted / span
            max_exposure = peak_exposure

            # docs/M4_CORE.md:68 defines the drawdown as the largest
            # `previous peak - equity`, with the initial capital as the first peak.
            # Equity moves here only when a fill realizes P&L, so this is the
            # realized-equity curve at fill granularity.
            equity_series = [(start_time, initial_cash)]
            equity_series.extend(
                (ts, initial_cash + realized) for ts, realized in realized_after_fill
            )
            equity_series.append((curve_end, initial_cash + realized_pnl))
            peak = initial_cash
            for _ts, equity in equity_series:
                if equity > peak:
                    peak = equity
                if peak - equity > max_drawdown:
                    max_drawdown = peak - equity
    total_pnl = realized_pnl + unrealized_pnl
    # docs/M4_CORE.md:67 defines the session return as
    # (equity final - initial cash) / initial cash * 100, i.e. the change in the
    # ACCOUNT. `total_pnl` is a different thing: it sums this run's matched FIFO
    # realized P&L with the unrealized P&L of the CURRENT position book, so it
    # silently drops any cash movement the fills do not explain (fees settling,
    # an unmatched SELL -- reported separately as anomalies.unmatched_sells, an
    # inherited lot opening or closing, a deposit) and can even net a real loss
    # against an unrelated gain. The equity difference is the account's own
    # answer and needs no such reconciliation.
    equity_delta = final_equity - initial_cash
    return_pct = (equity_delta / initial_cash) * 100 if initial_cash else Decimal("0")
    
    total_trades = total_wins + total_losses
    win_rate = (Decimal(total_wins) / Decimal(total_trades)) * 100 if total_trades > 0 else Decimal("0")
    avg_win = gross_wins / Decimal(total_wins) if total_wins > 0 else Decimal("0")
    avg_loss = gross_losses / Decimal(total_losses) if total_losses > 0 else Decimal("0")
    
    profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else (Decimal("999.99") if gross_wins > 0 else Decimal("0"))
    expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss)
    
    signals_data = conn.execute(
        text('''
            SELECT s.signal_type, r.decision, r.reason 
            FROM risk_decisions r
            JOIN signals s ON r.signal_id = s.signal_id
            WHERE r.run_id = :run_id
        '''),
        {"run_id": run_id_str}
    ).mappings().fetchall()
    
    sig_count = {"BUY": 0, "SELL": 0, "HOLD": 0}
    dec_count = {"APPROVED": 0, "REJECTED": 0}
    rejections: dict[str, int] = {}
    
    for s in signals_data:
        sig_type = s["signal_type"]
        if sig_type in sig_count:
            sig_count[sig_type] += 1
        dec = s["decision"]
        if dec in dec_count:
            dec_count[dec] += 1
        if dec == "REJECTED":
            reason = s["reason"]
            rejections[reason] = rejections.get(reason, 0) + 1
            
    errors = []
    for o in orders:
        if o["status"] == "CANCELED" or o["status"] == "REJECTED":
            errors.append({"order_id": str(o["order_id"]), "symbol": o["symbol"], "status": o["status"]})
            
    dust = []
    for p in positions:
        if Decimal(str(p["market_value"])) > 0 and Decimal(str(p["market_value"])) < 1.00:
            dust.append({"symbol": p["symbol"], "quantity": str(p["quantity"])})
            
    return {
        "session_id": run_id_str,
        "started_at": start_time.isoformat(),
        "ended_at": end_time.isoformat() if end_time else None,
        "equity_initial": str(initial_cash),
        "equity_final": str(final_equity),
        "pnl_total": str(total_pnl),
        "pnl_realized": str(realized_pnl),
        "pnl_unrealized": str(unrealized_pnl),
        "return_pct": str(return_pct),
        "max_drawdown": str(round(max_drawdown, 2)),
        "avg_exposure": str(round(avg_exposure, 2)),
        "max_exposure": str(round(max_exposure, 2)),
        "signals": sig_count,
        "decisions": dec_count,
        "rejection_reasons": rejections,
        "orders_sent": len(orders),
        "orders_filled": len([o for o in orders if o["status"] == "FILLED"]),
        "orders_canceled": len([o for o in orders if o["status"] == "CANCELED"]),
        "trades_completed": len(completed_trades),
        "win_rate": str(round(win_rate, 2)),
        "avg_win": str(round(avg_win, 2)),
        "avg_loss": str(round(avg_loss, 2)),
        "expectancy": str(round(expectancy, 4)),
        "profit_factor": str(round(profit_factor, 2)),
        "symbols_data": {p["symbol"]: {"market_value": str(p["market_value"])} for p in positions},
        "closed_trades": completed_trades,
        "anomalies": {
            "api_reconciliation_errors": errors,
            "dust_positions": dust,
            "unmatched_sells": [
                {"symbol": sym, "quantity": str(qty)}
                for sym, qty in sorted(unmatched_sells.items())
            ],
        }
    }
