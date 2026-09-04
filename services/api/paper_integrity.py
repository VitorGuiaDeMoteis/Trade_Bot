"""Independent replay accountant: verify provenance and every committed financial state.

This does not call PaperExecutor or modify the database. Stored fills are accepted only
when they match the frozen inputs and the cash/long-only/allocation rules.
"""

import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from itertools import groupby
from uuid import UUID, uuid5

from sqlalchemy import Connection, RowMapping, select

from packages.contracts.decisions import DecisionItem
from packages.domain.market_bar import MarketBar
from packages.domain.paper import ZERO, PaperBook, PaperConfig, PaperPosition, money
from services.api.models import (
    paper_fills,
    paper_marks,
    paper_orders,
    paper_outcomes,
    paper_runs,
    portfolio_snapshots,
    positions,
)
from services.risk_engine.paper_sizing import entry_quantity

FIELDS = ("cash", "market_value", "equity", "realized_pnl", "unrealized_pnl", "total_pnl", "fees")


def validate_control(c: Connection, control: RowMapping | None) -> None:
    if (not control or control["active_run_id"] is None) and c.scalar(
        select(paper_runs.c.run_id).limit(1)
    ):
        raise ValueError("paper_missing_active_control")


def frozen_groups(run: RowMapping) -> list[list[DecisionItem]]:
    digest = hashlib.sha256(json.dumps(run["dataset"], sort_keys=True).encode()).hexdigest()
    if digest != run["dataset_hash"]:
        raise ValueError("paper_dataset_hash_mismatch")
    try:
        items = [DecisionItem.model_validate(raw) for raw in run["dataset"]]
        keys = [(i.candle.open_time, i.candle.symbol) for i in items]
        if keys != sorted(keys) or len(set(keys)) != len(keys):
            raise ValueError("paper_dataset_order")
        for item in items:
            bar, signal, risk = item.candle, item.signal, item.risk
            MarketBar(**{name: getattr(bar, name) for name in MarketBar.__dataclass_fields__})
            if (
                not bar.is_closed
                or bar.timeframe != "1h"
                or bar.provider != run["provider"]
                or signal.candle_id != bar.candle_id
                or signal.stream_id != bar.stream_id
                or risk.signal_id != signal.signal_id
                or signal.strategy_version != "v1-deterministic"
            ):
                raise ValueError("paper_dataset_lineage")
        if len({i.risk.decision_id for i in items}) != len(items):
            raise ValueError("paper_dataset_duplicate_risk")
        groups = [list(g) for _, g in groupby(items, key=lambda i: i.candle.open_time)]
        # M3 commits each whole bar at its close. A later opening must not precede
        # that close, even when the bars belong to different symbols.
        if any(
            later[0].candle.open_time < earlier[0].candle.close_time
            for earlier, later in zip(groups, groups[1:], strict=False)
        ):
            raise ValueError("paper_overlapping_cross_asset_intervals")
        expected_status = (
            "READY"
            if run["step"] == 0
            else ("COMPLETED" if run["step"] == len(groups) else "RUNNING")
        )
        if not 0 <= run["step"] <= len(groups) or run["status"] != expected_status:
            raise ValueError("paper_checkpoint_mismatch")
        as_of = groups[run["step"] - 1][0].candle.close_time if run["step"] else None
        if run["as_of"] != as_of:
            raise ValueError("paper_checkpoint_time_mismatch")
        return groups
    except (ValueError, TypeError, KeyError) as error:
        raise ValueError("paper_invalid_frozen_dataset") from error


