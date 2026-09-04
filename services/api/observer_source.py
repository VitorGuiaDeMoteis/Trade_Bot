"""Trusted read-only projection of persisted facts. Never pass Settings to Observer."""

from datetime import datetime
from typing import Any

from sqlalchemy import Engine, select, text

from packages.contracts.observer import MAX_CANDLES_PER_SYMBOL, MAX_SYMBOLS, AIObserverSnapshot, utc
from services.api.models import candles, paper_runs, risk_decisions, signals, system_controls
from services.api.paper_integrity import reconcile, validate_control
from services.observer.snapshot import project


def collect(
    engine: Engine,
    *,
    as_of: datetime,
    provider: str,
    session_state: str,
    symbols: tuple[str, ...],
    accepted_report: dict[str, Any] | None = None,
) -> AIObserverSnapshot:
    utc(as_of)
    if provider not in {"alpaca", "simulator"} or not 0 < len(set(symbols)) <= MAX_SYMBOLS:
        raise ValueError("observer_invalid_selection")
    raw: dict[str, Any] = {
        "as_of_utc": as_of.isoformat(),
        "provider": provider,
        "session_state": session_state,
        "symbols": sorted(set(symbols)),
        "timeframe": "1h",
        "candles": [],
        "signals": [],
        "risk_decisions": [],
        "paper": None,
        "accepted_backtest": None,
    }
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as c, c.begin():
        c.execute(text("SET TRANSACTION READ ONLY"))
        for symbol in raw["symbols"]:
            rows = (
                c.execute(
                    select(candles)
                    .where(
                        candles.c.provider == provider,
                        candles.c.symbol == symbol,
                        candles.c.timeframe == "1h",
                        candles.c.is_closed,
                        candles.c.close_time <= as_of,
                    )
                    .order_by(candles.c.open_time.desc())
                    .limit(MAX_CANDLES_PER_SYMBOL)
                )
                .mappings()
                .all()
            )
            for row in rows:
                raw["candles"].append(
                    {
                        "symbol": row["symbol"],
                        "open_time": row["open_time"].isoformat(),
                        "close_time": row["close_time"].isoformat(),
                        "is_closed": True,
                        "volume": row["volume"],
                        **{
                            field: format(row[field], "f")
                            for field in ("open", "high", "low", "close")
                        },
                    }
                )
            known_series = (
                candles.c.provider == provider,
                candles.c.symbol == symbol,
                candles.c.timeframe == "1h",
                candles.c.close_time <= as_of,
                signals.c.generated_at <= as_of,
            )
            signal = (
                c.execute(
                    select(signals)
                    .join(candles, signals.c.candle_id == candles.c.candle_id)
                    .where(*known_series)
                    .order_by(signals.c.generated_at.desc(), signals.c.signal_id)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if signal:
                raw["signals"].append(
                    {
                        "symbol": symbol,
                        "generated_at": signal["generated_at"].isoformat(),
                        "strategy_version": signal["strategy_version"],
                        "signal_type": signal["signal_type"],
                    }
                )
            risk = (
                c.execute(
                    select(risk_decisions)
                    .join(signals, risk_decisions.c.signal_id == signals.c.signal_id)
                    .join(candles, signals.c.candle_id == candles.c.candle_id)
                    .where(*known_series, risk_decisions.c.decided_at <= as_of)
                    .order_by(risk_decisions.c.decided_at.desc(), risk_decisions.c.decision_id)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if risk:
                raw["risk_decisions"].append(
                    {
                        "symbol": symbol,
                        "decided_at": risk["decided_at"].isoformat(),
                        "decision": risk["decision"],
                    }
                )
        control = (
            c.execute(select(system_controls).where(system_controls.c.control_id == 1))
            .mappings()
            .first()
        )
        validate_control(c, control)
        if control and control["active_run_id"]:
            paper = (
                c.execute(select(paper_runs).where(paper_runs.c.run_id == control["active_run_id"]))
                .mappings()
                .one()
            )
            book = reconcile(c, paper)
            if paper["as_of"] and paper["as_of"] <= as_of:
                raw["paper"] = {
                    "as_of_utc": paper["as_of"].isoformat(),
                    "paused": control["paused"],
                    "cash": format(book.cash, "f"),
                    "equity": format(book.equity, "f"),
                    "total_pnl": format(book.total_pnl, "f"),
                    "positions": [
                        {
                            "symbol": p.symbol,
                            "quantity": p.quantity,
                            "average_price": format(p.average_price, "f"),
                        }
                        for p in book.positions.values()
                        if p.quantity
                    ],
                }
    if accepted_report:
        frames = accepted_report["equity_curve"]
        if frames and datetime.fromisoformat(frames[-1]["timestamp"]) > as_of:
            raise ValueError("observer_future_backtest")
        raw["accepted_backtest"] = {
            "result_hash": accepted_report["result_hash"],
            **{
                key: accepted_report["metrics"][key]
                for key in ("return_pct", "max_drawdown_pct", "closed_trades", "profit_factor")
            },
        }
    return project(raw)
