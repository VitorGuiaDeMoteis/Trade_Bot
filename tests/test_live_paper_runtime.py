import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_market_integration import market as market

from services.api.live_paper_runtime import LivePaperExecutionRuntime

CONTROL_SQL = (
    "INSERT INTO live_paper_control "
    "(control_id, armed, activation_cutoff, updated_at) "
    "VALUES (1, true, :c, :n)"
)
CANDLE_SQL_TEMPLATE = (
    "INSERT INTO candles "
    "(candle_id, stream_id, sequence, symbol, timeframe, provider, open_time, "
    "close_time, open, high, low, close, volume, is_closed) "
    "VALUES (:cid, :sid, :sequence, :sym, :timeframe, 'alpaca', :ot, :ct, "
    "150, 155, 149, 150, 1000, true)"
)
SIGNAL_SQL_TEMPLATE = (
    "INSERT INTO signals "
    "(signal_id, stream_id, candle_id, strategy_version, signal_type, reason, generated_at) "
    "VALUES (:signal_id, :stream_id, :candle_id, 'v2-15m-baseline', :side, 'ok', :now)"
)
DECISION_SQL_TEMPLATE = (
    "INSERT INTO risk_decisions "
    "(decision_id, signal_id, decision, reason, decided_at) "
    "VALUES (:decision_id, :signal_id, 'APPROVED', 'ok', :now)"
)
CANDLE_15M_1_SQL = CANDLE_SQL_TEMPLATE.replace(":sequence", "1").replace(":timeframe", "'15m'")
CANDLE_1M_2_SQL = CANDLE_SQL_TEMPLATE.replace(":sequence", "2").replace(":timeframe", "'1m'")
CANDLE_15M_2_SQL = CANDLE_SQL_TEMPLATE.replace(":sequence", "2").replace(":timeframe", "'15m'")
CANDLE_1M_3_SQL = CANDLE_SQL_TEMPLATE.replace(":sequence", "3").replace(":timeframe", "'1m'")
SIGNAL_BUY_SQL = (
    SIGNAL_SQL_TEMPLATE.replace(":signal_id", ":sid")
    .replace(":stream_id", ":sid_val")
    .replace(":candle_id", ":cid")
    .replace(":side", "'BUY'")
)
SIGNAL_SELL_SQL = SIGNAL_BUY_SQL.replace("'BUY'", "'SELL'")
DECISION_LEGACY_SQL = DECISION_SQL_TEMPLATE.replace(":decision_id", ":did").replace(
    ":signal_id", ":sid"
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required"),
]


