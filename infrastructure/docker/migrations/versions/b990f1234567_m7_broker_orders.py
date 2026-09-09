"""m7_broker_orders

Revision ID: b990f1234567
Revises: ea8afad3f1d3
Create Date: 2026-09-09 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b990f1234567"
down_revision: str | None = "ea8afad3f1d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Remove broker columns from paper_orders
    op.drop_constraint("uq_paper_orders_broker_order_id", "paper_orders", type_="unique")
    op.drop_constraint("uq_paper_orders_client_order_id", "paper_orders", type_="unique")
    op.drop_column("paper_orders", "broker_order_id")
    op.drop_column("paper_orders", "client_order_id")
    op.drop_column("paper_orders", "broker_status")
    op.drop_column("paper_orders", "last_reconciled_at")

    # Create broker_orders
    op.create_table(
        "broker_orders",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("broker_order_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_notional", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("requested_quantity", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column(
            "filled_quantity",
            sa.Numeric(precision=28, scale=10),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"], ["paper_orders.order_id"], name="fk_broker_orders_order_id"
        ),
        sa.PrimaryKeyConstraint("order_id"),
        sa.UniqueConstraint("client_order_id", name="uq_broker_orders_client_id"),
        sa.UniqueConstraint("broker_order_id", name="uq_broker_orders_broker_id"),
    )

    # Create broker_fills
    op.create_table(
        "broker_fills",
        sa.Column("broker_fill_id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("price", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("fee", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"], ["broker_orders.order_id"], name="fk_broker_fills_order_id"
        ),
        sa.PrimaryKeyConstraint("broker_fill_id"),
    )

    # Remove broker_fill_id from paper_fills
    op.drop_constraint("uq_paper_fills_broker_fill_id", "paper_fills", type_="unique")
    op.drop_column("paper_fills", "broker_fill_id")


def downgrade() -> None:
    op.add_column(
        "paper_fills",
        sa.Column("broker_fill_id", sa.VARCHAR(length=64), autoincrement=False, nullable=True),
    )
    op.create_unique_constraint("uq_paper_fills_broker_fill_id", "paper_fills", ["broker_fill_id"])

    op.drop_table("broker_fills")
    op.drop_table("broker_orders")

    op.add_column(
        "paper_orders",
        sa.Column(
            "last_reconciled_at", sa.DateTime(timezone=True), autoincrement=False, nullable=True
        ),
    )
    op.add_column(
        "paper_orders",
        sa.Column("broker_status", sa.VARCHAR(length=32), autoincrement=False, nullable=True),
    )
    op.add_column(
        "paper_orders",
        sa.Column("client_order_id", sa.VARCHAR(length=64), autoincrement=False, nullable=True),
    )
    op.add_column(
        "paper_orders",
        sa.Column("broker_order_id", sa.VARCHAR(length=64), autoincrement=False, nullable=True),
    )
    op.create_unique_constraint(
        "uq_paper_orders_client_order_id", "paper_orders", ["client_order_id"]
    )
    op.create_unique_constraint(
        "uq_paper_orders_broker_order_id", "paper_orders", ["broker_order_id"]
    )
