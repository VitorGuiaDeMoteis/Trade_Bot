"""Quarantine unverified Alpaca rows; closed bars and precise hourly prices."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006_m15_integrity"
down_revision: str | Sequence[str] | None = "d4ae1863048a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    ("candles", "candle_id", "provider = 'alpaca'"),
    (
        "system_events",
        "event_id",
        "candle_id IN (SELECT candle_id FROM candles WHERE provider='alpaca')",
    ),
    (
        "signals",
        "signal_id",
        "candle_id IN (SELECT candle_id FROM candles WHERE provider='alpaca')",
    ),
    (
        "risk_decisions",
        "decision_id",
        "signal_id IN (SELECT signal_id FROM signals WHERE candle_id IN "
        "(SELECT candle_id FROM candles WHERE provider='alpaca'))",
    ),
)


def upgrade() -> None:
    op.execute(
        "LOCK TABLE candles, system_events, signals, risk_decisions IN ACCESS EXCLUSIVE MODE"
    )
    op.create_table(
        "legacy_market_archive",
        sa.Column("kind", sa.String(32), primary_key=True),
        sa.Column("record_id", sa.Uuid(), primary_key=True),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("reason", sa.String(128), nullable=False),
    )
    # Historical and minute-origin rows cannot be reliably distinguished.
    # Preserve every column and dependent row in this same atomic transaction.
    for table, key, predicate in TABLES:
        op.execute(
            f"INSERT INTO legacy_market_archive SELECT '{table}', {key}, to_jsonb(t), "
            f"'pre_m15_unverified_timeframe' FROM {table} t WHERE {predicate}"
        )
    for table, _, predicate in reversed(TABLES):
        op.execute(f"DELETE FROM {table} WHERE {predicate}")
    op.add_column(
        "candles", sa.Column("is_closed", sa.Boolean(), nullable=False, server_default="true")
    )
    op.create_check_constraint("ck_candles_closed", "candles", "is_closed")
    op.alter_column("candles", "regime", existing_type=sa.String(16), nullable=True)
    for field in ("open", "high", "low", "close"):
        op.alter_column("candles", field, type_=sa.Numeric(28, 10), existing_type=sa.Numeric(24, 4))


def downgrade() -> None:
    # Fail closed: never merge unverified legacy data into a newly validated series.
    count = op.get_bind().scalar(sa.text("SELECT count(*) FROM candles WHERE provider='alpaca'"))
    if count:
        raise RuntimeError("Export validated Alpaca data before downgrading M1.5.")
    op.drop_constraint("ck_candles_closed", "candles", type_="check")
    op.drop_column("candles", "is_closed")
    op.alter_column("candles", "regime", existing_type=sa.String(16), nullable=False)
    for field in ("open", "high", "low", "close"):
        op.alter_column("candles", field, type_=sa.Numeric(24, 4), existing_type=sa.Numeric(28, 10))
    for table, _, _ in TABLES:
        op.execute(
            f"INSERT INTO {table} SELECT (jsonb_populate_record(NULL::{table}, payload)).* "
            f"FROM legacy_market_archive WHERE kind='{table}'"
        )
    op.drop_table("legacy_market_archive")
