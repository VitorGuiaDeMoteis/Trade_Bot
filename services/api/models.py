from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()
candles = Table(
    "candles",
    metadata,
    Column("candle_id", Uuid, primary_key=True),
    Column("stream_id", Uuid, nullable=False),
    Column("sequence", BigInteger, nullable=False),
    Column("symbol", String(16), nullable=False, server_default="TEST"),
    Column("timeframe", String(16), nullable=False, server_default="1h"),
    Column("provider", String(32), nullable=False, server_default="simulator"),
    Column("open_time", DateTime(timezone=True), nullable=False),
    Column("close_time", DateTime(timezone=True), nullable=False),
    Column("open", Numeric(28, 10), nullable=False),
    Column("high", Numeric(28, 10), nullable=False),
    Column("low", Numeric(28, 10), nullable=False),
    Column("close", Numeric(28, 10), nullable=False),
    Column("volume", BigInteger, nullable=False),
    Column("regime", String(16), nullable=True),
    Column("is_closed", Boolean, nullable=False, server_default="true"),
    CheckConstraint("is_closed", name="ck_candles_closed"),
    UniqueConstraint("stream_id", "sequence", name="uq_candles_stream_sequence"),
    UniqueConstraint("provider", "symbol", "timeframe", "open_time", name="uq_candles_market_time"),
    CheckConstraint("sequence > 0 AND volume >= 0", name="ck_candles_sequence_volume"),
    CheckConstraint(
        '"low" > 0 AND "low" <= "open" AND "low" <= "close" AND '
        '"high" >= "open" AND "high" >= "close"',
        name="ck_candles_ohlc",
    ),
    CheckConstraint("close_time = open_time + interval '1 hour'", name="ck_candles_hour"),
    CheckConstraint(
        "regime IN ('uptrend','downtrend','sideways','volatile')", name="ck_candles_regime"
    ),
)
system_events = Table(
    "system_events",
    metadata,
    Column("event_id", Uuid, primary_key=True),
    Column("candle_id", Uuid, ForeignKey("candles.candle_id"), nullable=False, unique=True),
    Column("stream_id", Uuid, nullable=False),
    Column("sequence", BigInteger, nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("schema_version", String(8), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", Uuid, nullable=False),
    UniqueConstraint("stream_id", "sequence", name="uq_events_stream_sequence"),
)

signals = Table(
    "signals",
    metadata,
    Column("signal_id", Uuid, primary_key=True),
    Column("candle_id", Uuid, ForeignKey("candles.candle_id"), nullable=False),
    Column("stream_id", Uuid, nullable=False),
    Column("strategy_version", String(64), nullable=False),
    Column("reason", String(255), nullable=False),
    CheckConstraint("length(trim(reason)) > 0", name="ck_signals_reason"),
    Column("signal_type", String(16), nullable=False),
    Column("generated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("candle_id", "strategy_version", name="uq_signals_candle_strategy"),
    CheckConstraint("signal_type IN ('BUY', 'SELL', 'HOLD')", name="ck_signals_type"),
)

risk_decisions = Table(
    "risk_decisions",
    metadata,
    Column("decision_id", Uuid, primary_key=True),
    Column("signal_id", Uuid, ForeignKey("signals.signal_id"), nullable=False, unique=True),
    Column("decision", String(16), nullable=False),
    Column("reason", String(255), nullable=False),
    Column("decided_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("decision IN ('APPROVED', 'REJECTED')", name="ck_risk_decisions_type"),
)

# Immutable evidence from the pre-validation provider. Never exposed as market data.
legacy_market_archive = Table(
    "legacy_market_archive",
    metadata,
    Column("kind", String(32), primary_key=True),
    Column("record_id", Uuid, primary_key=True),
    Column("payload", JSONB, nullable=False),
    Column("reason", String(128), nullable=False),
)


paper_runs = Table(
    "paper_runs",
    metadata,
    Column("run_id", Uuid, primary_key=True),
    Column("mode", String(16), nullable=False),
    Column("provider", String(32), nullable=False),
    Column("status", String(16), nullable=False),
    Column("initial_cash", Numeric(28, 10), nullable=False),
    Column("cash", Numeric(28, 10), nullable=False),
    Column("fees", Numeric(28, 10), nullable=False),
    Column("realized_pnl", Numeric(28, 10), nullable=False),
    Column("fee_bps", Numeric(16, 6), nullable=False),
    Column("slippage_bps", Numeric(16, 6), nullable=False),
    Column("dataset", JSONB, nullable=False),
    Column("dataset_hash", String(64), nullable=False),
    Column("step", BigInteger, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "mode = 'REPLAY' AND status IN ('READY','RUNNING','COMPLETED')", name="ck_paper_run_mode"
    ),
    CheckConstraint(
        "cash >= 0 AND initial_cash > 0 AND fees >= 0 AND step >= 0", name="ck_paper_run_money"
    ),
    CheckConstraint(
        "fee_bps BETWEEN 0 AND 100 AND slippage_bps BETWEEN 0 AND 100", name="ck_paper_run_costs"
    ),
)


paper_events = Table(
    "paper_events",
    metadata,
    Column("event_id", Uuid, primary_key=True),
    Column("run_id", Uuid, ForeignKey("paper_runs.run_id"), nullable=True),
    Column("event_type", String(64), nullable=False),
    Column("schema_version", String(8), nullable=False),
    Column("correlation_id", Uuid, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSONB, nullable=False),
)

paper_marks = Table(
    "paper_marks",
    metadata,
    Column("run_id", Uuid, ForeignKey("paper_runs.run_id"), primary_key=True),
    Column("symbol", String(16), primary_key=True),
    Column("price", Numeric(28, 10), nullable=False),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    CheckConstraint("price > 0", name="ck_paper_marks_price"),
)

portfolio_snapshots = Table(
    "portfolio_snapshots",
    metadata,
    Column("run_id", Uuid, ForeignKey("paper_runs.run_id"), primary_key=True),
    Column("step", BigInteger, primary_key=True),
    Column("cash", Numeric(28, 10), nullable=False),
    Column("market_value", Numeric(28, 10), nullable=False),
    Column("equity", Numeric(28, 10), nullable=False),
    Column("realized_pnl", Numeric(28, 10), nullable=False),
    Column("unrealized_pnl", Numeric(28, 10), nullable=False),
    Column("total_pnl", Numeric(28, 10), nullable=False),
    Column("fees", Numeric(28, 10), nullable=False),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "equity = cash + market_value AND cash >= 0", name="ck_portfolio_snapshot_equity"
    ),
)

positions = Table(
    "positions",
    metadata,
    Column("run_id", Uuid, ForeignKey("paper_runs.run_id"), primary_key=True),
    Column("symbol", String(16), primary_key=True),
    Column("quantity", BigInteger, nullable=False),
    Column("average_price", Numeric(28, 10), nullable=False),
    Column("realized_pnl", Numeric(28, 10), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("quantity >= 0 AND average_price >= 0", name="ck_positions_long_only"),
)

system_controls = Table(
    "system_controls",
    metadata,
    Column("control_id", BigInteger, primary_key=True),
    Column("active_run_id", Uuid, ForeignKey("paper_runs.run_id"), nullable=True),
    Column("paused", Boolean, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("control_id = 1", name="ck_controls_singleton"),
)

paper_orders = Table(
    "paper_orders",
    metadata,
    Column("order_id", Uuid, primary_key=True),
    Column("run_id", Uuid, ForeignKey("paper_runs.run_id"), nullable=False),
    Column("signal_id", Uuid, ForeignKey("signals.signal_id"), nullable=False),
    Column("risk_decision_id", Uuid, ForeignKey("risk_decisions.decision_id"), nullable=False),
    Column("symbol", String(16), nullable=False),
    Column("side", String(8), nullable=False),
    Column("quantity", BigInteger, nullable=False),
    Column("status", String(16), nullable=False),
    Column("requested_at", DateTime(timezone=True), nullable=False),
    Column("idempotency_key", Uuid, nullable=False, unique=True),
    Column("reason", String(128), nullable=False),
    UniqueConstraint("run_id", "risk_decision_id", name="uq_paper_order_risk"),
    CheckConstraint(
        "side IN ('BUY','SELL') AND status IN ('FILLED','REJECTED') AND quantity >= 0",
        name="ck_paper_orders_state",
    ),
)

paper_fills = Table(
    "paper_fills",
    metadata,
    Column("fill_id", Uuid, primary_key=True),
    Column("order_id", Uuid, ForeignKey("paper_orders.order_id"), nullable=False, unique=True),
    Column("price", Numeric(28, 10), nullable=False),
    Column("reference_price", Numeric(28, 10), nullable=False),
    Column("quantity", BigInteger, nullable=False),
    Column("fee", Numeric(28, 10), nullable=False),
    Column("slippage", Numeric(28, 10), nullable=False),
    Column("realized_pnl", Numeric(28, 10), nullable=False),
    Column("filled_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "price > 0 AND reference_price > 0 AND quantity > 0 AND fee >= 0 AND slippage >= 0",
        name="ck_paper_fills_money",
    ),
)

paper_outcomes = Table(
    "paper_outcomes",
    metadata,
    Column("run_id", Uuid, ForeignKey("paper_runs.run_id"), primary_key=True),
    Column("risk_decision_id", Uuid, ForeignKey("risk_decisions.decision_id"), primary_key=True),
    Column("signal_id", Uuid, ForeignKey("signals.signal_id"), nullable=False),
    Column("execution_candle_id", Uuid, ForeignKey("candles.candle_id"), nullable=False),
    Column("order_id", Uuid, ForeignKey("paper_orders.order_id"), nullable=True),
    Column("status", String(16), nullable=False),
    Column("reason", String(128), nullable=False),
    Column("timestamp", DateTime(timezone=True), nullable=False),
)

PAPER_TABLES = [
    paper_runs,
    paper_events,
    paper_marks,
    portfolio_snapshots,
    positions,
    system_controls,
    paper_orders,
    paper_fills,
    paper_outcomes,
]
