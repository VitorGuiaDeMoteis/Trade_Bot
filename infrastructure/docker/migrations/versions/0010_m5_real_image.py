"""Preserve the real runtime image identity separately from model weights."""

import sqlalchemy as sa
from alembic import op

revision = "0010_m5_real_image"
down_revision = "0009_m5_observer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("observer_analysis_runs", sa.Column("image_digest", sa.String(71), nullable=True))


def downgrade() -> None:
    op.drop_column("observer_analysis_runs", "image_digest")
