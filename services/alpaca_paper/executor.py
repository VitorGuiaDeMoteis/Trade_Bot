import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert

from packages.domain.paper import AlpacaSubmitResult
from packages.domain.risk import RiskDecision
from services.alpaca_paper.adapter import AlpacaPaperAdapter
from services.api.models import broker_orders, paper_orders

logger = logging.getLogger("trading_bot.alpaca_paper")


class AlpacaPaperExecutor:
    """Fronteira separada do PaperExecutor local."""

    def __init__(self, adapter: AlpacaPaperAdapter) -> None:
        self.adapter = adapter

    async def _handle_timeout_or_disconnect(
        self, engine: Engine, order_id: UUID, client_order_id: str
    ) -> None:
        """
        Idempotência: Se houver timeout, nunca reenviar cegamente.
        Pesquisar por client_order_id.
        """
        remote_order = await self.adapter.get_order_by_client_id(client_order_id)
        if remote_order:
            # Reconciliar estado
            broker_status = remote_order.get("status")
            status = self._map_status(broker_status)

            with engine.begin() as connection:
                connection.execute(
                    broker_orders.update()
                    .where(broker_orders.c.order_id == order_id)
                    .values(
                        broker_order_id=remote_order.get("id"),
                        status=broker_status,
                        filled_quantity=Decimal(str(remote_order.get("filled_qty", "0"))),
                        last_reconciled_at=datetime.now(UTC),
                    )
                )
                connection.execute(
                    paper_orders.update()
                    .where(paper_orders.c.order_id == order_id)
                    .values(status=status)
                )
        else:
            # Prova de ausência da ordem original -> podemos reenviar
            # Após timeout, cancelar localmente só quando o broker provar ausência (404).
            with engine.begin() as connection:
                connection.execute(
                    paper_orders.update()
                    .where(paper_orders.c.order_id == order_id)
                    .values(status="CANCELED", reason="not_found_on_broker")
                )
                connection.execute(
                    broker_orders.update()
                    .where(broker_orders.c.order_id == order_id)
                    .values(status="CANCELED", last_reconciled_at=datetime.now(UTC))
                )

    def _map_status(self, alpaca_status: str | None) -> str:
        if not alpaca_status:
            return "UNKNOWN"
        mapping = {
            "new": "NEW",
            "accepted": "ACCEPTED",
            "pending_new": "PENDING_NEW",
            "partially_filled": "PARTIALLY_FILLED",
            "filled": "FILLED",
            "pending_cancel": "PENDING_CANCEL",
            "canceled": "CANCELED",
            "rejected": "REJECTED",
            "expired": "EXPIRED",
            "replaced": "REPLACED",
        }
        return mapping.get(alpaca_status.lower(), "UNKNOWN")

    async def submit(
        self,
        engine: Engine,
        run_id: UUID,
        signal_id: UUID,
        risk: RiskDecision,
        symbol: str,
        side: Literal["BUY", "SELL"],
        quantity: Decimal,
        order_id: UUID,
        requested_at: datetime,
        notional: Decimal | None = None,
    ) -> AlpacaSubmitResult:

        client_order_id = f"m7_{order_id.hex}"

        # 1. Persistir intent: SUBMITTING
        try:
            with engine.begin() as connection:
                connection.execute(
                    paper_orders.insert().values(
                        order_id=order_id,
                        run_id=run_id,
                        signal_id=signal_id,
                        risk_decision_id=risk.decision_id,
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        filled_quantity=0,
                        status="SUBMITTING",
                        requested_at=requested_at,
                        idempotency_key=order_id,
                        reason="intent_persisted",
                    )
                )

                connection.execute(
                    broker_orders.insert().values(
                        order_id=order_id,
                        client_order_id=client_order_id,
                        status="submitting",
                        requested_notional=notional,
                        requested_quantity=quantity if notional is None else None,
                        filled_quantity=Decimal("0"),
                        last_reconciled_at=datetime.now(UTC),
                    )
                )
        except Exception as e:
            if "IntegrityError" in type(e).__name__ or "UniqueViolation" in type(e).__name__:
                logger.warning(f"Duplicate intent locally blocked for order {order_id}")
                # IDEMPOTENCY: Do not POST. Reconcile existing intent instead.
                await self.reconcile_order(engine, order_id)
                # Fetch recovered status
                with engine.begin() as conn:
                    row = conn.execute(
                        select(paper_orders.c.status).where(paper_orders.c.order_id == order_id)
                    ).first()
                status = row.status if row else "UNKNOWN"
                return AlpacaSubmitResult(status, "duplicate_intent", quantity)
            raise

        # 2. Chamar Alpaca
        try:
            alpaca_order = await self.adapter.submit_order(
                symbol=symbol,
                qty=quantity if notional is None else None,
                side=side.lower(),
                client_order_id=client_order_id,
                notional=str(notional) if notional else None,
            )
        except Exception as e:
            logger.error(f"Error submitting order: {e}")
            from services.alpaca_paper.adapter import AlpacaPaperError

            if isinstance(e, AlpacaPaperError) and e.status_code in (403, 422):
                with engine.begin() as connection:
                    connection.execute(
                        paper_orders.update()
                        .where(paper_orders.c.order_id == order_id)
                        .values(status="REJECTED", reason=str(e))
                    )
                    connection.execute(
                        broker_orders.update()
                        .where(broker_orders.c.order_id == order_id)
                        .values(
                            status="rejected",
                            last_reconciled_at=datetime.now(UTC),
                        )
                    )
                return AlpacaSubmitResult("REJECTED", "broker_rejected", quantity)

            await self._handle_timeout_or_disconnect(engine, order_id, client_order_id)
            return AlpacaSubmitResult("REJECTED", "network_error", quantity)

        # 3. Atualizar status
        broker_status = alpaca_order.get("status")
        status = self._map_status(broker_status)
        broker_order_id = alpaca_order.get("id")

        with engine.begin() as connection:
            connection.execute(
                broker_orders.update()
                .where(broker_orders.c.order_id == order_id)
                .values(
                    broker_order_id=broker_order_id,
                    status=broker_status,
                    last_reconciled_at=datetime.now(UTC),
                )
            )

            connection.execute(
                paper_orders.update()
                .where(paper_orders.c.order_id == order_id)
                .values(status=status)
            )

        if status in ("PARTIALLY_FILLED", "FILLED"):
            await self.reconcile_order(engine, order_id)

        return AlpacaSubmitResult(status, "submitted_to_broker", quantity)

    async def reconcile_order(self, engine: Engine, order_id: UUID) -> None:
        from services.api.models import broker_fills

        with engine.begin() as connection:
            row = connection.execute(
                select(broker_orders.c.broker_order_id, broker_orders.c.client_order_id).where(
                    broker_orders.c.order_id == order_id
                )
            ).first()

        if not row:
            return

        broker_order_id = row.broker_order_id
        client_order_id = row.client_order_id

        if broker_order_id:
            remote_order = await self.adapter.get_order_by_id(broker_order_id)
        else:
            remote_order = await self.adapter.get_order_by_client_id(client_order_id)

        if not remote_order:
            with engine.begin() as connection:
                connection.execute(
                    paper_orders.update()
                    .where(paper_orders.c.order_id == order_id)
                    .values(status="CANCELED", reason="not_found_on_broker")
                )
                connection.execute(
                    broker_orders.update()
                    .where(broker_orders.c.order_id == order_id)
                    .values(status="canceled", last_reconciled_at=datetime.now(UTC))
                )
            return

        new_status = remote_order.get("status")
        filled_qty = Decimal(str(remote_order.get("filled_qty", "0")))
        actual_broker_id = remote_order.get("id")

        mapped_status = self._map_status(new_status)

        with engine.begin() as connection:
            connection.execute(
                broker_orders.update()
                .where(broker_orders.c.order_id == order_id)
                .values(
                    broker_order_id=actual_broker_id,
                    status=new_status,
                    filled_quantity=filled_qty,
                    last_reconciled_at=datetime.now(UTC),
                )
            )

            connection.execute(
                paper_orders.update()
                .where(paper_orders.c.order_id == order_id)
                .values(status=mapped_status, filled_quantity=filled_qty)
            )

        # "se filled_qty > 0, os fills precisam ser persistidos independentemente do status final"
        if filled_qty > 0 and actual_broker_id:
            activities = await self.adapter.get_fills(actual_broker_id)
            for act in activities:
                fill_id = act.get("id")
                qty = Decimal(str(act.get("qty", "0")))
                price = Decimal(str(act.get("price", "0")))

                # Fetch transaction_time and fee properly
                t_time = act.get("transaction_time")
                if t_time:
                    try:
                        filled_at_val = datetime.fromisoformat(t_time.replace("Z", "+00:00"))
                    except Exception:
                        filled_at_val = datetime.now(UTC)
                else:
                    filled_at_val = datetime.now(UTC)

                fee_val = None
                # Represent unavailable as None explicitly
                # If they provide fee, parse it
                if "fee" in act and act["fee"] is not None:
                    try:
                        fee_val = Decimal(str(act["fee"]))
                    except (ArithmeticError, TypeError, ValueError):
                        pass

                with engine.begin() as connection:
                    connection.execute(
                        insert(broker_fills)
                        .values(
                            broker_fill_id=fill_id,
                            order_id=order_id,
                            quantity=qty,
                            price=price,
                            fee=fee_val,
                            filled_at=filled_at_val,
                        )
                        .on_conflict_do_nothing(index_elements=["broker_fill_id"])
                    )
