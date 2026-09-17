"""add run_id to risk_decisions

Revision ID: 888888888888
Revises: cbec58d3efff
Create Date: 2026-09-15 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '888888888888'
down_revision: Union[str, None] = 'cbec58d3efff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('risk_decisions', sa.Column('run_id', sa.Uuid(), nullable=True))
    op.create_foreign_key('fk_risk_decisions_run_id', 'risk_decisions', 'paper_runs', ['run_id'], ['run_id'])


def downgrade() -> None:
    # op.drop_constraint('fk_risk_decisions_run_id', 'risk_decisions', type_='foreignkey')
    op.drop_column('risk_decisions', 'run_id')