class FakeExternalBroker:
    def __init__(self):
        self.orders_submitted = []
        self.positions = []
        self.is_open = True
        self.orders_remote = []
        self.account_cash = Decimal("10000")
        self.account_equity = Decimal("10000")
        self.clock_time = datetime(2026, 9, 8, 18, 30, tzinfo=UTC)
        self.lose_submit_response = False

    async def get_account(self):
        from packages.contracts.broker import BrokerAccount

        return BrokerAccount("USD", self.account_equity, self.account_cash, self.account_cash)

    async def get_positions(self):
        return self.positions

    async def get_orders(self):
        return self.orders_remote

    async def get_order_by_client_order_id(self, client_order_id: str):
        for o in self.orders_remote:
            if o.client_order_id == client_order_id:
                return o
        return None

    async def submit_order(self, symbol: str, side: str, quantity: int, client_order_id: str):
        self.orders_submitted.append((symbol, side, quantity, client_order_id))
        from packages.contracts.broker import BrokerOrder

        o = BrokerOrder(
            client_order_id=client_order_id,
            broker_order_id=str(uuid4()),
            symbol=symbol,
            side=side,
            status="accepted",
            requested_qty=quantity,
            filled_qty=0,
            filled_avg_price=Decimal("0"),
            submitted_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.orders_remote.append(o)
        if self.lose_submit_response:
            raise ConnectionError("simulated response loss")
        return o

    async def get_clock(self):
        from packages.contracts.broker import BrokerClock

        return BrokerClock(is_open=self.is_open, timestamp=self.clock_time)


class FakeProvider:
    def __init__(self, state="connected"):
        self._state = state

    def get_status(self):
        class Status:
            state = self._state

        return Status()


@pytest.fixture
def clean_db(market):
    return market[1]


def seed_eligible(engine, symbol="SPY", side="BUY", price="100", generated=None):
    now = generated or datetime.now(UTC)
    stream = uuid4()
    candle = uuid4()
    signal = uuid4()
    decision = uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO live_paper_control "
                "(control_id,armed,activation_cutoff,updated_at) VALUES (1,true,:cutoff,:now) "
                "ON CONFLICT (control_id) DO UPDATE SET armed=true,activation_cutoff=:cutoff"
            ),
            {"cutoff": now - timedelta(minutes=10), "now": now},
        )
        for sequence, timeframe, duration in ((1, "15m", 15), (2, "1m", 1)):
            candle_id = candle if timeframe == "15m" else uuid4()
            conn.execute(
                text(
                    "INSERT INTO candles "
                    "(candle_id,stream_id,sequence,symbol,timeframe,provider,open_time,"
                    "close_time,open,high,low,close,volume,is_closed) VALUES "
                    "(:id,:stream,:sequence,:symbol,:timeframe,'alpaca',:open,:close,"
                    ":price,:price,:price,:price,1000,true)"
                ),
                {
                    "id": candle_id,
                    "stream": stream,
                    "sequence": sequence,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open": now - timedelta(minutes=duration),
                    "close": now,
                    "price": Decimal(price),
                },
            )
        conn.execute(
            text(
                "INSERT INTO signals "
                "(signal_id,stream_id,candle_id,strategy_version,signal_type,reason,"
                "generated_at) VALUES (:signal,:stream,:candle,'v2-15m-baseline',"
                ":side,'test',:now)"
            ),
            {
                "signal": signal,
                "stream": stream,
                "candle": candle,
                "side": side,
                "now": now,
            },
        )
        conn.execute(
            text(
                "INSERT INTO risk_decisions "
                "(decision_id,signal_id,decision,reason,decided_at) "
                "VALUES (:decision,:signal,'APPROVED','test',:now)"
            ),
            {"decision": decision, "signal": signal, "now": now},
        )
    return decision


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required")
@pytest.mark.anyio
async def test_live_paper_buy_e2e_real_db(clean_db):
    engine = clean_db
    symbol = "AAPL"
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=10)
    sid = uuid4()

    with engine.begin() as conn:
        conn.execute(
            text(CONTROL_SQL),
            {"c": cutoff, "n": now},
        )
        cid_15m = uuid4()
        conn.execute(
            text(CANDLE_15M_1_SQL),
            {
                "cid": cid_15m,
                "sid": sid,
                "sym": symbol,
                "ot": now - timedelta(minutes=15),
                "ct": now,
            },
        )
        conn.execute(
            text(CANDLE_1M_2_SQL),
            {
                "cid": uuid4(),
                "sid": sid,
                "sym": symbol,
                "ot": now - timedelta(minutes=1),
                "ct": now,
            },
        )
        signal_id = uuid4()
        conn.execute(
            text(SIGNAL_BUY_SQL),
            {"sid": signal_id, "sid_val": sid, "cid": cid_15m, "now": now},
        )
        decision_id = uuid4()
        conn.execute(
            text(DECISION_LEGACY_SQL),
            {"did": decision_id, "sid": signal_id, "now": now},
        )

    broker = FakeExternalBroker()
    runtime = LivePaperExecutionRuntime(broker, engine, [symbol], FakeProvider())
    runtime.execution_ready = True

    await runtime._process_pending()

    assert len(broker.orders_submitted) == 1
    sym, side, qty, cid = broker.orders_submitted[0]
    assert sym == symbol
    assert side == "BUY"
    assert qty == 6
    assert len(cid) <= 64

    # Now verify restart partial fill cumulative
    # First, 2 shares filled
    broker.orders_remote[0].status = "partially_filled"
    broker.orders_remote[0].filled_qty = 2
    broker.orders_remote[0].filled_avg_price = Decimal("150")

    await runtime._reconcile()

    with engine.begin() as conn:
        fills = conn.execute(
            text("SELECT qty FROM broker_fills WHERE client_order_id = :cid"), {"cid": cid}
        ).fetchall()
        assert len(fills) == 1
        assert fills[0].qty == 2

    # Second, 5 shares filled total
    broker.orders_remote[0].status = "partially_filled"
    broker.orders_remote[0].filled_qty = 5

    await runtime._reconcile()

    with engine.begin() as conn:
        fills = conn.execute(
            text(
                "SELECT qty FROM broker_fills WHERE client_order_id = :cid ORDER BY filled_at ASC"
            ),
            {"cid": cid},
        ).fetchall()
        assert len(fills) == 2
        assert fills[0].qty == 2
        assert fills[1].qty == 3

    # Ensure cumulative is 5
    assert sum(f.qty for f in fills) == 5

    # Run reconcile again to ensure duplicate doesn't insert more
    await runtime._reconcile()
    with engine.begin() as conn:
        fills = conn.execute(
            text(
                "SELECT qty FROM broker_fills WHERE client_order_id = :cid ORDER BY filled_at ASC"
            ),
            {"cid": cid},
        ).fetchall()
        assert len(fills) == 2

    # Verify order is not duplicated on next loop
    broker.orders_submitted.clear()
    await runtime._process_pending()
    assert len(broker.orders_submitted) == 0


