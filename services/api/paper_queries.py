from uuid import UUID

from sqlalchemy import Connection, func, select

from packages.contracts.paper import (
    PaperFill,
    PaperLink,
    PaperOrder,
    PaperPortfolio,
    PaperPositionResponse,
)
from packages.domain.paper import ZERO, money
from services.api.models import (
    paper_fills,
    paper_marks,
    paper_orders,
    paper_outcomes,
    paper_runs,
    system_controls,
)
from services.api.paper_store import PaperStore


def portfolio(c: Connection, store: PaperStore, limit: int = 50) -> PaperPortfolio:
    control = c.execute(select(system_controls)).mappings().first()
    result = PaperPortfolio(
        provider=store.settings.market_data_provider,
        paused=bool(control and control["paused"]),
        initial_cash=store.config.initial_cash,
        cash=store.config.initial_cash,
        equity=store.config.initial_cash,
        market_value=ZERO,
        realized_pnl=ZERO,
        unrealized_pnl=ZERO,
        total_pnl=ZERO,
        fees=ZERO,
        fee_bps=store.config.fee_bps,
        slippage_bps=store.config.slippage_bps,
    )
    if not control or not control["active_run_id"]:
        return result
    run_id = control["active_run_id"]
    run = c.execute(select(paper_runs).where(paper_runs.c.run_id == run_id)).mappings().one()
    book = store.reconcile(c, run)
    for name in (
        "initial_cash",
        "cash",
        "market_value",
        "equity",
        "realized_pnl",
        "unrealized_pnl",
        "total_pnl",
        "fees",
    ):
        setattr(result, name, getattr(book, name))
    result.run_id, result.status, result.provider = run_id, run["status"], run["provider"]
    result.as_of, result.step = run["as_of"], run["step"]
    result.fee_bps, result.slippage_bps = run["fee_bps"], run["slippage_bps"]
    result.dataset_hash, result.dataset_count = run["dataset_hash"], len(run["dataset"])
    marks = {
        r["symbol"]: r
        for r in c.execute(select(paper_marks).where(paper_marks.c.run_id == run_id)).mappings()
    }
    result.positions = [
        PaperPositionResponse(
            symbol=p.symbol,
            quantity=p.quantity,
            average_price=p.average_price,
            current_price=book.marks[p.symbol],
            market_value=money(book.marks[p.symbol] * p.quantity),
            realized_pnl=p.realized_pnl,
            unrealized_pnl=money((book.marks[p.symbol] - p.average_price) * p.quantity),
            updated_at=marks[p.symbol]["timestamp"],
        )
        for p in sorted(book.positions.values(), key=lambda p: p.symbol)
        if p.quantity
    ]
    result.orders = [
        PaperOrder.model_validate(dict(r))
        for r in c.execute(
            select(paper_orders)
            .where(paper_orders.c.run_id == run_id)
            .order_by(
                paper_orders.c.requested_at.desc(), paper_orders.c.symbol, paper_orders.c.order_id
            )
            .limit(limit)
        ).mappings()
    ]
    result.fills = [
        PaperFill.model_validate(dict(r))
        for r in c.execute(
            select(paper_fills)
            .where(paper_fills.c.order_id.in_([o.order_id for o in result.orders]))
            .order_by(paper_fills.c.filled_at.desc(), paper_fills.c.fill_id)
        ).mappings()
    ]
    result.orders_count = (
        c.scalar(
            select(func.count()).select_from(paper_orders).where(paper_orders.c.run_id == run_id)
        )
        or 0
    )
    result.fills_count = (
        c.scalar(
            select(func.count())
            .select_from(paper_fills.join(paper_orders))
            .where(paper_orders.c.run_id == run_id)
        )
        or 0
    )
    return result


def links(c: Connection, risk_ids: list[UUID]) -> dict[UUID, PaperLink]:
    result = {identity: PaperLink() for identity in risk_ids}
    run_id = c.scalar(select(system_controls.c.active_run_id))
    if not run_id:
        return result
    run = c.execute(select(paper_runs).where(paper_runs.c.run_id == run_id)).mappings().one()
    included = {UUID(item["risk"]["decision_id"]) for item in run["dataset"]}
    for identity in included.intersection(risk_ids):
        result[identity] = PaperLink(
            run_id=run_id, status="WAITING", reason="awaiting_replay_or_next_candle"
        )
    rows = c.execute(
        select(paper_outcomes, paper_orders, paper_fills)
        .select_from(paper_outcomes.outerjoin(paper_orders).outerjoin(paper_fills))
        .where(paper_outcomes.c.run_id == run_id, paper_outcomes.c.risk_decision_id.in_(risk_ids))
    ).mappings()
    for row in rows:
        result[row[paper_outcomes.c.risk_decision_id]] = PaperLink(
            run_id=run_id,
            status=row[paper_outcomes.c.status],
            reason=row[paper_outcomes.c.reason],
            order=PaperOrder.model_validate({col.name: row[col] for col in paper_orders.c})
            if row[paper_orders.c.order_id]
            else None,
            fill=PaperFill.model_validate({col.name: row[col] for col in paper_fills.c})
            if row[paper_fills.c.fill_id]
            else None,
        )
    return result
