"""PostgreSQL orchestration of a frozen, local replay; engines remain pure."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from itertools import groupby
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

from sqlalchemy import Connection, Engine, RowMapping, select
from sqlalchemy.dialects.postgresql import insert

from packages.contracts.decisions import DecisionItem, RiskResponse, SignalResponse
from packages.contracts.market import CandleResponse
from packages.domain.paper import ZERO, PaperBook, PaperConfig, PaperPosition, PaperResult, money
from packages.domain.risk import RiskDecision
from services.api.config import Settings
from services.api.models import (
    candles,
    paper_events,
    paper_fills,
    paper_marks,
    paper_orders,
    paper_outcomes,
    paper_runs,
    portfolio_snapshots,
    positions,
    risk_decisions,
    signals,
    system_controls,
)
from services.paper_executor.engine import PaperExecutor
from services.risk_engine.paper_sizing import entry_quantity


class PaperPaused(ValueError):
    pass


class PaperStore:
    def __init__(self, engine: Engine, settings: Settings) -> None:
        self.engine = engine
        self.settings = settings
        self.config = PaperConfig(
            settings.paper_initial_cash, settings.paper_fee_bps, settings.paper_slippage_bps
        )

    def _control(self, c: Connection) -> RowMapping:
        c.execute(
            insert(system_controls)
            .values(control_id=1, paused=False, updated_at=datetime.now(UTC))
            .on_conflict_do_nothing()
        )
        return c.execute(select(system_controls).with_for_update()).mappings().one()

    def event(
        self,
        c: Connection,
        run_id: UUID | None,
        kind: str,
        timestamp: datetime,
        payload: dict[str, Any],
        identity: UUID | None = None,
    ) -> None:
        correlation = identity or uuid4()
        c.execute(
            paper_events.insert().values(
                event_id=uuid5(correlation, kind),
                run_id=run_id,
                event_type=kind,
                schema_version="1.0",
                correlation_id=correlation,
                occurred_at=timestamp,
                recorded_at=datetime.now(UTC),
                payload=json.loads(json.dumps(payload, default=str)),
            )
        )

    def set_paused(self, paused: bool) -> None:
        with self.engine.begin() as c:
            control = self._control(c)
            if control["paused"] == paused:
                return
            now = datetime.now(UTC)
            c.execute(system_controls.update().values(paused=paused, updated_at=now))
            self.event(
                c,
                control["active_run_id"],
                "system.mode.changed",
                now,
                {"paused": paused, "mode": "LOCAL_PAPER"},
            )

    def initialize(self, *, reset: bool = False) -> UUID:
        with self.engine.begin() as c:
            control = self._control(c)
            if control["active_run_id"] and not reset:
                run = (
                    c.execute(
                        select(paper_runs).where(paper_runs.c.run_id == control["active_run_id"])
                    )
                    .mappings()
                    .one()
                )
                if (
                    PaperConfig(run["initial_cash"], run["fee_bps"], run["slippage_bps"])
                    != self.config
                ):
                    raise ValueError("paper_config_changed_requires_explicit_reset")
                return cast(UUID, run["run_id"])
            rows = c.execute(
                select(candles, signals, risk_decisions)
                .select_from(candles.join(signals).join(risk_decisions))
                .where(
                    candles.c.provider == self.settings.market_data_provider,
                    candles.c.symbol.in_(self.settings.symbols),
                    candles.c.timeframe == "1h",
                    candles.c.is_closed.is_(True),
                    signals.c.strategy_version == "v1-deterministic",
                )
                .order_by(candles.c.open_time, candles.c.symbol, candles.c.candle_id)
            ).mappings()
            dataset = [
                DecisionItem(
                    candle=CandleResponse.model_validate({col.name: r[col] for col in candles.c}),
                    signal=SignalResponse.model_validate({col.name: r[col] for col in signals.c}),
                    risk=RiskResponse.model_validate(
                        {col.name: r[col] for col in risk_decisions.c}
                    ),
                ).model_dump(mode="json", exclude={"paper"})
                for r in rows
            ]
            digest = hashlib.sha256(json.dumps(dataset, sort_keys=True).encode()).hexdigest()
            run_id = uuid4()
            now = datetime.now(UTC)
            c.execute(
                paper_runs.insert().values(
                    run_id=run_id,
                    mode="REPLAY",
                    provider=self.settings.market_data_provider,
                    status="READY",
                    initial_cash=self.config.initial_cash,
                    cash=self.config.initial_cash,
                    fees=ZERO,
                    realized_pnl=ZERO,
                    fee_bps=self.config.fee_bps,
                    slippage_bps=self.config.slippage_bps,
                    dataset=dataset,
                    dataset_hash=digest,
                    step=0,
                    as_of=None,
                    created_at=now,
                )
            )
            c.execute(system_controls.update().values(active_run_id=run_id, updated_at=now))
            self.event(
                c,
                run_id,
                "paper.run.created",
                now,
                {
                    "dataset_hash": digest,
                    "count": len(dataset),
                    "previous_run_id": control["active_run_id"],
                    "config": asdict(self.config),
                },
            )
            return run_id

    @staticmethod
    def load_book(c: Connection, run: RowMapping) -> PaperBook:
        run_id = run["run_id"]
        book = PaperBook(run["initial_cash"], run["cash"], run["fees"], run["realized_pnl"])
        for row in c.execute(select(positions).where(positions.c.run_id == run_id)).mappings():
            book.positions[row["symbol"]] = PaperPosition(
                row["symbol"], row["quantity"], row["average_price"], row["realized_pnl"]
            )
        book.marks = {
            r["symbol"]: r["price"]
            for r in c.execute(select(paper_marks).where(paper_marks.c.run_id == run_id)).mappings()
        }
        return book

    def replay(
        self, *, max_steps: int | None = None, after_fill: Callable[[], None] | None = None
    ) -> UUID:
        run_id = self.initialize()
        with self.engine.connect() as c:
            raw = (
                c.execute(select(paper_runs).where(paper_runs.c.run_id == run_id)).mappings().one()
            )
            dataset = [DecisionItem.model_validate(d) for d in raw["dataset"]]
        groups = [list(items) for _, items in groupby(dataset, key=lambda d: d.candle.open_time)]
        previous: dict[str, DecisionItem] = {}
        for step, group in enumerate(groups, start=1):
            if max_steps is not None and step > max_steps:
                break
            self._group(run_id, step, group, previous, step == len(groups), after_fill)
            previous.update({item.candle.symbol: item for item in group})
        return run_id

    def _group(
        self,
        run_id: UUID,
        step: int,
        group: list[DecisionItem],
        previous: dict[str, DecisionItem],
        final: bool,
        after_fill: Callable[[], None] | None,
    ) -> None:
        with self.engine.begin() as c:
            control = self._control(c)  # pause/reset and execution share this lock
            if control["active_run_id"] != run_id:
                raise ValueError("paper_run_changed")
            run = (
                c.execute(select(paper_runs).where(paper_runs.c.run_id == run_id).with_for_update())
                .mappings()
                .one()
            )
            if run["step"] >= step:
                return
            if control["paused"]:
                raise PaperPaused("paper_paused")
            if run["step"] != step - 1:
                raise ValueError("paper_checkpoint_gap")
            book = self.reconcile(c, run)
            executor = PaperExecutor(
                PaperConfig(run["initial_cash"], run["fee_bps"], run["slippage_bps"])
            )
            opened, closed = group[0].candle.open_time, group[0].candle.close_time
            # All opens in this timestamp are visible; NO current close is available yet.
            for current in group:
                book.marks[current.candle.symbol] = current.candle.open
            for current in group:
                symbol = current.candle.symbol
                item = previous.get(symbol)
                if item is None:
                    continue
                risk = RiskDecision(**item.risk.model_dump())
                if risk.decision != "APPROVED":
                    result = PaperResult("NO_ACTION", "risk_rejected")
                elif item.signal.signal_type == "HOLD":
                    result = PaperResult("NO_ACTION", "hold")
                elif opened < item.candle.close_time:
                    raise ValueError("paper_look_ahead")
                elif opened - item.candle.close_time > timedelta(hours=1):
                    result = PaperResult("NO_ACTION", "expired_replay_signal")
                else:
                    side = item.signal.signal_type
                    quantity = (
                        entry_quantity(
                            book.equity,
                            executor.fill_price(current.candle.open, side),
                            executor.config.fee_bps,
                        )
                        if side == "BUY"
                        else 0
                    )
                    result = executor.execute(
                        book, symbol, side, current.candle.open, quantity, risk
                    )
                order_id = None
                if result.status != "NO_ACTION":
                    order_id = uuid5(run_id, str(risk.decision_id))
                    c.execute(
                        paper_orders.insert().values(
                            order_id=order_id,
                            run_id=run_id,
                            signal_id=item.signal.signal_id,
                            risk_decision_id=risk.decision_id,
                            symbol=symbol,
                            side=item.signal.signal_type,
                            quantity=result.quantity,
                            status=result.status,
                            requested_at=opened,
                            idempotency_key=order_id,
                            reason=result.reason,
                        )
                    )
                    self.event(
                        c,
                        run_id,
                        "paper.order.created",
                        opened,
                        {"order_id": order_id, "status": result.status},
                        order_id,
                    )
                    if result.status == "FILLED":
                        c.execute(
                            paper_fills.insert().values(
                                fill_id=uuid5(order_id, "fill"),
                                order_id=order_id,
                                price=result.price,
                                reference_price=current.candle.open,
                                quantity=result.quantity,
                                fee=result.fee,
                                slippage=result.slippage,
                                realized_pnl=result.realized_pnl,
                                filled_at=opened,
                            )
                        )
                        if after_fill:
                            after_fill()  # fault-injection seam; entire group must roll back
                        self.event(
                            c, run_id, "paper.order.filled", opened, asdict(result), order_id
                        )
                        self.event(
                            c,
                            run_id,
                            "position.updated",
                            opened,
                            asdict(book.positions[symbol]),
                            order_id,
                        )
                c.execute(
                    paper_outcomes.insert().values(
                        run_id=run_id,
                        risk_decision_id=risk.decision_id,
                        signal_id=item.signal.signal_id,
                        execution_candle_id=current.candle.candle_id,
                        order_id=order_id,
                        status=result.status,
                        reason=result.reason,
                        timestamp=opened,
                    )
                )
            # Only now mark all current closes and advance the common clock.
            for item in group:
                book.marks[item.candle.symbol] = item.candle.close
                values = dict(
                    run_id=run_id,
                    symbol=item.candle.symbol,
                    price=item.candle.close,
                    timestamp=closed,
                )
                c.execute(
                    insert(paper_marks)
                    .values(**values)
                    .on_conflict_do_update(index_elements=["run_id", "symbol"], set_=values)
                )
            book.reconcile()
            for pos in book.positions.values():
                values = {"run_id": run_id, **asdict(pos), "updated_at": closed}
                c.execute(
                    insert(positions)
                    .values(**values)
                    .on_conflict_do_update(index_elements=["run_id", "symbol"], set_=values)
                )
            c.execute(
                paper_runs.update()
                .where(paper_runs.c.run_id == run_id)
                .values(
                    cash=book.cash,
                    fees=book.fees,
                    realized_pnl=book.realized_pnl,
                    step=step,
                    as_of=closed,
                    status="COMPLETED" if final else "RUNNING",
                )
            )
            snapshot = {
                name: getattr(book, name)
                for name in (
                    "cash",
                    "market_value",
                    "equity",
                    "realized_pnl",
                    "unrealized_pnl",
                    "total_pnl",
                    "fees",
                )
            }
            c.execute(
                portfolio_snapshots.insert().values(
                    run_id=run_id, step=step, timestamp=closed, **snapshot
                )
            )
            self.event(c, run_id, "portfolio.updated", closed, snapshot, uuid5(run_id, str(step)))

    def reconcile(self, c: Connection, run: RowMapping) -> PaperBook:
        """Rebuild balances/positions from fills, independently of saved balances."""
        saved = self.load_book(c, run)
        ledger = PaperBook(run["initial_cash"], run["initial_cash"], marks=saved.marks)
        rows = c.execute(
            select(paper_orders, paper_fills)
            .select_from(paper_orders.outerjoin(paper_fills))
            .where(paper_orders.c.run_id == run["run_id"])
            .order_by(paper_orders.c.requested_at, paper_orders.c.symbol, paper_orders.c.order_id)
        ).mappings()
        for r in rows:
            if r[paper_orders.c.status] == "REJECTED":
                if r[paper_fills.c.fill_id] is not None:
                    raise ValueError("paper_rejected_order_has_fill")
                continue
            if (
                r[paper_fills.c.fill_id] is None
                or r[paper_orders.c.quantity] != r[paper_fills.c.quantity]
            ):
                raise ValueError("paper_order_fill_mismatch")
            qty, price, fee = (
                r[paper_fills.c.quantity],
                r[paper_fills.c.price],
                r[paper_fills.c.fee],
            )
            symbol = r[paper_orders.c.symbol]
            pos = ledger.positions.setdefault(symbol, PaperPosition(symbol))
            notional = money(price * qty)
            direction = 1 if r[paper_orders.c.side] == "BUY" else -1
            reference = r[paper_fills.c.reference_price]
            if price != money(reference * (1 + direction * run["slippage_bps"] / 10000)) or r[
                paper_fills.c.slippage
            ] != money(abs(price - reference) * qty):
                raise ValueError("paper_fill_price_mismatch")
            if r[paper_orders.c.side] == "BUY":
                if pos.quantity:
                    raise ValueError("paper_pyramiding_detected")
                pos.quantity, pos.average_price = qty, price
                ledger.cash = money(ledger.cash - notional - fee)
                pnl = ZERO
            else:
                if pos.quantity != qty:
                    raise ValueError("paper_short_or_partial_close")
                pnl = money((price - pos.average_price) * qty)
                pos.realized_pnl = money(pos.realized_pnl + pnl)
                ledger.realized_pnl = money(ledger.realized_pnl + pnl)
                ledger.cash = money(ledger.cash + notional - fee)
                pos.quantity, pos.average_price = 0, ZERO
            if pnl != r[paper_fills.c.realized_pnl] or fee != money(
                notional * run["fee_bps"] / 10000
            ):
                raise ValueError("paper_fill_accounting_mismatch")
            ledger.fees = money(ledger.fees + fee)
        ledger.reconcile()
        if (ledger.cash, ledger.fees, ledger.realized_pnl, ledger.positions) != (
            saved.cash,
            saved.fees,
            saved.realized_pnl,
            saved.positions,
        ):
            raise ValueError("paper_ledger_mismatch")
        saved.reconcile()
        last = (
            c.execute(
                select(portfolio_snapshots).where(
                    portfolio_snapshots.c.run_id == run["run_id"],
                    portfolio_snapshots.c.step == run["step"],
                )
            )
            .mappings()
            .first()
        )
        if run["step"] and (
            last is None
            or any(
                last[name] != getattr(saved, name)
                for name in (
                    "cash",
                    "market_value",
                    "equity",
                    "fees",
                    "realized_pnl",
                    "unrealized_pnl",
                    "total_pnl",
                )
            )
        ):
            raise ValueError("paper_snapshot_mismatch")
        return saved