@pytest.mark.anyio
async def test_strategy_risk_to_live_buy_uses_real_postgres(clean_db):
    from packages.domain.market_bar import MarketBar, series_id
    from services.api.market_store import MarketStore
    from services.risk_engine.engine import RiskEngine
    from services.strategy_engine.engine import StrategyV2_15mBaseline

    now = datetime.now(UTC)
    symbol = "TSLA"
    bar = MarketBar(
        "alpaca",
        symbol,
        "15m",
        now - timedelta(minutes=15),
        now,
        Decimal("100"),
        Decimal("111"),
        Decimal("99"),
        Decimal("110"),
        1000,
        True,
    )
    MarketStore(
        clean_db,
        series_id("alpaca", symbol, "15m"),
        strategy=StrategyV2_15mBaseline(),
        risk=RiskEngine(),
    ).append(bar)
    minute = MarketBar(
        "alpaca",
        symbol,
        "1m",
        now - timedelta(minutes=1),
        now,
        Decimal("110"),
        Decimal("110"),
        Decimal("110"),
        Decimal("110"),
        100,
        True,
    )
    MarketStore(clean_db, series_id("alpaca", symbol, "1m")).append(minute)
    with clean_db.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO live_paper_control "
                "(control_id,armed,activation_cutoff,updated_at) VALUES (1,true,:cutoff,:now)"
            ),
            {"cutoff": now - timedelta(minutes=1), "now": now},
        )
    broker = FakeExternalBroker()
    runtime = LivePaperExecutionRuntime(broker, clean_db, [symbol], FakeProvider())
    runtime.execution_ready = True
    await runtime._process_pending()
    assert [(symbol, side, qty) for symbol, side, qty, _ in broker.orders_submitted] == [
        ("TSLA", "BUY", 9)
    ]


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required")
@pytest.mark.anyio
async def test_live_paper_sell_e2e_real_db(clean_db):
    engine = clean_db
    symbol = "AAPL"
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=10)
    sid = uuid4()

    with engine.begin() as conn:
        conn.execute(
            text(CONTROL_SQL),
            {"c": cutoff, "n": now},
        )
        cid_15m = uuid4()
        conn.execute(
            text(CANDLE_15M_1_SQL),
            {
                "cid": cid_15m,
                "sid": sid,
                "sym": symbol,
                "ot": now - timedelta(minutes=15),
                "ct": now,
            },
        )
        conn.execute(
            text(CANDLE_1M_2_SQL),
            {
                "cid": uuid4(),
                "sid": sid,
                "sym": symbol,
                "ot": now - timedelta(minutes=1),
                "ct": now,
            },
        )
        signal_id = uuid4()
        conn.execute(
            text(SIGNAL_SELL_SQL),
            {"sid": signal_id, "sid_val": sid, "cid": cid_15m, "now": now},
        )
        decision_id = uuid4()
        conn.execute(
            text(DECISION_LEGACY_SQL),
            {"did": decision_id, "sid": signal_id, "now": now},
        )

    broker = FakeExternalBroker()
    from packages.contracts.broker import BrokerPosition

    broker.positions = [
        BrokerPosition(
            symbol=symbol,
            quantity=10,
            average_entry_price=Decimal("150"),
            current_price=Decimal("150"),
        )
    ]

    runtime = LivePaperExecutionRuntime(broker, engine, [symbol], FakeProvider())
    runtime.execution_ready = True

    await runtime._process_pending()

    assert len(broker.orders_submitted) == 1
    sym, side, qty, cid = broker.orders_submitted[0]
    assert sym == symbol
    assert side == "SELL"
    assert qty == 10
    broker.orders_remote[0].status = "filled"
    broker.orders_remote[0].filled_qty = 10
    broker.orders_remote[0].filled_avg_price = Decimal("150")
    broker.positions = []
    await runtime._reconcile()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT sum(qty) FROM broker_fills")).scalar_one() == 10
    assert all(position.quantity >= 0 for position in broker.positions)


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required")
@pytest.mark.anyio
async def test_live_paper_no_data_and_stale_and_blocks(clean_db):
    engine = clean_db
    symbol = "AAPL"
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=10)
    sid = uuid4()

    with engine.begin() as conn:
        conn.execute(
            text(CONTROL_SQL),
            {"c": cutoff, "n": now},
        )
        cid_15m = uuid4()
        conn.execute(
            text(CANDLE_15M_1_SQL),
            {
                "cid": cid_15m,
                "sid": sid,
                "sym": symbol,
                "ot": now - timedelta(minutes=15),
                "ct": now,
            },
        )
        signal_id = uuid4()
        conn.execute(
            text(SIGNAL_BUY_SQL),
            {"sid": signal_id, "sid_val": sid, "cid": cid_15m, "now": now},
        )
        decision_id = uuid4()
        conn.execute(
            text(DECISION_LEGACY_SQL),
            {"did": decision_id, "sid": signal_id, "now": now},
        )

    broker = FakeExternalBroker()
    runtime = LivePaperExecutionRuntime(broker, engine, [symbol], FakeProvider())
    runtime.execution_ready = True

    # NO DATA (1m is missing)
    await runtime._process_pending()
    assert len(broker.orders_submitted) == 0

    # STALE DATA (1m is 6 minutes old)
    with engine.begin() as conn:
        conn.execute(
            text(CANDLE_1M_2_SQL),
            {
                "cid": uuid4(),
                "sid": sid,
                "sym": symbol,
                "ot": now - timedelta(minutes=7),
                "ct": now - timedelta(minutes=6),
            },
        )

    await runtime._process_pending()
    assert len(broker.orders_submitted) == 0

    # DEGRADED
    runtime.provider = FakeProvider("degraded")
    await runtime._process_pending()
    assert len(broker.orders_submitted) == 0

    # CLOSED
    runtime.provider = FakeProvider("connected")
    broker.is_open = False
    await runtime._process_pending()
    assert len(broker.orders_submitted) == 0
    broker.is_open = True

    # DISARMED
    with engine.begin() as conn:
        conn.execute(text("UPDATE live_paper_control SET armed = false"))
    await runtime._process_pending()
    assert len(broker.orders_submitted) == 0
    with engine.begin() as conn:
        conn.execute(text("UPDATE live_paper_control SET armed = true"))


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required")
@pytest.mark.anyio
async def test_live_paper_historical_backlog(clean_db):
    engine = clean_db
    symbol = "AAPL"
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=10)
    sid = uuid4()

    with engine.begin() as conn:
        conn.execute(
            text(CONTROL_SQL),
            {"c": cutoff, "n": now},
        )

        # One hundred old decisions prove filtering occurs in SQL, before LIMIT 1.
        for sequence in range(1, 101):
            generated = now - timedelta(hours=2, minutes=sequence)
            old_candle = uuid4()
            conn.execute(
                text(CANDLE_SQL_TEMPLATE),
                {
                    "cid": old_candle,
                    "sid": sid,
                    "sequence": sequence,
                    "sym": symbol,
                    "timeframe": "15m",
                    "ot": generated - timedelta(minutes=15),
                    "ct": generated,
                },
            )
            old_signal = uuid4()
            conn.execute(
                text(SIGNAL_BUY_SQL),
                {
                    "sid": old_signal,
                    "sid_val": sid,
                    "cid": old_candle,
                    "now": generated,
                },
            )
            conn.execute(
                text(DECISION_LEGACY_SQL),
                {"did": uuid4(), "sid": old_signal, "now": generated},
            )

        # 2. Fresh signal
        cid_fresh = uuid4()
        conn.execute(
            text(CANDLE_SQL_TEMPLATE),
            {
                "cid": cid_fresh,
                "sid": sid,
                "sequence": 101,
                "sym": symbol,
                "timeframe": "15m",
                "ot": now - timedelta(minutes=15),
                "ct": now,
            },
        )
        fresh_sig = uuid4()
        conn.execute(
            text(SIGNAL_BUY_SQL),
            {"sid": fresh_sig, "sid_val": sid, "cid": cid_fresh, "now": now},
        )
        conn.execute(
            text(DECISION_LEGACY_SQL),
            {"did": uuid4(), "sid": fresh_sig, "now": now},
        )

        # Fresh 1m candle so it's not stale
        conn.execute(
            text(CANDLE_SQL_TEMPLATE),
            {
                "cid": uuid4(),
                "sid": sid,
                "sequence": 102,
                "sym": symbol,
                "timeframe": "1m",
                "ot": now - timedelta(minutes=1),
                "ct": now,
            },
        )

    broker = FakeExternalBroker()
    runtime = LivePaperExecutionRuntime(broker, engine, [symbol], FakeProvider())
    runtime.execution_ready = True

    await runtime._process_pending()

    # The fresh signal executes immediately; no old decision is reserved or submitted.
    assert len(broker.orders_submitted) == 1
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM broker_orders")).scalar_one() == 1


