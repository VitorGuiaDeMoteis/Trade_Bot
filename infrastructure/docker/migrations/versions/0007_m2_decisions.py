"""Persist signal explanations without replaying strategy or risk."""

import sqlalchemy as sa
from alembic import op

revision = "0007_m2_decisions"
down_revision = "0006_m15_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("reason", sa.String(255), nullable=True))
    # Explain only signals whose version AND stored candle prove the baseline rule.
    # Unknown/mismatching legacy decisions retain their identities and honest provenance.
    op.execute("""
        UPDATE signals s SET reason = CASE
          WHEN s.strategy_version = 'v1-deterministic'
            AND s.signal_type = 'BUY' AND c.close > c.open
            THEN 'Fechamento acima da abertura.'
          WHEN s.strategy_version = 'v1-deterministic'
            AND s.signal_type = 'SELL' AND c.close < c.open
            THEN 'Fechamento abaixo da abertura.'
          WHEN s.strategy_version = 'v1-deterministic'
            AND s.signal_type = 'HOLD' AND c.close = c.open
            THEN 'Abertura e fechamento equivalentes. Sem ação.'
          ELSE 'Justificativa histórica não registrada; regra não comprovada pelo backfill.'
        END FROM candles c WHERE c.candle_id = s.candle_id
    """)
    op.alter_column("signals", "reason", nullable=False)
    op.create_check_constraint("ck_signals_reason", "signals", "length(trim(reason)) > 0")


def downgrade() -> None:
    op.drop_constraint("ck_signals_reason", "signals", type_="check")
    op.drop_column("signals", "reason")
