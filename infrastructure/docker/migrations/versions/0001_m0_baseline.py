"""Baseline M0: somente controle de versao Alembic, sem entidades de M1+."""

revision: str = "0001_m0"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