@pytest.mark.parametrize(
    "state",
    [
        "degraded",
        "stalled",
        "reconnecting",
        "starting",
        "stopped",
        "offline",
        "configuration_error",
    ],
)
@pytest.mark.anyio
async def test_every_unhealthy_provider_state_blocks_submit(clean_db, state):
    seed_eligible(clean_db)
    broker = FakeExternalBroker()
    runtime = LivePaperExecutionRuntime(broker, clean_db, ["SPY"], FakeProvider(state))
    runtime.execution_ready = True
    await runtime._process_pending()
    assert broker.orders_submitted == []


@pytest.mark.anyio
async def test_non_alpaca_candles_cannot_authorize_live_order(clean_db):
    seed_eligible(clean_db)
    with clean_db.begin() as conn:
        conn.execute(text("UPDATE candles SET provider='simulator'"))
    broker = FakeExternalBroker()
    runtime = LivePaperExecutionRuntime(broker, clean_db, ["SPY"], FakeProvider())
    runtime.execution_ready = True
    await runtime._process_pending()
    assert broker.orders_submitted == []


@pytest.mark.anyio
async def test_sizing_ids_and_insufficient_capital(clean_db):
    decision = seed_eligible(clean_db, price="333")
    broker = FakeExternalBroker()
    broker.account_cash = Decimal("1000")
    runtime = LivePaperExecutionRuntime(broker, clean_db, ["SPY"], FakeProvider())
    runtime.execution_ready = True
    await runtime._process_pending()
    assert broker.orders_submitted[0][2] == 3
    first_id = runtime.client_order_id(decision)
    assert first_id == runtime.client_order_id(decision)
    assert first_id != runtime.client_order_id(uuid4())
    assert first_id.startswith("agy-") and len(first_id) <= 64

    # A second eligible symbol has less cash than one whole share: no broker POST.
    seed_eligible(clean_db, "AAPL", price="101")
    broker.account_cash = Decimal("100")
    await runtime._process_symbol("AAPL", datetime.now(UTC), datetime.now(UTC) - timedelta(hours=1))
    assert len(broker.orders_submitted) == 1


