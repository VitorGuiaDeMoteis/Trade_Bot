import pytest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import insert
from services.api.models import (
    broker_fills,
    broker_orders,
    broker_portfolio_snapshots,
    paper_runs,
)
from fastapi.testclient import TestClient

from sqlalchemy import create_engine
from services.api.config import Settings

@pytest.fixture
def override_config(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "alpaca_paper")
    monkeypatch.setenv("ALPACA_API_KEY_ID", "dummy_key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "dummy_secret")

@pytest.fixture
def test_engine():
    settings = Settings()
    return create_engine(settings.database_url)

def insert_baseline(engine):
    from services.api.models import system_controls, candles, signals, risk_decisions
    with engine.begin() as conn:
        run_id = uuid4()
        conn.execute(insert(paper_runs).values(
            run_id=run_id, mode="REPLAY", provider="alpaca", status="RUNNING",
            initial_cash=100000, cash=100000, fees=0, realized_pnl=0,
            fee_bps=0, slippage_bps=0, dataset={}, dataset_hash="h", step=1,
            created_at=datetime.now(UTC)
        ))
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        
        stmt = pg_insert(system_controls).values(
            control_id=1, active_run_id=run_id, paused=False, updated_at=datetime.now(UTC)
        )
        conn.execute(stmt.on_conflict_do_update(
            index_elements=['control_id'],
            set_={'active_run_id': run_id}
        ))
        
        # Insert a signal and risk decision
        c_id = uuid4()
        s_id = uuid4()
        from datetime import timedelta
        open_time = datetime.now(UTC)
        conn.execute(insert(candles).values(
            candle_id=c_id, stream_id=uuid4(), sequence=1, symbol="AAPL", provider="alpaca",
            open_time=open_time, close_time=open_time + timedelta(hours=1),
            open=100, high=100, low=100, close=100, volume=100
        ))
        conn.execute(insert(signals).values(
            signal_id=s_id, candle_id=c_id, stream_id=uuid4(), strategy_version="1",
            reason="test", signal_type="BUY", generated_at=datetime.now(UTC)
        ))
        rd_id = uuid4()
        conn.execute(insert(risk_decisions).values(
            decision_id=rd_id, run_id=run_id, signal_id=s_id, decision="APPROVED",
            reason="ok", decided_at=datetime.now(UTC)
        ))
        return run_id, s_id, rd_id

@pytest.mark.anyio
async def test_broker_portfolio_fee_none(test_engine, override_config, monkeypatch):
    async def mock_stop(self): pass
    monkeypatch.setattr("services.alpaca_paper.worker.AlpacaPaperWorker.start", lambda self: None)
    monkeypatch.setattr("services.alpaca_paper.worker.AlpacaPaperWorker.stop", mock_stop)
    
    from services.api.main import create_app
    app = create_app()
    
    # Insert test data with fee=None
    run_id, s_id, rd_id = insert_baseline(test_engine)
    with test_engine.begin() as conn:
        from sqlalchemy import delete
        from services.api.models import broker_fills, broker_orders, paper_orders, broker_portfolio_snapshots
        conn.execute(delete(broker_fills))
        conn.execute(delete(broker_orders))
        conn.execute(delete(paper_orders))
        conn.execute(delete(broker_portfolio_snapshots))
        
        conn.execute(insert(broker_portfolio_snapshots).values(
            provider="alpaca",
            status="ACTIVE",
            cash=Decimal("100"),
            market_value=Decimal("100"),
            equity=Decimal("200"),
            unrealized_pnl=Decimal("0"),
            buying_power=Decimal("100"),
            last_reconciled_at=datetime.now(UTC)
        ))
        
        order_id = uuid4()
        from services.api.models import paper_orders
        conn.execute(insert(paper_orders).values(
            order_id=order_id, run_id=run_id, signal_id=s_id, risk_decision_id=rd_id,
            symbol="AAPL", side="BUY", quantity=Decimal("1"), filled_quantity=Decimal("1"),
            status="FILLED", requested_at=datetime.now(UTC), idempotency_key=order_id, reason="test"
        ))
        
        conn.execute(insert(broker_orders).values(
            order_id=order_id,
            client_order_id=str(order_id),
            broker_order_id="b_id",
            status="filled",
            filled_quantity=Decimal("1"),
            last_reconciled_at=datetime.now(UTC)
        ))
        
        conn.execute(insert(broker_fills).values(
            broker_fill_id="fill_1",
            order_id=order_id,
            quantity=Decimal("1"),
            price=Decimal("10.0"),
            fee=None, # The crucial part!
            filled_at=datetime.now(UTC)
        ))
        
    with TestClient(app) as client:
        response = client.get("/api/v1/broker/portfolio")
        assert response.status_code == 200
        data = response.json()
        
        # Check that fee is None (null in JSON)
        fill = data["fills"][0]
        assert fill["fee"] is None
        
        # Check that fees, fee_bps, slippage_bps are None
        assert data["fees"] is None
        assert data["fee_bps"] is None
        assert data["slippage_bps"] is None
        
    # Cleanup to avoid breaking other tests
    with test_engine.begin() as conn:
        conn.execute(delete(broker_fills))
        conn.execute(delete(broker_orders))
        conn.execute(delete(paper_orders))
        conn.execute(delete(broker_portfolio_snapshots))


@pytest.mark.anyio
async def test_broker_order_status_is_mapped_local_value_not_uppercased_broker_text(
    test_engine, override_config, monkeypatch
):
    """status must come from paper_orders, never be re-derived from broker text.

    Alpaca emits order states outside _map_status (done_for_day, halted,
    stopped, ...). The route used `.upper()` on the raw broker string, which
    produced a value absent from the contract Literal, and pydantic rejected
    it: ONE unfamiliar order status 500'd the entire portfolio endpoint. The
    mapped paper_orders.status degrades to UNKNOWN and must be what is served.
    """

    async def mock_stop(self) -> None:
        pass

    monkeypatch.setattr("services.alpaca_paper.worker.AlpacaPaperWorker.start", lambda self: None)
    monkeypatch.setattr("services.alpaca_paper.worker.AlpacaPaperWorker.stop", mock_stop)

    from services.api.main import create_app

    app = create_app()
    run_id, s_id, rd_id = insert_baseline(test_engine)

    with test_engine.begin() as conn:
        from sqlalchemy import delete

        from services.api.models import (
            broker_fills,
            broker_orders,
            broker_portfolio_snapshots,
            paper_orders,
        )

        conn.execute(delete(broker_fills))
        conn.execute(delete(broker_orders))
        conn.execute(delete(paper_orders))
        conn.execute(delete(broker_portfolio_snapshots))

        conn.execute(
            insert(broker_portfolio_snapshots).values(
                provider="alpaca",
                status="ACTIVE",
                cash=Decimal("100"),
                market_value=Decimal("0"),
                equity=Decimal("100"),
                unrealized_pnl=Decimal("0"),
                buying_power=Decimal("100"),
                last_reconciled_at=datetime.now(UTC),
            )
        )

        order_id = uuid4()
        # Local mapped status is FILLED (what the executor wrote).
        conn.execute(
            insert(paper_orders).values(
                order_id=order_id,
                run_id=run_id,
                signal_id=s_id,
                risk_decision_id=rd_id,
                symbol="AAPL",
                side="BUY",
                quantity=Decimal("1"),
                filled_quantity=Decimal("1"),
                status="FILLED",
                requested_at=datetime.now(UTC),
                idempotency_key=order_id,
                reason="test",
            )
        )
        # The raw broker string is one _map_status does NOT know: .upper()
        # makes "DONE_FOR_DAY", which is not in the contract Literal.
        conn.execute(
            insert(broker_orders).values(
                order_id=order_id,
                client_order_id=str(order_id),
                broker_order_id="b_id",
                status="done_for_day",
                filled_quantity=Decimal("1"),
                last_reconciled_at=datetime.now(UTC),
            )
        )

    with TestClient(app) as client:
        response = client.get("/api/v1/broker/portfolio")
        # The invariant the bug broke: an unfamiliar broker status must not
        # take down the whole portfolio payload.
        assert response.status_code == 200
        order = response.json()["orders"][0]
        # The mapped local status is authoritative, not an uppercased guess.
        assert order["status"] == "FILLED"
        # The raw broker string is still available, verbatim, in its own field.
        assert order["broker_status"] == "done_for_day"

    with test_engine.begin() as conn:
        conn.execute(delete(broker_fills))
        conn.execute(delete(broker_orders))
        conn.execute(delete(paper_orders))
        conn.execute(delete(broker_portfolio_snapshots))


@pytest.mark.anyio
async def test_broker_order_unacknowledged_reports_null_broker_id_not_empty_string(
    test_engine, override_config, monkeypatch
):
    """A broker id the broker never issued must read as null, never as "".

    broker_orders.broker_order_id is NULL until the broker acknowledges the
    order. The route coerced that NULL to an empty STRING, so the payload
    asserted that a broker id existed and merely had no characters. Every
    `is not None` check on that field -- including the REPLAY-vs-broker
    comparison the observer performs -- read an unacknowledged order as a
    genuinely-issued one. It is the same fabrication as the `quantity: 0`
    coercion: inventing a value hides the inconsistency rather than surfacing
    it.
    """
    async def mock_stop(self) -> None:
        pass

    monkeypatch.setattr("services.alpaca_paper.worker.AlpacaPaperWorker.start", lambda self: None)
    monkeypatch.setattr("services.alpaca_paper.worker.AlpacaPaperWorker.stop", mock_stop)

    from services.api.main import create_app

    app = create_app()
    run_id, s_id, rd_id = insert_baseline(test_engine)

    with test_engine.begin() as conn:
        from sqlalchemy import delete

        from services.api.models import (
            broker_fills,
            broker_orders,
            broker_portfolio_snapshots,
            paper_orders,
        )

        conn.execute(delete(broker_fills))
        conn.execute(delete(broker_orders))
        conn.execute(delete(paper_orders))
        conn.execute(delete(broker_portfolio_snapshots))

        conn.execute(
            insert(broker_portfolio_snapshots).values(
                provider="alpaca",
                status="ACTIVE",
                cash=Decimal("100"),
                market_value=Decimal("0"),
                equity=Decimal("100"),
                unrealized_pnl=Decimal("0"),
                buying_power=Decimal("100"),
                last_reconciled_at=datetime.now(UTC),
            )
        )

        # Accepted by the bot, never acknowledged by the broker: the row is
        # present and the local status is SUBMITTING (the executor's persisted
        # intent, services/alpaca_paper/executor.py:138 -- the last state before
        # the broker replies), but the broker id is NULL.
        order_id = uuid4()
        conn.execute(
            insert(paper_orders).values(
                order_id=order_id,
                run_id=run_id,
                signal_id=s_id,
                risk_decision_id=rd_id,
                symbol="AAPL",
                side="BUY",
                quantity=Decimal("1"),
                filled_quantity=Decimal("0"),
                status="SUBMITTING",
                requested_at=datetime.now(UTC),
                idempotency_key=order_id,
                reason="test",
            )
        )
        conn.execute(
            insert(broker_orders).values(
                order_id=order_id,
                client_order_id=str(order_id),
                # The broker never returned an id.
                broker_order_id=None,
                status="new",
                filled_quantity=Decimal("0"),
                last_reconciled_at=datetime.now(UTC),
            )
        )

    with TestClient(app) as client:
        response = client.get("/api/v1/broker/portfolio")
        assert response.status_code == 200
        order = response.json()["orders"][0]

        # The invariant the bug broke: absent means null, not an empty string.
        assert order["broker_order_id"] is None
        # The local correlation key survives, so the order stays traceable.
        assert order["client_order_id"] == str(order_id)
        # The raw broker status is still surfaced verbatim in its own field.
        assert order["broker_status"] == "new"

    with test_engine.begin() as conn:
        conn.execute(delete(broker_fills))
        conn.execute(delete(broker_orders))
        conn.execute(delete(paper_orders))
        conn.execute(delete(broker_portfolio_snapshots))


@pytest.mark.anyio
async def test_broker_order_requested_at_is_submit_time_not_reconcile_time(
    test_engine, override_config, monkeypatch
):
    """requested_at must be the paper_orders submit time, never the reconcile time.

    broker_orders.last_reconciled_at is bumped on every reconciliation, so using
    it as requested_at made fills appear to precede the order that produced them.
    """
    async def mock_stop(self) -> None:
        pass

    monkeypatch.setattr("services.alpaca_paper.worker.AlpacaPaperWorker.start", lambda self: None)
    monkeypatch.setattr("services.alpaca_paper.worker.AlpacaPaperWorker.stop", mock_stop)

    from services.api.main import create_app

    app = create_app()
    run_id, s_id, rd_id = insert_baseline(test_engine)

    requested_at = datetime.now(UTC) - timedelta(hours=1)
    # Reconciliation happened long afterwards, as it always does on a live cycle.
    reconciled_at = datetime.now(UTC)

    with test_engine.begin() as conn:
        from sqlalchemy import delete

        from services.api.models import (
            broker_fills,
            broker_orders,
            broker_portfolio_snapshots,
            paper_orders,
        )

        conn.execute(delete(broker_fills))
        conn.execute(delete(broker_orders))
        conn.execute(delete(paper_orders))
        conn.execute(delete(broker_portfolio_snapshots))

        conn.execute(
            insert(broker_portfolio_snapshots).values(
                provider="alpaca",
                status="ACTIVE",
                cash=Decimal("100"),
                market_value=Decimal("100"),
                equity=Decimal("200"),
                unrealized_pnl=Decimal("0"),
                buying_power=Decimal("100"),
                last_reconciled_at=reconciled_at,
            )
        )

        order_id = uuid4()
        conn.execute(
            insert(paper_orders).values(
                order_id=order_id,
                run_id=run_id,
                signal_id=s_id,
                risk_decision_id=rd_id,
                symbol="AAPL",
                side="BUY",
                quantity=Decimal("1"),
                filled_quantity=Decimal("1"),
                status="FILLED",
                requested_at=requested_at,
                idempotency_key=order_id,
                reason="test",
            )
        )
        conn.execute(
            insert(broker_orders).values(
                order_id=order_id,
                client_order_id=str(order_id),
                broker_order_id="b_id",
                status="filled",
                filled_quantity=Decimal("1"),
                last_reconciled_at=reconciled_at,
            )
        )
        filled_at = requested_at + timedelta(minutes=5)
        conn.execute(
            insert(broker_fills).values(
                broker_fill_id="fill_req_at",
                order_id=order_id,
                quantity=Decimal("1"),
                price=Decimal("10.0"),
                fee=None,
                filled_at=filled_at,
            )
        )

    with TestClient(app) as client:
        response = client.get("/api/v1/broker/portfolio")
        assert response.status_code == 200
        order = response.json()["orders"][0]
        fill = response.json()["fills"][0]

        # requested_at is the real submit time, not the reconcile time.
        assert order["requested_at"] == requested_at.isoformat().replace("+00:00", "Z")
        # The reconcile timestamp is surfaced in its own field instead of dropped.
        assert order["last_reconciled_at"] is not None
        # The invariant the bug broke: a fill can never precede its own order.
        # Compared as datetimes, not strings: ISO renderings differ by
        # fractional-second presence, which would make a string compare flaky.
        assert datetime.fromisoformat(fill["filled_at"]) > datetime.fromisoformat(
            order["requested_at"]
        )

    with test_engine.begin() as conn:
        conn.execute(delete(broker_fills))
        conn.execute(delete(broker_orders))
        conn.execute(delete(paper_orders))
        conn.execute(delete(broker_portfolio_snapshots))
