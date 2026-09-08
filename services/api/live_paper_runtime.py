"""Fail-closed coordinator for automatic Alpaca paper orders."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_OID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Engine

from packages.contracts.broker import BrokerOrder, ExternalBroker
from packages.contracts.provider import MarketDataProvider
from services.api.database import check_database

logger = logging.getLogger("live_paper_runtime")
OPEN_STATES = {"pending_new", "accepted", "new", "partially_filled"}
TERMINAL_STATES = {"filled", "canceled", "rejected", "expired"}
REMOTE_STATES = OPEN_STATES | TERMINAL_STATES
STRATEGY_VERSION = "v2-15m-baseline"


class ReconciliationError(RuntimeError):
    """Remote and local broker audit cannot be reconciled safely."""


class LivePaperExecutionRuntime:
    def __init__(
        self,
        broker: ExternalBroker,
        engine: Engine,
        symbols: list[str],
        provider: MarketDataProvider,
    ) -> None:
        self.broker = broker
        self.engine = engine
        self.symbols = list(dict.fromkeys(symbols))
        self.provider = provider
        self.running = False
        self._task: asyncio.Task[None] | None = None
        self._cycle_lock = asyncio.Lock()
        self.execution_ready = False

    def start(self) -> None:
        if not self.running:
            self.running = True
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while self.running:
            try:
                blocked_symbols = await self._reconcile()
                self.execution_ready = True
                await self._process_pending(blocked_symbols)
            except Exception:
                self.execution_ready = False
                logger.error("Live paper cycle failed closed")
            await asyncio.sleep(5)

    async def _reconcile(self) -> set[str]:
        self.execution_ready = False
        if check_database(self.engine) != "up":
            raise ReconciliationError("database_not_ready")
        account = await self.broker.get_account()
        clock = await self.broker.get_clock()
        positions = await self.broker.get_positions()
        self._validate_account(account)
        self._validate_clock(clock)
        self._validate_positions(positions)
        remote_orders = await self.broker.get_orders()
        if any(order.status not in REMOTE_STATES for order in remote_orders):
            raise ReconciliationError("unknown_remote_order_state")
        with self.engine.connect() as conn:
            local = {
                row.client_order_id: row
                for row in conn.execute(
                    text(
                        "SELECT client_order_id,status,symbol FROM broker_orders "
                        "ORDER BY submitted_at,client_order_id"
                    )
                )
            }
        remote_by_id = {order.client_order_id: order for order in remote_orders}
        for client_id in remote_by_id:
            if client_id.startswith("agy-") and client_id not in local:
                raise ReconciliationError("remote_order_missing_local_audit")

        blocked_symbols = set()
        for client_id, row in local.items():
            remote = remote_by_id.get(client_id)
            if remote is None and row.status in {
                "pending_new",
                "accepted",
                "new",
                "partially_filled",
                "submission_ambiguous",
            }:
                remote = await self.broker.get_order_by_client_order_id(client_id)
            if remote is None:
                if row.status == "pre_submit":
                    with self.engine.begin() as conn:
                        conn.execute(
                            text("DELETE FROM broker_orders WHERE client_order_id=:cid"),
                            {"cid": client_id}
                        )
                    continue
                if row.status in {
                    "pending_new",
                    "accepted",
                    "new",
                    "partially_filled",
                    "submission_ambiguous",
                }:
                    logger.error(f"Ambiguous order {client_id} for {row.symbol}; blocking symbol")
                    blocked_symbols.add(row.symbol)
                continue

            try:
                self._apply_remote(remote)
            except ReconciliationError:
                logger.error(f"Reconciliation error for {row.symbol}; blocking symbol")
                blocked_symbols.add(row.symbol)

        self.execution_ready = True
        return blocked_symbols

    def _mark_failed_local(self, client_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE broker_orders SET status='failed_local', last_reconciliation_at=:now WHERE client_order_id=:cid"
                ),
                {"cid": client_id, "now": datetime.now(UTC)},
            )

    def _mark_ambiguous(self, client_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE broker_orders SET status='submission_ambiguous', last_reconciliation_at=:now WHERE client_order_id=:cid"
                ),
                {"cid": client_id, "now": datetime.now(UTC)},
            )

    def _apply_remote(self, order: BrokerOrder) -> None:
        if (
            not order.client_order_id
            or not order.broker_order_id
            or order.status not in REMOTE_STATES
            or order.side.upper() not in {"BUY", "SELL"}
            or order.requested_qty <= 0
            or order.filled_qty < 0
            or (order.filled_qty > 0 and Decimal(order.filled_avg_price) <= 0)
            or (order.status == "filled" and order.filled_qty != order.requested_qty)
            or (
                order.status == "partially_filled"
                and not 0 < order.filled_qty < order.requested_qty
            )
        ):
            raise ReconciliationError("invalid_remote_order")
        with self.engine.begin() as conn:
            local = conn.execute(
                text(
                    "SELECT symbol,side,requested_qty FROM broker_orders "
                    "WHERE client_order_id=:cid FOR UPDATE"
                ),
                {"cid": order.client_order_id},
            ).fetchone()
            if (
                local is None
                or order.symbol != local.symbol
                or order.side.upper() != local.side
                or order.requested_qty != local.requested_qty
                or order.filled_qty > local.requested_qty
            ):
                raise ReconciliationError("remote_order_divergence")
            fills = conn.execute(
                text("SELECT qty,price FROM broker_fills WHERE client_order_id=:cid FOR UPDATE"),
                {"cid": order.client_order_id},
            ).fetchall()
            local_qty = sum(int(fill.qty) for fill in fills)
            if local_qty > order.filled_qty:
                raise ReconciliationError("local_fill_exceeds_remote")
            delta = order.filled_qty - local_qty
            if delta:
                average = Decimal(order.filled_avg_price)
                if average <= 0:
                    raise ReconciliationError("remote_fill_price_invalid")
                local_notional = sum(Decimal(fill.price) * int(fill.qty) for fill in fills)
                delta_price = (average * order.filled_qty - local_notional) / delta
                if delta_price <= 0:
                    raise ReconciliationError("remote_fill_notional_divergence")
                conn.execute(
                    text(
                        "INSERT INTO broker_fills "
                        "(fill_id,client_order_id,qty,price,filled_at) "
                        "VALUES (:fid,:cid,:qty,:price,:at)"
                    ),
                    {
                        "fid": f"{order.client_order_id}-{order.filled_qty}",
                        "cid": order.client_order_id,
                        "qty": delta,
                        "price": delta_price,
                        "at": order.updated_at,
                    },
                )
            conn.execute(
                text(
                    "UPDATE broker_orders SET broker_order_id=:bid,status=:status,"
                    "filled_qty=:qty,filled_avg_price=:price,filled_at=:filled_at,"
                    "last_reconciliation_at=:now WHERE client_order_id=:cid"
                ),
                {
                    "cid": order.client_order_id,
                    "bid": order.broker_order_id,
                    "status": order.status,
                    "qty": order.filled_qty,
                    "price": order.filled_avg_price or None,
                    "filled_at": order.updated_at if order.status == "filled" else None,
                    "now": datetime.now(UTC),
                },
            )

    @staticmethod
    def _validate_account(account: Any) -> None:
        values = (Decimal(account.equity), Decimal(account.cash), Decimal(account.buying_power))
        if account.currency != "USD" or any(not value.is_finite() or value < 0 for value in values):
            raise ReconciliationError("invalid_remote_account")

    @staticmethod
    def _validate_clock(clock: Any) -> None:
        if clock.timestamp.tzinfo is None or clock.timestamp.utcoffset() is None:
            raise ReconciliationError("invalid_remote_clock")

    @staticmethod
    def _validate_positions(positions: list[Any]) -> None:
        symbols: set[str] = set()
        for position in positions:
            prices = (Decimal(position.average_entry_price), Decimal(position.current_price))
            if (
                not position.symbol
                or position.symbol in symbols
                or position.quantity < 0
                or any(not price.is_finite() or price < 0 for price in prices)
            ):
                raise ReconciliationError("invalid_remote_positions")
            symbols.add(position.symbol)

    @staticmethod
    def _regular_open(clock: Any) -> bool:
        local = clock.timestamp.astimezone(ZoneInfo("America/New_York"))
        minute = local.hour * 60 + local.minute
        return bool(clock.is_open and local.weekday() < 5 and 570 <= minute < 960)

    async def _process_pending(self, blocked_symbols: set[str]) -> None:
        async with self._cycle_lock:
            if not self.execution_ready or check_database(self.engine) != "up":
                return
            clock = await self.broker.get_clock()
            if not self._regular_open(clock):
                return
            with self.engine.connect() as conn:
                ctrl = conn.execute(
                    text(
                        "SELECT armed,activation_cutoff FROM live_paper_control WHERE control_id=1"
                    )
                ).fetchone()
            if not ctrl or not ctrl.armed or ctrl.activation_cutoff is None:
                return
            status = self.provider.get_status()
            if status.state not in ("connected", "degraded"):
                return
            now = datetime.now(UTC)
            for symbol in self.symbols:
                if symbol in blocked_symbols or symbol in status.degraded_symbols:
                    continue
                await self._process_symbol(symbol, now, ctrl.activation_cutoff)

    async def _process_symbol(self, symbol: str, now: datetime, cutoff: datetime) -> None:
        with self.engine.connect() as conn:
            latest = conn.execute(
                text(
                    "SELECT close_time FROM candles WHERE symbol=:symbol "
                    "AND timeframe='1m' AND provider='alpaca' AND is_closed=true "
                    "ORDER BY close_time DESC LIMIT 1"
                ),
                {"symbol": symbol},
            ).fetchone()
        if not latest or latest.close_time > now or now - latest.close_time > timedelta(minutes=5):
            return
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT r.decision_id,r.signal_id,s.signal_type,s.strategy_version,"
                    "s.generated_at,c.close AS reference_price FROM risk_decisions r "
                    "JOIN signals s ON r.signal_id=s.signal_id "
                    "JOIN candles c ON s.candle_id=c.candle_id "
                    "LEFT JOIN broker_orders b ON r.decision_id=b.risk_decision_id "
                    "WHERE b.client_order_id IS NULL AND r.decision='APPROVED' "
                    "AND s.signal_type IN ('BUY','SELL') AND c.symbol=:symbol "
                    "AND c.timeframe='15m' AND c.provider='alpaca' AND c.is_closed=true "
                    "AND s.strategy_version=:version AND s.generated_at>=:cutoff "
                    "AND s.generated_at>=:expiry ORDER BY s.generated_at,r.decision_id LIMIT 1"
                ),
                {
                    "symbol": symbol,
                    "version": STRATEGY_VERSION,
                    "cutoff": cutoff,
                    "expiry": now - timedelta(minutes=30),
                },
            ).fetchone()
        if row is None:
            return
        account = await self.broker.get_account()
        positions = await self.broker.get_positions()
        orders = await self.broker.get_orders()
        self._validate_account(account)
        self._validate_positions(positions)
        if any(order.status not in REMOTE_STATES for order in orders):
            raise ReconciliationError("unknown_remote_order_state")
        if any(order.symbol == symbol and order.status in OPEN_STATES for order in orders):
            return
        quantity = next(
            (position.quantity for position in positions if position.symbol == symbol), 0
        )
        if row.signal_type == "BUY":
            if quantity != 0:
                return
            reference = Decimal(row.reference_price)
            maximum = min(Decimal(account.equity) * Decimal("0.10"), Decimal(account.cash))
            requested = int(maximum // reference) if reference > 0 else 0
        else:
            if quantity <= 0:
                return
            requested = int(quantity)
        if requested <= 0:
            return
        client_id = self.client_order_id(row.decision_id)
        if not self._reserve(row, symbol, requested, client_id):
            return

        try:
            existing = await self.broker.get_order_by_client_order_id(client_id)
            if existing:
                order = existing
            else:
                self._mark_ambiguous(client_id)
                order = await self.broker.submit_order(
                    symbol=symbol,
                    side=row.signal_type,
                    quantity=requested,
                    client_order_id=client_id,
                )
            self._apply_remote(order)
        except Exception:
            self.execution_ready = False
            logger.error("Paper broker submission uncertain; reconciliation required")

    @staticmethod
    def client_order_id(decision_id: Any) -> str:
        return "agy-" + uuid5(NAMESPACE_OID, str(decision_id)).hex

    def _reserve(self, row: Any, symbol: str, qty: int, client_id: str) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO broker_orders "
                    "(client_order_id,broker_order_id,signal_id,risk_decision_id,"
                    "strategy_version,symbol,timeframe,side,requested_qty,status,filled_qty,"
                    "submitted_at,last_reconciliation_at) VALUES "
                    "(:cid,NULL,:sid,:rid,:version,:symbol,'15m',:side,:qty,'pre_submit',0,"
                    ":now,:now) ON CONFLICT DO NOTHING"
                ),
                {
                    "cid": client_id,
                    "sid": row.signal_id,
                    "rid": row.decision_id,
                    "version": row.strategy_version,
                    "symbol": symbol,
                    "side": row.signal_type,
                    "qty": qty,
                    "now": datetime.now(UTC),
                },
            )
            return bool(result.rowcount)
