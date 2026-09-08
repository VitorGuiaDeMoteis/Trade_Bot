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


def get_inspector() -> sa.Inspector:
    bind = op.get_bind()
    return sa.inspect(bind)


def has_table(table_name: str) -> bool:
    return table_name in get_inspector().get_table_names()


def has_constraint(table_name: str, constraint_name: str) -> bool:
    inspector = get_inspector()
    if table_name not in inspector.get_table_names():
        return False
    
    uqs = inspector.get_unique_constraints(table_name)
    if any(uq.get("name") == constraint_name for uq in uqs):
        return True
        
    cks = inspector.get_check_constraints(table_name)
    if any(ck.get("name") == constraint_name for ck in cks):
        return True
        
    return False


def upgrade() -> None:
    # Use explicit type to ensure it's BigInteger in both states without crashing if it's already BigInteger.
    op.alter_column("broker_orders", "requested_qty", type_=sa.BigInteger())
    op.alter_column("broker_orders", "filled_qty", type_=sa.BigInteger())

    if not has_constraint("broker_orders", "uq_broker_order_risk_decision"):
        op.create_unique_constraint(
            "uq_broker_order_risk_decision", "broker_orders", ["risk_decision_id"]
        )

    if not has_constraint("broker_orders", "ck_broker_orders_side"):
        op.create_check_constraint("ck_broker_orders_side", "broker_orders", "side IN ('BUY', 'SELL')")
        
    if not has_constraint("broker_orders", "ck_broker_orders_timeframe"):
        op.create_check_constraint("ck_broker_orders_timeframe", "broker_orders", "timeframe = '15m'")
        
    if not has_constraint("broker_orders", "ck_broker_orders_status"):
        op.create_check_constraint(
            "ck_broker_orders_status",
            "broker_orders",
            "status IN ('pending_new','accepted','new','partially_filled','filled','canceled','rejected','expired','pre_submit','submission_ambiguous','failed_local')",
        )
        
    if not has_constraint("broker_orders", "ck_broker_orders_quantities"):
        op.create_check_constraint(
            "ck_broker_orders_quantities",
            "broker_orders",
            "requested_qty > 0 AND filled_qty >= 0 AND filled_qty <= requested_qty",
        )
        
    if not has_constraint("broker_orders", "ck_broker_orders_fill_price"):
        op.create_check_constraint(
            "ck_broker_orders_fill_price",
            "broker_orders",
            "(filled_qty = 0 AND filled_avg_price IS NULL) OR (filled_qty > 0 AND filled_avg_price IS NOT NULL AND filled_avg_price > 0)",
        )
        
    if not has_constraint("broker_orders", "ck_broker_orders_filled_complete"):
        op.create_check_constraint(
            "ck_broker_orders_filled_complete",
            "broker_orders",
            "status != 'filled' OR filled_qty = requested_qty",
        )

    op.alter_column("broker_fills", "qty", type_=sa.BigInteger())
    if not has_constraint("broker_fills", "ck_broker_fills_values"):
        op.create_check_constraint("ck_broker_fills_values", "broker_fills", "qty > 0 AND price > 0")

    if not has_table("live_paper_control"):
        op.create_table(
            "live_paper_control",
            sa.Column("control_id", sa.BigInteger(), primary_key=True),
            sa.Column("armed", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("armed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("activation_cutoff", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("control_id = 1", name="ck_live_paper_singleton"),
        )
    else:
        op.alter_column("live_paper_control", "control_id", type_=sa.BigInteger())

    if has_constraint("candles", "ck_candles_hour"):
        op.drop_constraint("ck_candles_hour", "candles", type_="check")
        
    if not has_constraint("candles", "ck_candles_timeframe_duration"):
        op.create_check_constraint(
            "ck_candles_timeframe_duration",
            "candles",
            "(timeframe = '1m' AND close_time = open_time + interval '1 minute') OR "
            "(timeframe = '5m' AND close_time = open_time + interval '5 minutes') OR "
            "(timeframe = '15m' AND close_time = open_time + interval '15 minutes') OR "
            "(timeframe = '1h' AND close_time = open_time + interval '1 hour')",
        )


def downgrade() -> None:
    if has_constraint("candles", "ck_candles_timeframe_duration"):
        op.drop_constraint("ck_candles_timeframe_duration", "candles", type_="check")
    if not has_constraint("candles", "ck_candles_hour"):
        op.create_check_constraint(
            "ck_candles_hour", "candles", "close_time = open_time + interval '1 hour'"
        )
        
    if has_table("live_paper_control"):
        op.alter_column("live_paper_control", "control_id", type_=sa.Integer())
        
    if has_constraint("broker_fills", "ck_broker_fills_values"):
        op.drop_constraint("ck_broker_fills_values", "broker_fills", type_="check")
    op.alter_column("broker_fills", "qty", type_=sa.Integer())

    if has_constraint("broker_orders", "ck_broker_orders_filled_complete"):
        op.drop_constraint("ck_broker_orders_filled_complete", "broker_orders", type_="check")
    if has_constraint("broker_orders", "ck_broker_orders_fill_price"):
        op.drop_constraint("ck_broker_orders_fill_price", "broker_orders", type_="check")
    if has_constraint("broker_orders", "ck_broker_orders_quantities"):
        op.drop_constraint("ck_broker_orders_quantities", "broker_orders", type_="check")
    if has_constraint("broker_orders", "ck_broker_orders_status"):
        op.drop_constraint("ck_broker_orders_status", "broker_orders", type_="check")
    if has_constraint("broker_orders", "ck_broker_orders_timeframe"):
        op.drop_constraint("ck_broker_orders_timeframe", "broker_orders", type_="check")
    if has_constraint("broker_orders", "ck_broker_orders_side"):
        op.drop_constraint("ck_broker_orders_side", "broker_orders", type_="check")
    if has_constraint("broker_orders", "uq_broker_order_risk_decision"):
        op.drop_constraint("uq_broker_order_risk_decision", "broker_orders", type_="unique")
        
    op.alter_column("broker_orders", "filled_qty", type_=sa.Integer())
    op.alter_column("broker_orders", "requested_qty", type_=sa.Integer())

