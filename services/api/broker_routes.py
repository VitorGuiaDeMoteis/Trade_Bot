from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import func, select

from packages.contracts.paper import PaperFill, PaperOrder, PaperPortfolio, PaperPositionResponse
from services.api.models import (
    broker_fills,
    broker_orders,
    broker_portfolio_snapshots,
    broker_positions,
    paper_orders,
    system_controls,
)

router = APIRouter(prefix="/api/v1/broker", tags=["broker paper"])


@router.get("/portfolio", response_model=PaperPortfolio)
async def get_broker_portfolio(request: Request, response: Response) -> PaperPortfolio:
    config = request.app.state.configuration
    if getattr(config, "execution_mode", "") != "alpaca_paper":
        raise HTTPException(400, "not_in_alpaca_paper_mode")

    engine = request.app.state.database

    with engine.begin() as conn:
        control = conn.execute(select(system_controls)).mappings().first()
        paused = control["paused"] if control else False
        run_id = control["active_run_id"] if control else None

        # Read snapshot
        snapshot = (
            conn.execute(
                select(broker_portfolio_snapshots).where(
                    broker_portfolio_snapshots.c.provider == "alpaca"
                )
            )
            .mappings()
            .first()
        )

        if not snapshot:
            raise HTTPException(404, "No broker snapshot available")

        # Read positions
        b_positions = (
            conn.execute(select(broker_positions).where(broker_positions.c.provider == "alpaca"))
            .mappings()
            .all()
        )

        positions = []
        for p in b_positions:
            positions.append(
                PaperPositionResponse(
                    symbol=p["symbol"],
                    quantity=Decimal(str(p["quantity"])),
                    average_price=Decimal(str(p["average_price"])),
                    current_price=Decimal(str(p["current_price"])),
                    market_value=Decimal(str(p["market_value"])),
                    realized_pnl=None,
                    unrealized_pnl=Decimal(str(p["unrealized_pnl"])),
                    updated_at=p["updated_at"],
                )
            )

        # Read orders
        j = broker_orders.join(paper_orders, broker_orders.c.order_id == paper_orders.c.order_id)
        b_orders = (
            conn.execute(
                select(
                    broker_orders,
                    paper_orders.c.symbol,
                    paper_orders.c.side,
                    paper_orders.c.run_id,
                    paper_orders.c.signal_id,
                    paper_orders.c.risk_decision_id,
                    paper_orders.c.requested_at,
                    # paper_orders.status is the executor's _map_status output
                    # and the only value CHECK-constrained to the contract
                    # Literal (ck_paper_orders_state_m7). broker_orders.status
                    # holds the raw broker text. Label it so it does not
                    # collide with broker_orders.status in the mapping row.
                    paper_orders.c.status.label("paper_status"),
                )
                .select_from(j)
                # Ordered by SUBMIT time, not by reconcile time: last_reconciled_at
                # is bumped on every cycle for an order still working at the broker,
                # so sorting by it floats stale open orders above genuinely newer
                # ones and the list contradicts the requested_at it reports.
                # The symbol/order_id tiebreakers keep the LIMIT 100 window stable.
                .order_by(
                    paper_orders.c.requested_at.desc(),
                    paper_orders.c.symbol,
                    paper_orders.c.order_id,
                )
                .limit(100)
            )
            .mappings()
            .all()
        )

        orders = []
        for o in b_orders:
            orders.append(
                PaperOrder(
                    order_id=o["order_id"],
                    run_id=o["run_id"],
                    signal_id=o["signal_id"],
                    risk_decision_id=o["risk_decision_id"],
                    symbol=o["symbol"],
                    side=o["side"],
                    # A notional order stores requested_quantity as NULL by
                    # design: the share count is not knowable until the broker
                    # fills it. Coercing that NULL to 0 published a fabricated
                    # "quantity: 0" beside a real filled_quantity, so a
                    # consumer sizing from `quantity` saw a trade that traded
                    # nothing. Fall back to the only real share count the row
                    # has. Never invent a zero: a missing requested_quantity on
                    # a non-notional row is a real inconsistency, and reporting
                    # 0 would hide it rather than surface it.
                    quantity=Decimal(
                        str(
                            o["requested_quantity"]
                            if o["requested_quantity"] is not None
                            else o["filled_quantity"]
                        )
                    ),
                    filled_quantity=Decimal(str(o["filled_quantity"])),
                    # Report the mapped status the executor already wrote to
                    # paper_orders, never a status re-derived from the raw
                    # broker string. `.upper()` was only accidentally correct
                    # for the ten statuses in _map_status: Alpaca also emits
                    # states outside that map (e.g. "done_for_day", "halted",
                    # "suspended", "stopped"), and .upper() turned those into
                    # strings absent from the contract Literal, so pydantic
                    # rejected the row and the whole portfolio endpoint 500'd
                    # on a single unfamiliar order status. _map_status degrades
                    # to UNKNOWN instead, which is exactly the fallback wanted.
                    # paper_orders.status is NOT NULL and CHECK-constrained, so
                    # this can never be empty.
                    status=o["paper_status"],
                    # requested_at is the real submission time from paper_orders.
                    # broker_orders.last_reconciled_at is bumped on every
                    # reconciliation, so it must never be reported as the
                    # request time: a fill could otherwise appear to precede
                    # the order that produced it.
                    requested_at=o["requested_at"],
                    last_reconciled_at=o["last_reconciled_at"],
                    idempotency_key=uuid5(NAMESPACE_URL, o["client_order_id"]),
                    reason="Broker Order",
                    client_order_id=o["client_order_id"],
                    # broker_orders.broker_order_id is NULL until the broker
                    # acknowledges the order, and NULL legitimately persists for
                    # a submission the broker never accepted. `or ""` turned
                    # that absence into an empty STRING: the payload claimed a
                    # broker id existed and merely had no characters, so a
                    # consumer testing `is not None` read an unacknowledged
                    # order as a real one. That is the same fabrication as the
                    # `quantity: 0` coercion above -- inventing a value hides
                    # the inconsistency instead of surfacing it -- and it also
                    # disagreed with the REPLAY constructor, which reports this
                    # same field as the contract default None. Pass the NULL
                    # through so both constructors mean the same thing.
                    broker_order_id=o["broker_order_id"],
                    # The raw broker string stays raw, in its own field.
                    broker_status=o["status"],
                )
            )

        b_fills = (
            conn.execute(select(broker_fills).order_by(broker_fills.c.filled_at.desc()).limit(100))
            .mappings()
            .all()
        )
        fills = []
        for f in b_fills:
            fills.append(
                PaperFill(
                    fill_id=uuid5(NAMESPACE_URL, f["broker_fill_id"]),
                    order_id=f["order_id"],
                    broker_fill_id=f["broker_fill_id"],
                    price=Decimal(str(f["price"])),
                    reference_price=Decimal(str(f["price"])),
                    quantity=Decimal(str(f["quantity"])),
                    fee=Decimal(str(f["fee"])) if f["fee"] is not None else None,
                    slippage=None,  # Unavailable
                    realized_pnl=None,
                    filled_at=f["filled_at"],
                )
            )

        # The lists above are capped at 100 rows, so report the real totals with
        # COUNT over the same join instead of len(b_orders)/len(b_fills).
        orders_count = (
            conn.scalar(select(func.count()).select_from(j)) or 0
        )
        fills_count = (
            conn.scalar(select(func.count()).select_from(broker_fills)) or 0
        )

        # The snapshot status is the single source of truth for whether the last
        # reconciliation cycle succeeded. `_enter_degraded` flips the stored status
        # to DEGRADED when a cycle fails, so this is the persisted latch, not a
        # recomputation of current health.
        degraded = snapshot["status"] in ("DEGRADED", "STALE")

        return PaperPortfolio(
            mode="ALPACA_PAPER",
            run_id=run_id,
            status=snapshot["status"],
            provider="alpaca",
            paused=paused,
            as_of=datetime.now(UTC),
            initial_cash=Decimal(str(snapshot["cash"])),
            cash=Decimal(str(snapshot["cash"])),
            market_value=Decimal(str(snapshot["market_value"])),
            equity=Decimal(str(snapshot["equity"])),
            total_pnl=None,
            unrealized_pnl=Decimal(str(snapshot["unrealized_pnl"])),
            realized_pnl=None,
            fees=None,  # Explicit None if unavailable
            fee_bps=None,
            slippage_bps=None,
            positions=positions,
            orders=orders,
            fills=fills,
            orders_count=orders_count,
            fills_count=fills_count,
            last_reconciled_at=snapshot["last_reconciled_at"],
            # `reconciled` defaults to True in the contract, and this route
            # never passed it, so a DEGRADED/STALE snapshot published
            # "reconciled": true beside "degraded": true -- a book whose last
            # reconciliation FAILED asserting it was verified. Derive both
            # flags from the single snapshot status so they can never disagree.
            degraded=degraded,
            reconciled=not degraded,
        )
