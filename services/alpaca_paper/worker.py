import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import Engine, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from packages.domain.risk import RiskDecision
from services.alpaca_paper.adapter import AlpacaPaperAdapter
from services.alpaca_paper.executor import AlpacaPaperExecutor
from services.alpaca_paper.guard import ExecutionGuard
from services.api.config import Settings
from services.api.models import (
    broker_orders,
    broker_portfolio_snapshots,
    broker_positions,
    candles,
    paper_orders,
    paper_runs,
    risk_decisions,
    signals,
    system_controls,
)

logger = logging.getLogger("trading_bot.alpaca_worker")

ACTIVE_ORDER_STATUSES = (
    "SUBMITTING",
    "NEW",
    "ACCEPTED",
    "PENDING_NEW",
    "PARTIALLY_FILLED",
    "PENDING_CANCEL",
    "REPLACED",
    "UNKNOWN",
)


class AlpacaPaperWorker:
    def __init__(
        self,
        engine: Engine,
        adapter: AlpacaPaperAdapter,
        settings: Settings,
        *,
        release_on_ready: bool = False,
    ) -> None:
        self.engine = engine
        self.adapter = adapter
        self.settings = settings
        self.executor = AlpacaPaperExecutor(adapter)
        self.task: asyncio.Task[None] | None = None
        self.running = False
        self.degraded = True
        self.reconciliation_ready = False
        self.degraded_reason: str | None = "startup_reconciliation_pending"
        self.release_on_ready = release_on_ready
        self.execution_released = False

    def start(self) -> None:
        if self.task is None or self.task.done():
            self.running = True
            self.task = asyncio.create_task(self._run(), name="alpaca-paper-worker")

    async def stop(self) -> None:
        self.running = False
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

    async def preflight(self) -> bool:
        try:
            account = await self.adapter.get_account()
            return account.get("status") == "ACTIVE"
        except Exception as error:
            logger.error("Alpaca PAPER preflight failed: %s", error)
            return False

    async def _run(self) -> None:
        async with self.adapter:
            while self.running:
                try:
                    account, positions = await self.reconcile_once()
                    if self.release_on_ready and not self.execution_released:
                        await asyncio.to_thread(self._release_execution)
                        self.execution_released = True
                    await self._process_pending_submits(account=account, positions=positions)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    await self._enter_degraded(str(error))
                    logger.error("Paper cycle failed closed: %s", error)
                await asyncio.sleep(3.0)

    async def reconcile_once(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Refresh all broker state before opening the execution gate."""

        self.reconciliation_ready = False
        self.degraded = True
        self.degraded_reason = "reconciliation_in_progress"

        account = await self.adapter.get_account()
        if account.get("status") != "ACTIVE":
            raise RuntimeError(f"alpaca_paper_account_not_active:{account.get('status')}")

        await self._reconcile_active_orders()
        # Refresh account and positions after order reconciliation so a fill
        # observed in this cycle cannot be paired with an older exposure view.
        account = await self.adapter.get_account()
        if account.get("status") != "ACTIVE":
            raise RuntimeError(f"alpaca_paper_account_not_active:{account.get('status')}")
        positions = await self.adapter.get_positions()
        self._validate_positions(positions)
        open_orders = await self.adapter.get_open_orders()
        await asyncio.to_thread(self._assert_open_orders_known, open_orders)
        await asyncio.to_thread(self._save_broker_snapshot, account, positions, "ACTIVE")

        self.degraded = False
        self.reconciliation_ready = True
        self.degraded_reason = None
        return account, positions

    def _release_execution(self) -> None:
        with self.engine.begin() as connection:
            control = (
                connection.execute(
                    select(system_controls)
                    .where(system_controls.c.control_id == 1)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if control is None or control["active_run_id"] is None:
                raise RuntimeError("active_alpaca_paper_run_missing_baseline_reset_first")
            mode = connection.scalar(
                select(paper_runs.c.mode).where(paper_runs.c.run_id == control["active_run_id"])
            )
            if mode != "ALPACA_PAPER":
                raise RuntimeError(f"active_run_mode_mismatch:{mode}")
            connection.execute(
                update(paper_runs)
                .where(paper_runs.c.run_id == control["active_run_id"])
                .values(status="RUNNING")
            )
            connection.execute(
                update(system_controls)
                .where(system_controls.c.control_id == 1)
                .values(paused=False, updated_at=datetime.now(UTC))
            )

    @staticmethod
    def _decimal(value: Any, field: str) -> Decimal:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise RuntimeError(f"invalid_broker_{field}") from error
        if not result.is_finite():
            raise RuntimeError(f"invalid_broker_{field}")
        return result

    def _validate_positions(self, positions: list[dict[str, Any]]) -> None:
        seen: set[str] = set()
        for position in positions:
            symbol = str(position.get("symbol", "")).upper()
            quantity = self._decimal(position.get("qty"), "position_quantity")
            market_value = self._decimal(position.get("market_value"), "position_market_value")
            self._decimal(position.get("avg_entry_price"), "average_price")
            self._decimal(position.get("current_price"), "current_price")
            if not symbol or symbol in seen:
                raise RuntimeError("broker_position_identity_unknown")
            if symbol not in ExecutionGuard.ALLOWED_SYMBOLS:
                raise RuntimeError(f"unmanaged_broker_position:{symbol}")
            if quantity < 0 or market_value < 0:
                raise RuntimeError(f"short_broker_position_forbidden:{symbol}")
            seen.add(symbol)

    def _assert_open_orders_known(self, open_orders: list[dict[str, Any]]) -> None:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    select(
                        broker_orders.c.broker_order_id,
                        broker_orders.c.client_order_id,
                        broker_orders.c.requested_notional,
                        broker_orders.c.requested_quantity,
                        paper_orders.c.symbol,
                        paper_orders.c.side,
                        paper_orders.c.status,
                    ).join(paper_orders, broker_orders.c.order_id == paper_orders.c.order_id)
                )
                .mappings()
                .all()
            )

        by_broker_id = {row["broker_order_id"]: row for row in rows if row["broker_order_id"]}
        by_client_id = {row["client_order_id"]: row for row in rows}
        for remote in open_orders:
            broker_id = remote.get("id")
            client_id = remote.get("client_order_id")
            local = by_broker_id.get(broker_id) or by_client_id.get(client_id)
            if local is None:
                raise RuntimeError(
                    f"unknown_broker_open_order:{broker_id or client_id or 'missing_id'}"
                )
            if str(remote.get("symbol", "")).upper() != local["symbol"]:
                raise RuntimeError(f"broker_order_symbol_divergence:{broker_id or client_id}")
            if str(remote.get("side", "")).upper() != local["side"]:
                raise RuntimeError(f"broker_order_side_divergence:{broker_id or client_id}")
            if local["status"] not in ACTIVE_ORDER_STATUSES:
                raise RuntimeError(f"broker_order_status_divergence:{broker_id or client_id}")
            if local["side"] == "BUY":
                remote_notional = remote.get("notional")
                local_notional = local["requested_notional"]
                if (
                    remote_notional is None
                    or local_notional is None
                    or self._decimal(remote_notional, "open_order_notional")
                    != Decimal(str(local_notional))
                ):
                    raise RuntimeError(f"broker_order_notional_divergence:{broker_id or client_id}")
            else:
                remote_quantity = remote.get("qty")
                local_quantity = local["requested_quantity"]
                if (
                    remote_quantity is None
                    or local_quantity is None
                    or self._decimal(remote_quantity, "open_order_quantity")
                    != Decimal(str(local_quantity))
                ):
                    raise RuntimeError(f"broker_order_quantity_divergence:{broker_id or client_id}")

    async def _enter_degraded(self, reason: str) -> None:
        self.degraded = True
        self.reconciliation_ready = False
        self.degraded_reason = reason[:255]

        def persist() -> None:
            with self.engine.begin() as connection:
                connection.execute(
                    update(broker_portfolio_snapshots)
                    .where(broker_portfolio_snapshots.c.provider == "alpaca")
                    .values(status="DEGRADED")
                )

        try:
            await asyncio.to_thread(persist)
        except Exception:
            logger.exception("Could not persist DEGRADED broker status")

    async def _process_pending_submits(
        self,
        *,
        account: dict[str, Any] | None = None,
        positions: list[dict[str, Any]] | None = None,
    ) -> None:
        if self.degraded or not self.reconciliation_ready:
            return

        def fetch_pending() -> list[dict[str, Any]] | None:
            with self.engine.connect() as connection:
                control = connection.execute(select(system_controls)).mappings().first()
                if not control or control["paused"] or not control["active_run_id"]:
                    return None
                run_id = control["active_run_id"]
                query = (
                    select(risk_decisions, signals, candles.c.symbol)
                    .join(signals, risk_decisions.c.signal_id == signals.c.signal_id)
                    .join(candles, signals.c.candle_id == candles.c.candle_id)
                    .outerjoin(
                        paper_orders,
                        paper_orders.c.risk_decision_id == risk_decisions.c.decision_id,
                    )
                    .where(
                        risk_decisions.c.decision == "APPROVED",
                        paper_orders.c.order_id.is_(None),
                        risk_decisions.c.run_id == run_id,
                    )
                    .order_by(risk_decisions.c.decided_at)
                    .limit(10)
                )
                return [
                    {"run_id": run_id, **dict(row)} for row in connection.execute(query).mappings()
                ]

        pending = await asyncio.to_thread(fetch_pending)
        if not pending:
            return
        if account is None or positions is None:
            raise RuntimeError("broker_state_not_supplied_to_execution")

        last_equity = self._decimal(account.get("equity"), "equity")
        snapshot_time = datetime.now(UTC)

        for row in pending:
            if self.degraded or not self.reconciliation_ready:
                return
            run_id = row["run_id"]
            risk = RiskDecision(
                decision_id=row["decision_id"],
                signal_id=row["signal_id"],
                decision=row["decision"],
                reason=row["reason"],
                decided_at=row["decided_at"],
            )
            symbol = row["symbol"]
            side = row["signal_type"]

            if side not in ("BUY", "SELL"):
                with self.engine.begin() as connection:
                    connection.execute(
                        update(risk_decisions)
                        .where(risk_decisions.c.decision_id == risk.decision_id)
                        .values(decision="REJECTED", reason=f"Invalid side {side} for execution")
                    )
                continue

            with self.engine.connect() as connection:
                blocked_symbols = list(
                    connection.scalars(
                        select(paper_orders.c.symbol).where(
                            paper_orders.c.status == "REJECTED",
                            paper_orders.c.reason.ilike("%qty%"),
                            paper_orders.c.requested_at
                            >= datetime.now(UTC) - timedelta(minutes=60),
                        )
                    )
                )
                in_flight_rows = (
                    connection.execute(
                        select(
                            paper_orders.c.symbol,
                            paper_orders.c.side,
                            paper_orders.c.quantity,
                            broker_orders.c.requested_notional,
                        )
                        .outerjoin(
                            broker_orders, paper_orders.c.order_id == broker_orders.c.order_id
                        )
                        .where(
                            or_(
                                paper_orders.c.status.in_(ACTIVE_ORDER_STATUSES),
                                paper_orders.c.requested_at >= snapshot_time,
                            )
                        )
                    )
                    .mappings()
                    .all()
                )

            in_flight = [dict(item) for item in in_flight_rows]
            approved, reason = ExecutionGuard.evaluate(
                side=side,
                symbol=symbol,
                positions=positions,
                snapshot=account,
                last_equity=last_equity,
                in_flight=in_flight,
                blocked_symbols=blocked_symbols,
                state_known=self.reconciliation_ready,
            )
            if not approved:
                with self.engine.begin() as connection:
                    connection.execute(
                        update(risk_decisions)
                        .where(risk_decisions.c.decision_id == risk.decision_id)
                        .values(decision="REJECTED", reason=reason)
                    )
                logger.info("Guard rejected %s %s: %s", side, symbol, reason)
                continue

            if side == "SELL":
                broker_quantity = sum(
                    (
                        self._decimal(position.get("qty"), "position_quantity")
                        for position in positions
                        if position.get("symbol") == symbol
                    ),
                    Decimal("0"),
                )
                pending_sell_quantity = sum(
                    (
                        self._decimal(item.get("quantity", 0), "pending_sell_quantity")
                        for item in in_flight
                        if item["symbol"] == symbol and item["side"] == "SELL"
                    ),
                    Decimal("0"),
                )
                quantity = broker_quantity - pending_sell_quantity
                if quantity <= 0:
                    raise RuntimeError(f"sell_quantity_unavailable:{symbol}")
                notional = None
            else:
                quantity = Decimal("0")
                notional = ExecutionGuard.MAX_NOTIONAL_PER_TRADE

            order_id = uuid5(run_id, str(risk.decision_id))
            await self.executor.submit(
                engine=self.engine,
                run_id=run_id,
                signal_id=row["signal_id"],
                risk=risk,
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_id=order_id,
                requested_at=datetime.now(UTC),
                notional=notional,
            )

    def _save_broker_snapshot(
        self,
        account: dict[str, Any],
        remote_positions: list[dict[str, Any]],
        status: str,
    ) -> None:
        cash = self._decimal(account.get("cash"), "cash")
        equity = self._decimal(account.get("equity"), "equity")
        portfolio_value = self._decimal(account.get("portfolio_value"), "portfolio_value")
        buying_power = self._decimal(account.get("buying_power", 0), "buying_power")
        market_value = portfolio_value - cash
        reconciled_at = datetime.now(UTC)

        positions_data = []
        unrealized_pnl_total = Decimal("0")
        for remote in remote_positions:
            unrealized_pnl = self._decimal(remote.get("unrealized_pl", 0), "unrealized_pnl")
            unrealized_pnl_total += unrealized_pnl
            positions_data.append(
                {
                    "provider": "alpaca",
                    "symbol": str(remote["symbol"]).upper(),
                    "quantity": self._decimal(remote.get("qty"), "position_quantity"),
                    "average_price": self._decimal(remote.get("avg_entry_price"), "average_price"),
                    "current_price": self._decimal(remote.get("current_price"), "current_price"),
                    "market_value": self._decimal(remote.get("market_value"), "market_value"),
                    "unrealized_pnl": unrealized_pnl,
                    "updated_at": reconciled_at,
                }
            )

        with self.engine.begin() as connection:
            statement = insert(broker_portfolio_snapshots).values(
                provider="alpaca",
                status=status,
                cash=cash,
                market_value=market_value,
                equity=equity,
                unrealized_pnl=unrealized_pnl_total,
                buying_power=buying_power,
                last_reconciled_at=reconciled_at,
            )
            connection.execute(
                statement.on_conflict_do_update(
                    index_elements=["provider"],
                    set_={
                        "status": status,
                        "cash": statement.excluded.cash,
                        "market_value": statement.excluded.market_value,
                        "equity": statement.excluded.equity,
                        "unrealized_pnl": statement.excluded.unrealized_pnl,
                        "buying_power": statement.excluded.buying_power,
                        "last_reconciled_at": statement.excluded.last_reconciled_at,
                    },
                )
            )
            connection.execute(
                broker_positions.delete().where(broker_positions.c.provider == "alpaca")
            )
            if positions_data:
                connection.execute(insert(broker_positions), positions_data)

    async def _snapshot_broker_portfolio(self) -> None:
        account = await self.adapter.get_account()
        positions = await self.adapter.get_positions()
        self._validate_positions(positions)
        await asyncio.to_thread(self._save_broker_snapshot, account, positions, "ACTIVE")

    async def _reconcile_active_orders(self) -> None:
        def fetch_active() -> list[UUID]:
            with self.engine.connect() as connection:
                return list(
                    connection.scalars(
                        select(paper_orders.c.order_id).where(
                            paper_orders.c.status.in_(ACTIVE_ORDER_STATUSES)
                        )
                    )
                )

        active_orders = await asyncio.to_thread(fetch_active)
        for order_id in active_orders:
            await self.executor.reconcile_order(self.engine, order_id)