@pytest.mark.anyio
async def test_multi_symbol_conflict_is_scoped(clean_db):
    seed_eligible(clean_db, "AAPL")
    seed_eligible(clean_db, "SPY")
    broker = FakeExternalBroker()
    from packages.contracts.broker import BrokerOrder

    broker.orders_remote.append(
        BrokerOrder(
            "external-aapl",
            "remote-aapl",
            "AAPL",
            "BUY",
            "accepted",
            1,
            0,
            Decimal("0"),
            datetime.now(UTC),
            datetime.now(UTC),
        )
    )
    runtime = LivePaperExecutionRuntime(broker, clean_db, ["AAPL", "SPY"], FakeProvider())
    runtime.execution_ready = True
    await runtime._process_pending()
    assert [(symbol, side) for symbol, side, _, _ in broker.orders_submitted] == [("SPY", "BUY")]


@pytest.mark.anyio
async def test_concurrent_cycles_reserve_once(clean_db):
    seed_eligible(clean_db)
    broker = FakeExternalBroker()
    first = LivePaperExecutionRuntime(broker, clean_db, ["SPY"], FakeProvider())
    second = LivePaperExecutionRuntime(broker, clean_db, ["SPY"], FakeProvider())
    first.execution_ready = second.execution_ready = True
    await asyncio.gather(first._process_pending(), second._process_pending())
    assert len(broker.orders_submitted) == 1


