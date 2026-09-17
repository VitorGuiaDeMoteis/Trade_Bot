"""fix_ck_paper_orders_state_m7

Revision ID: 863267844740
Revises: 9621f2ecf977
Create Date: 2026-09-16 10:59:17.382

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '863267844740'
down_revision: Union[str, None] = '9621f2ecf977'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old constraint
    op.drop_constraint('ck_paper_orders_state_m7', 'paper_orders', type_='check')
    
    # Add new constraint supporting notional orders (quantity = 0 implies notional, so filled_quantity can exceed quantity)
    op.create_check_constraint(
        'ck_paper_orders_state_m7',
        'paper_orders',
        "side IN ('BUY','SELL') AND status IN ('SUBMITTING', 'NEW', 'ACCEPTED', 'PENDING_NEW', 'PARTIALLY_FILLED', 'FILLED', 'PENDING_CANCEL', 'CANCELED', 'REJECTED', 'EXPIRED', 'REPLACED', 'UNKNOWN') AND quantity >= 0 AND filled_quantity >= 0 AND ((quantity > 0 AND filled_quantity <= quantity) OR (quantity = 0))"
    )

def downgrade() -> None:
    op.drop_constraint('ck_paper_orders_state_m7', 'paper_orders', type_='check')
    op.create_check_constraint(
        'ck_paper_orders_state_m7',
        'paper_orders',
        "side IN ('BUY','SELL') AND status IN ('SUBMITTING', 'NEW', 'ACCEPTED', 'PENDING_NEW', 'PARTIALLY_FILLED', 'FILLED', 'PENDING_CANCEL', 'CANCELED', 'REJECTED', 'EXPIRED', 'REPLACED', 'UNKNOWN') AND quantity >= 0 AND filled_quantity >= 0 AND filled_quantity <= quantity"
    )