def reconcile(c: Connection, run: RowMapping) -> PaperBook:
    groups = frozen_groups(run)
    config = PaperConfig(run["initial_cash"], run["fee_bps"], run["slippage_bps"])
    book = PaperBook(config.initial_cash, config.initial_cash)
    run_id = run["run_id"]
    orders = {
        r["order_id"]: r
        for r in c.execute(select(paper_orders).where(paper_orders.c.run_id == run_id)).mappings()
    }
    fills = {
        r["order_id"]: r
        for r in c.execute(select(paper_fills).where(paper_fills.c.order_id.in_(orders))).mappings()
    }
    outcomes = {
        r["risk_decision_id"]: r
        for r in c.execute(
            select(paper_outcomes).where(paper_outcomes.c.run_id == run_id)
        ).mappings()
    }
    snapshots = {
        r["step"]: r
        for r in c.execute(
            select(portfolio_snapshots).where(portfolio_snapshots.c.run_id == run_id)
        ).mappings()
    }
    if set(snapshots) != set(range(1, run["step"] + 1)):
        raise ValueError("paper_snapshot_checkpoint_mismatch")
    previous: dict[str, DecisionItem] = {}
    marks = {}
    seen_orders: set[UUID] = set()
    seen_outcomes: set[UUID] = set()
    for step, group in enumerate(groups[: run["step"]], 1):
        opened, closed = group[0].candle.open_time, group[0].candle.close_time
        # At a shared timestamp, ALL opening prices, never current closing prices.
        book.marks.update({i.candle.symbol: i.candle.open for i in group})
        for current in group:
            symbol = current.candle.symbol
            item = previous.get(symbol)
            if item is None:
                continue
            identity = item.risk.decision_id
            seen_outcomes.add(identity)
            outcome = outcomes.get(identity)
            if outcome is None or (
                outcome["signal_id"],
                outcome["execution_candle_id"],
                outcome["timestamp"],
            ) != (item.signal.signal_id, current.candle.candle_id, opened):
                raise ValueError("paper_outcome_lineage_mismatch")
            side = item.signal.signal_type
            pos = book.positions.get(symbol, PaperPosition(symbol))
            reason = None
            if item.risk.decision != "APPROVED":
                reason = "risk_rejected"
            elif side == "HOLD":
                reason = "hold"
            elif opened < item.candle.close_time:
                raise ValueError("paper_look_ahead")
            elif opened - item.candle.close_time > timedelta(hours=1):
                reason = "expired_replay_signal"
            elif side == "BUY" and pos.quantity:
                reason = "position_already_open"
            elif side == "SELL" and not pos.quantity:
                reason = "no_long_position"
            if reason:
                if (outcome["status"], outcome["reason"], outcome["order_id"]) != (
                    "NO_ACTION",
                    reason,
                    None,
                ):
                    raise ValueError("paper_no_action_mismatch")
                continue
            reference = current.candle.open
            direction = Decimal(1) if side == "BUY" else Decimal(-1)
            price = money(reference * (1 + direction * config.slippage_bps / 10000))
            quantity = (
                entry_quantity(book.equity, price, config.fee_bps)
                if side == "BUY"
                else pos.quantity
            )
            notional = money(price * quantity)
            fee = money(notional * config.fee_bps / 10000)
            reason = "simulated_fill"
            if quantity < 1:
                reason = "position_size_below_one_share"
            elif side == "BUY" and notional + fee > book.cash:
                reason = "insufficient_simulated_cash"
            elif side == "BUY" and notional + fee > money(book.equity * Decimal("0.10")):
                reason = "position_allocation_exceeded"
            status = "FILLED" if reason == "simulated_fill" else "REJECTED"
            order_id = uuid5(run_id, str(identity))
            order = orders.get(order_id)
            if order is None or any(
                order[name] != value
                for name, value in {
                    "signal_id": item.signal.signal_id,
                    "risk_decision_id": identity,
                    "symbol": symbol,
                    "side": side,
                    "quantity": quantity,
                    "status": status,
                    "requested_at": opened,
                    "idempotency_key": order_id,
                    "reason": reason,
                }.items()
            ):
                raise ValueError("paper_order_lineage_or_sizing_mismatch")
            if (outcome["order_id"], outcome["status"], outcome["reason"]) != (
                order_id,
                status,
                reason,
            ):
                raise ValueError("paper_order_outcome_mismatch")
            seen_orders.add(order_id)
            fill = fills.get(order_id)
            if status == "REJECTED":
                if fill is not None:
                    raise ValueError("paper_rejected_order_has_fill")
                continue
            pnl = ZERO if side == "BUY" else money((price - pos.average_price) * quantity)
            if fill is None or any(
                fill[name] != value
                for name, value in {
                    "fill_id": uuid5(order_id, "fill"),
                    "price": price,
                    "reference_price": reference,
                    "quantity": quantity,
                    "fee": fee,
                    "slippage": money(abs(price - reference) * quantity),
                    "realized_pnl": pnl,
                    "filled_at": opened,
                }.items()
            ):
                raise ValueError("paper_fill_accounting_or_provenance_mismatch")
            # Fold VERIFIED fills, independently of the executor's mutations.
            if side == "BUY":
                book.cash = money(book.cash - notional - fee)
                pos.quantity, pos.average_price = quantity, price
            else:
                book.cash = money(book.cash + notional - fee)
                pos.quantity, pos.average_price = 0, ZERO
                pos.realized_pnl = money(pos.realized_pnl + pnl)
                book.realized_pnl = money(book.realized_pnl + pnl)
            book.positions[symbol] = pos
            book.fees = money(book.fees + fee)
            book.reconcile()
        for item in group:
            book.marks[item.candle.symbol] = item.candle.close
            marks[item.candle.symbol] = (item.candle.close, closed)
        book.reconcile()
        snapshot = snapshots[step]
        if snapshot["timestamp"] != closed or any(
            snapshot[name] != getattr(book, name) for name in FIELDS
        ):
            raise ValueError("paper_snapshot_mismatch")
        previous.update({i.candle.symbol: i for i in group})
    if set(orders) != seen_orders or set(outcomes) != seen_outcomes:
        raise ValueError("paper_unaccounted_orders_or_outcomes")
    saved_positions = {
        r["symbol"]: PaperPosition(
            r["symbol"], r["quantity"], r["average_price"], r["realized_pnl"]
        )
        for r in c.execute(select(positions).where(positions.c.run_id == run_id)).mappings()
    }
    saved_marks = {
        r["symbol"]: (r["price"], r["timestamp"])
        for r in c.execute(select(paper_marks).where(paper_marks.c.run_id == run_id)).mappings()
    }
    if (
        saved_marks != marks
        or saved_positions != book.positions
        or any(run[name] != getattr(book, name) for name in ("cash", "fees", "realized_pnl"))
    ):
        raise ValueError("paper_ledger_mismatch")
    return book