@pytest.mark.anyio
async def test_response_loss_restart_recovers_without_second_post(clean_db):
    seed_eligible(clean_db)
    broker = FakeExternalBroker()
    broker.lose_submit_response = True
    first = LivePaperExecutionRuntime(broker, clean_db, ["SPY"], FakeProvider())
    first.execution_ready = True
    await first._process_pending()
    assert len(broker.orders_submitted) == 1 and first.execution_ready is False

    broker.lose_submit_response = False
    restarted = LivePaperExecutionRuntime(broker, clean_db, ["SPY"], FakeProvider())
    await restarted._reconcile()
    restarted.execution_ready = True
    await restarted._process_pending()
    assert len(broker.orders_submitted) == 1
    with clean_db.connect() as conn:
        assert conn.execute(text("SELECT status FROM broker_orders")).scalar_one() == "accepted"


@pytest.mark.anyio
async def test_fill_divergence_rolls_back_and_fails_closed(clean_db):
    seed_eligible(clean_db)
    broker = FakeExternalBroker()
    runtime = LivePaperExecutionRuntime(broker, clean_db, ["SPY"], FakeProvider())
    runtime.execution_ready = True
    await runtime._process_pending()
    remote = broker.orders_remote[0]
    remote.status = "partially_filled"
    remote.filled_qty = 2
    remote.filled_avg_price = Decimal("100")
    await runtime._reconcile()
    remote.filled_qty = 1
    with pytest.raises(RuntimeError, match="local_fill_exceeds_remote"):
        await runtime._reconcile()
    assert runtime.execution_ready is False
    with clean_db.connect() as conn:
        assert conn.execute(text("SELECT sum(qty) FROM broker_fills")).scalar_one() == 2
        assert conn.execute(text("SELECT filled_qty FROM broker_orders")).scalar_one() == 2


@pytest.mark.anyio
async def test_remote_order_identity_divergence_fails_closed(clean_db):
    seed_eligible(clean_db)
    broker = FakeExternalBroker()
    runtime = LivePaperExecutionRuntime(broker, clean_db, ["SPY"], FakeProvider())
    runtime.execution_ready = True
    await runtime._process_pending()
    broker.orders_remote[0].symbol = "AAPL"
    with pytest.raises(RuntimeError, match="remote_order_divergence"):
        await runtime._reconcile()
    assert runtime.execution_ready is False


