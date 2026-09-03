"""Candles fechados e log durável de eventos; sem entidades de trading."""

import sqlalchemy as sa
from alembic import op

revision: str = "0002_m1"
down_revision: str | None = "0001_m0"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "candles",
        sa.Column("candle_id", sa.Uuid(), primary_key=True),
        sa.Column("stream_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(24, 4), nullable=False),
        sa.Column("high", sa.Numeric(24, 4), nullable=False),
        sa.Column("low", sa.Numeric(24, 4), nullable=False),
        sa.Column("close", sa.Numeric(24, 4), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("regime", sa.String(16), nullable=False),
        sa.UniqueConstraint("stream_id", "sequence", name="uq_candles_stream_sequence"),
        sa.UniqueConstraint("stream_id", "open_time", name="uq_candles_stream_time"),
        sa.CheckConstraint("sequence > 0 AND volume >= 0", name="ck_candles_sequence_volume"),
        sa.CheckConstraint(
            '"low" > 0 AND "low" <= "open" AND "low" <= "close" AND '
            '"high" >= "open" AND "high" >= "close"',
            name="ck_candles_ohlc",
        ),
        sa.CheckConstraint("close_time = open_time + interval '1 hour'", name="ck_candles_hour"),
        sa.CheckConstraint(
            "regime IN ('uptrend','downtrend','sideways','volatile')", name="ck_candles_regime"
        ),
    )
    op.create_table(
        "system_events",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "candle_id", sa.Uuid(), sa.ForeignKey("candles.candle_id"), nullable=False, unique=True
        ),
        sa.Column("stream_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(8), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.UniqueConstraint("stream_id", "sequence", name="uq_events_stream_sequence"),
    )


def downgrade() -> None:
    op.drop_table("system_events")
    op.drop_table("candles")
