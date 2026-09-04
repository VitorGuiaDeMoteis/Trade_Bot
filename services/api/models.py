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
