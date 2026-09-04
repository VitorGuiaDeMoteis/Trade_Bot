"""Deterministic historical orchestration. PaperExecutor alone mutates financial state."""

from dataclasses import asdict, replace
from decimal import Context, Decimal, localcontext
from itertools import groupby
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from packages.domain.backtest import Dataset, digest, encode, manifest
from packages.domain.paper import ZERO, PaperBook, PaperConfig, PaperResult, money
from packages.domain.strategy import Signal
from services.paper_executor.engine import PaperExecutor
from services.risk_engine.engine import RiskEngine
from services.risk_engine.paper_sizing import entry_quantity
from services.strategy_engine.engine import BaseStrategy


def run(dataset: Dataset, config: PaperConfig | None = None) -> dict[str, Any]:
    # Keep Decimal results independent of the caller's ambient context.
    with localcontext(Context(prec=28)):
        chosen = config or PaperConfig()
        normalized = PaperConfig(**{k: money(v) for k, v in asdict(chosen).items()})
        return _run(dataset, normalized)


def _run(dataset: Dataset, config: PaperConfig) -> dict[str, Any]:
    inputs = manifest(dataset, config)
    run_id = uuid5(NAMESPACE_URL, inputs["manifest_hash"])
    book = PaperBook(config.initial_cash, config.initial_cash)
    executor, strategy, risk_engine = PaperExecutor(config), BaseStrategy(), RiskEngine()
    if (
        strategy.VERSION != inputs["strategy_version"]
        or risk_engine.VERSION != inputs["risk_version"]
    ):
        raise ValueError("backtest_engine_version_mismatch")
    pending: dict[str, Signal] = {}
    entries: dict[str, dict[str, Any]] = {}
    outcomes: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    frames: list[dict[str, Any]] = []
    fields = (
        "cash",
        "market_value",
        "equity",
        "realized_pnl",
        "unrealized_pnl",
        "total_pnl",
        "fees",
    )
    for step, (opened, source) in enumerate(groupby(dataset.candles, key=lambda c: c.open_time), 1):
        group = list(source)
        # All current OPENs, then fills in symbol order. No current CLOSE is exposed.
        book.marks.update({c.symbol: c.open for c in group})
        for candle in group:
            signal = pending.get(candle.symbol)
            if signal is None:
                continue
            if signal.generated_at > opened:
                raise ValueError("backtest_look_ahead")
            risk = risk_engine.evaluate(signal, opened)
            risk = replace(
                risk, decision_id=uuid5(run_id, f"risk/{signal.signal_id}/{opened.isoformat()}")
            )
            if risk.decision == "REJECTED":
                result = PaperResult("NO_ACTION", "risk_rejected")
            elif signal.signal_type == "HOLD":
                result = PaperResult("NO_ACTION", "hold")
            else:
                side = signal.signal_type
                quantity = (
                    entry_quantity(
                        book.equity, executor.fill_price(candle.open, side), config.fee_bps
                    )
                    if side == "BUY"
                    else 0
                )
                result = executor.execute(book, candle.symbol, side, candle.open, quantity, risk)
            order_id = (
                uuid5(run_id, f"order/{risk.decision_id}") if result.status != "NO_ACTION" else None
            )
            fill_id = uuid5(order_id, "fill") if order_id and result.status == "FILLED" else None
            outcome = {
                "symbol": candle.symbol,
                "signal": asdict(signal),
                "risk": asdict(risk),
                "execution_candle_id": candle.candle_id,
                "executed_at": opened,
                "order_id": order_id,
                "fill_id": fill_id,
                "reference_price": candle.open,
                **asdict(result),
            }
            outcomes.append(outcome)
            if result.status == "FILLED":
                if signal.signal_type == "BUY":
                    entries[candle.symbol] = outcome
                else:
                    entry = entries.pop(candle.symbol)
                    fees = money(entry["fee"] + result.fee)
                    trades.append(
                        {
                            "symbol": candle.symbol,
                            "quantity": result.quantity,
                            "entry_fill_id": entry["fill_id"],
                            "exit_fill_id": fill_id,
                            "opened_at": entry["executed_at"],
                            "closed_at": opened,
                            "gross_pnl": result.realized_pnl,
                            "fees": fees,
                            "net_pnl": money(result.realized_pnl - fees),
                        }
                    )
        # Close marks and newly generated signals become available only now.
        for candle in group:
            book.marks[candle.symbol] = candle.close
            signal = strategy.process_candle(candle, candle.close_time)
            signal = replace(
                signal, signal_id=uuid5(run_id, f"signal/{candle.candle_id}/{strategy.VERSION}")
            )
            pending[candle.symbol] = signal
            signals.append(asdict(signal))
        book.reconcile()
        frames.append(
            {
                "step": step,
                "timestamp": group[0].close_time,
                **{f: getattr(book, f) for f in fields},
            }
        )

    # No forced last-bar liquidation. Entry fees for open positions remain allocated.
    open_fees = money(sum((e["fee"] for e in entries.values()), ZERO))
    closed_net = money(sum((t["net_pnl"] for t in trades), ZERO))
    if book.total_pnl != money(closed_net + book.unrealized_pnl - open_fees):
        raise ValueError("backtest_trade_reconciliation_failed")
    wins = [t["net_pnl"] for t in trades if t["net_pnl"] > ZERO]
    losses = [t["net_pnl"] for t in trades if t["net_pnl"] < ZERO]
    peak = config.initial_cash
    max_drawdown, max_drawdown_pct = ZERO, ZERO
    for frame in frames:
        peak = max(peak, frame["equity"])
        drawdown = money(peak - frame["equity"])
        frame["drawdown"] = drawdown
        frame["drawdown_pct"] = money(drawdown / peak * 100)
        max_drawdown = max(max_drawdown, drawdown)
        max_drawdown_pct = max(max_drawdown_pct, frame["drawdown_pct"])
    metrics = {
        "initial_cash": config.initial_cash,
        "final_equity": book.equity,
        "return_pct": money(book.total_pnl / config.initial_cash * 100),
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown_pct,
        "closed_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "breakeven_trades": len(trades) - len(wins) - len(losses),
        "win_rate_pct": money(Decimal(len(wins)) / len(trades) * 100) if trades else None,
        "average_profit": money(sum(wins, ZERO) / len(wins)) if wins else None,
        "average_loss": money(sum(losses, ZERO) / len(losses)) if losses else None,
        "profit_factor": money(sum(wins, ZERO) / -sum(losses, ZERO)) if losses else None,
        "profit_factor_status": "defined"
        if losses
        else ("no_losses" if trades else "no_closed_trades"),
        "orders": sum(o["order_id"] is not None for o in outcomes),
        "fills": sum(o["fill_id"] is not None for o in outcomes),
        "open_positions": len(entries),
        "fees": book.fees,
        "slippage": money(sum((o["slippage"] for o in outcomes if o["fill_id"]), ZERO)),
        "realized_pnl_gross": book.realized_pnl,
        "closed_pnl_net": closed_net,
        "unrealized_pnl_gross": book.unrealized_pnl,
        "open_entry_fees": open_fees,
        "total_pnl_net": book.total_pnl,
    }
    report = {
        "schema_version": "1.0",
        "mode": "BACKTEST",
        "run_id": run_id,
        "manifest_hash": inputs["manifest_hash"],
        "dataset_hash": dataset.hash,
        "engine_version": inputs["engine_version"],
        "strategy_version": strategy.VERSION,
        "risk_version": risk_engine.VERSION,
        "config": inputs["config"],
        "metrics": metrics,
        "equity_curve": frames,
        "trades": trades,
        "signals": signals,
        "outcomes": outcomes,
        "positions": [
            asdict(p) | {"mark": book.marks[p.symbol]}
            for p in sorted(book.positions.values(), key=lambda p: p.symbol)
            if p.quantity
        ],
    }
    # Canonical JSON is the public contract: Decimal strings, finite numbers, stable IDs.
    import json

    return json.loads(encode({**report, "result_hash": digest(report)}))  # type: ignore[no-any-return]
