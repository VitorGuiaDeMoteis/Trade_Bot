from sqlalchemy import (
    BigInteger,
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

metadata = MetaData()
candles = Table(
    "candles",
    metadata,
    Column("candle_id", Uuid, primary_key=True),
    Column("stream_id", Uuid, nullable=False),
    Column("sequence", BigInteger, nullable=False),
    Column("open_time", DateTime(timezone=True), nullable=False),
    Column("close_time", DateTime(timezone=True), nullable=False),
    Column("open", Numeric(24, 4), nullable=False),
    Column("high", Numeric(24, 4), nullable=False),
    Column("low", Numeric(24, 4), nullable=False),
    Column("close", Numeric(24, 4), nullable=False),
    Column("volume", BigInteger, nullable=False),
    Column("regime", String(16), nullable=False),
    UniqueConstraint("stream_id", "sequence", name="uq_candles_stream_sequence"),
    UniqueConstraint("stream_id", "open_time", name="uq_candles_stream_time"),
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
