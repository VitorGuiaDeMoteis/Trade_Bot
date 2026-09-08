"""live_paper_broker_hardening

Revision ID: 002bd0000000
Revises: 002ad6ee70d8
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002bd0000000"
down_revision: str | Sequence[str] | None = "002ad6ee70d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("broker_orders", "requested_qty", type_=sa.BigInteger())
    op.alter_column("broker_orders", "filled_qty", type_=sa.BigInteger())
    op.create_unique_constraint(
        "uq_broker_order_risk_decision", "broker_orders", ["risk_decision_id"]
    )
    op.create_check_constraint("ck_broker_orders_side", "broker_orders", "side IN ('BUY', 'SELL')")
    op.create_check_constraint("ck_broker_orders_timeframe", "broker_orders", "timeframe = '15m'")
    op.create_check_constraint(
        "ck_broker_orders_status",
        "broker_orders",
        "status IN ('pending_new','accepted','new','partially_filled','filled','canceled','rejected','expired','pre_submit','submission_ambiguous','failed_local')",
    )
    op.create_check_constraint(
        "ck_broker_orders_quantities",
        "broker_orders",
        "requested_qty > 0 AND filled_qty >= 0 AND filled_qty <= requested_qty",
    )
    op.create_check_constraint(
        "ck_broker_orders_fill_price",
        "broker_orders",
        "(filled_qty = 0 AND filled_avg_price IS NULL) OR (filled_qty > 0 AND filled_avg_price IS NOT NULL AND filled_avg_price > 0)",
    )
    op.create_check_constraint(
        "ck_broker_orders_filled_complete",
        "broker_orders",
        "status != 'filled' OR filled_qty = requested_qty",
    )

    op.alter_column("broker_fills", "qty", type_=sa.BigInteger())
    op.create_check_constraint("ck_broker_fills_values", "broker_fills", "qty > 0 AND price > 0")

    op.create_table(
        "live_paper_control",
        sa.Column("control_id", sa.BigInteger(), primary_key=True),
        sa.Column("armed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("armed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activation_cutoff", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("control_id = 1", name="ck_live_paper_singleton"),
    )

    op.drop_constraint("ck_candles_hour", "candles", type_="check")
    op.create_check_constraint(
        "ck_candles_timeframe_duration",
        "candles",
        "(timeframe = '1m' AND close_time = open_time + interval '1 minute') OR "
        "(timeframe = '5m' AND close_time = open_time + interval '5 minutes') OR "
        "(timeframe = '15m' AND close_time = open_time + interval '15 minutes') OR "
        "(timeframe = '1h' AND close_time = open_time + interval '1 hour')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_candles_timeframe_duration", "candles", type_="check")
    op.create_check_constraint(
        "ck_candles_hour", "candles", "close_time = open_time + interval '1 hour'"
    )
    op.drop_table("live_paper_control")
    op.drop_constraint("ck_broker_fills_values", "broker_fills", type_="check")
    op.alter_column("broker_fills", "qty", type_=sa.Integer())

    op.drop_constraint("ck_broker_orders_filled_complete", "broker_orders", type_="check")
    op.drop_constraint("ck_broker_orders_fill_price", "broker_orders", type_="check")
    op.drop_constraint("ck_broker_orders_quantities", "broker_orders", type_="check")
    op.drop_constraint("ck_broker_orders_status", "broker_orders", type_="check")
    op.drop_constraint("ck_broker_orders_timeframe", "broker_orders", type_="check")
    op.drop_constraint("ck_broker_orders_side", "broker_orders", type_="check")
    op.drop_constraint("uq_broker_order_risk_decision", "broker_orders", type_="unique")
    op.alter_column("broker_orders", "filled_qty", type_=sa.Integer())
    op.alter_column("broker_orders", "requested_qty", type_=sa.Integer())
