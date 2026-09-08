"""live_paper_broker_audit

Revision ID: 002ad6ee70d8
Revises: 0010_m5_real_image
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002ad6ee70d8"
down_revision: str | Sequence[str] | None = "0010_m5_real_image"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "broker_orders",
        sa.Column("client_order_id", sa.String(64), primary_key=True),
        sa.Column("broker_order_id", sa.String(64), nullable=True),
        sa.Column("signal_id", sa.Uuid(), nullable=False),
        sa.Column("risk_decision_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_version", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("timeframe", sa.String(16), nullable=False),
        sa.Column("side", sa.String(16), nullable=False),
        sa.Column("requested_qty", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("filled_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("filled_avg_price", sa.Numeric(20, 10), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reconciliation_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "broker_fills",
        sa.Column("fill_id", sa.String(64), primary_key=True),
        sa.Column("client_order_id", sa.String(64), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(20, 10), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_order_id"], ["broker_orders.client_order_id"]),
    )


def downgrade() -> None:
    op.drop_table("broker_fills")
    op.drop_table("broker_orders")