@pytest.mark.anyio
async def test_invalid_account_or_short_position_fails_reconciliation(clean_db):
    from packages.contracts.broker import BrokerPosition

    broker = FakeExternalBroker()
    runtime = LivePaperExecutionRuntime(broker, clean_db, ["SPY"], FakeProvider())
    broker.account_cash = Decimal("-1")
    with pytest.raises(RuntimeError, match="invalid_remote_account"):
        await runtime._reconcile()
    broker.account_cash = Decimal("10000")
    broker.positions = [BrokerPosition("SPY", -1, Decimal("100"), Decimal("100"))]
    with pytest.raises(RuntimeError, match="invalid_remote_positions"):
        await runtime._reconcile()
    assert runtime.execution_ready is False


@pytest.mark.parametrize(
    "status",
    [
        "pending_new",
        "accepted",
        "new",
        "partially_filled",
        "filled",
        "canceled",
        "rejected",
        "expired",
    ],
)
@pytest.mark.anyio
async def test_all_broker_order_states_reconcile(clean_db, status):
    seed_eligible(clean_db)
    broker = FakeExternalBroker()
    runtime = LivePaperExecutionRuntime(broker, clean_db, ["SPY"], FakeProvider())
    runtime.execution_ready = True
    await runtime._process_pending()
    remote = broker.orders_remote[0]
    remote.status = status
    if status in {"partially_filled", "filled"}:
        remote.filled_qty = remote.requested_qty if status == "filled" else 1
        remote.filled_avg_price = Decimal("100")
    await runtime._reconcile()
    with clean_db.connect() as conn:
        assert conn.execute(text("SELECT status FROM broker_orders")).scalar_one() == status


@pytest.mark.parametrize("timeframe,minutes", [("1m", 1), ("5m", 5), ("15m", 15), ("1h", 60)])
def test_real_postgres_timeframe_duration_constraints(clean_db, timeframe, minutes):
    opened = datetime(2026, 9, 8, 14, 30, tzinfo=UTC)
    values = {
        "id": uuid4(),
        "stream": uuid4(),
        "symbol": "SPY",
        "timeframe": timeframe,
        "open": opened,
        "close": opened + timedelta(minutes=minutes),
    }
    statement = text(
        "INSERT INTO candles (candle_id,stream_id,sequence,symbol,timeframe,provider,"
        "open_time,close_time,open,high,low,close,volume,is_closed) VALUES "
        "(:id,:stream,1,:symbol,:timeframe,'alpaca',:open,:close,100,101,99,100,1,true)"
    )
    with clean_db.begin() as conn:
        conn.execute(statement, values)
    values.update(id=uuid4(), stream=uuid4(), close=opened + timedelta(minutes=minutes + 1))
    values["symbol"] = "AAPL"
    with (
        pytest.raises(IntegrityError, match="ck_candles_timeframe_duration"),
        clean_db.begin() as conn,
    ):
        conn.execute(statement, values)


@pytest.mark.parametrize(
    "status,requested_qty,filled_qty,filled_avg_price",
    [
        ("unknown", 1, 0, None),
        ("accepted", 0, 0, None),
        ("accepted", 1, 1, None),
        ("filled", 2, 1, Decimal("100")),
    ],
)
def test_real_postgres_rejects_invalid_broker_order_state(
    clean_db, status, requested_qty, filled_qty, filled_avg_price
):
    statement = text(
        "INSERT INTO broker_orders "
        "(client_order_id,signal_id,risk_decision_id,strategy_version,symbol,timeframe,"
        "side,requested_qty,status,filled_qty,filled_avg_price,submitted_at,"
        "last_reconciliation_at) VALUES "
        "(:client,:signal,:decision,'v2-15m-baseline','SPY','15m','BUY',:requested,"
        ":status,:filled,:price,:now,:now)"
    )
    with pytest.raises(IntegrityError), clean_db.begin() as conn:
        conn.execute(
            statement,
            {
                "client": "agy-" + uuid4().hex,
                "signal": uuid4(),
                "decision": uuid4(),
                "requested": requested_qty,
                "status": status,
                "filled": filled_qty,
                "price": filled_avg_price,
                "now": datetime.now(UTC),
            },
        )
