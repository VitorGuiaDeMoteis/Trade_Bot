import json
from decimal import Decimal
from typing import Any
from sqlalchemy import Connection, text
from uuid import UUID

def get_session_analytics(conn: Connection, run_id: UUID | str) -> dict[str, Any]:
    run_id_str = str(run_id)
    
    run_row = conn.execute(
        text("SELECT created_at, initial_cash FROM paper_runs WHERE run_id = :run_id"),
        {"run_id": run_id_str}
    ).mappings().first()
    
    if not run_row:
        raise ValueError("Run not found")
        
    start_time = run_row["created_at"]
    
    end_time = conn.execute(
        text("SELECT MAX(last_reconciled_at) as end_time FROM broker_portfolio_snapshots")
    ).scalar() or start_time
    
    orders = conn.execute(
        text("SELECT order_id, symbol, side, quantity, filled_quantity, status, requested_at FROM paper_orders WHERE run_id = :run_id ORDER BY requested_at"),
        {"run_id": run_id_str}
    ).mappings().fetchall()
    
    positions = conn.execute(
        text("SELECT symbol, quantity, average_price, current_price, market_value, unrealized_pnl, updated_at FROM broker_positions")
    ).mappings().fetchall()
    
    unrealized_pnl = sum([Decimal(str(p["unrealized_pnl"])) for p in positions])
    market_value = sum([Decimal(str(p["market_value"])) for p in positions])
    
    snap_first = conn.execute(text("SELECT cash, equity FROM broker_portfolio_snapshots ORDER BY last_reconciled_at ASC LIMIT 1")).mappings().first()
    initial_cash = Decimal(str(snap_first["equity"])) if snap_first else Decimal(str(run_row["initial_cash"]))
    
    snap = conn.execute(text("SELECT cash, equity FROM broker_portfolio_snapshots LIMIT 1")).mappings().first()
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

    fifo_buys = {}
    completed_trades = []
    session_realized_pnl = Decimal("0")
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

    realized_pnl = session_realized_pnl
    total_pnl = realized_pnl + unrealized_pnl
    return_pct = (total_pnl / initial_cash) * 100 if initial_cash else Decimal("0")
    
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
    rejections = {}
    
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
        "max_drawdown": "0.00",
        "avg_exposure": str(market_value),
        "max_exposure": str(market_value),
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
            "dust_positions": dust
        }
    }
