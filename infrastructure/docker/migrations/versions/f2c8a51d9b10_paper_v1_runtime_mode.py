"""Distinguish the Alpaca Paper runtime from local replay runs.

Revision ID: f2c8a51d9b10
Revises: 863267844740
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f2c8a51d9b10"
down_revision: str | Sequence[str] | None = "863267844740"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_paper_run_mode", "paper_runs", type_="check")
    op.create_check_constraint(
        "ck_paper_run_mode",
        "paper_runs",
        "mode IN ('REPLAY','ALPACA_PAPER') AND status IN ('READY','RUNNING','COMPLETED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_paper_run_mode", "paper_runs", type_="check")
    op.create_check_constraint(
        "ck_paper_run_mode",
        "paper_runs",
        "mode = 'REPLAY' AND status IN ('READY','RUNNING','COMPLETED')",
    )
