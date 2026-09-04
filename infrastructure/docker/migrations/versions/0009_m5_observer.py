"""Append-only observer audit, independent of financial history."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009_m5_observer"
down_revision = "0008_m3_paper"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "observer_analysis_runs",
        sa.Column("analysis_id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(80), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(8), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("output_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("fallback", sa.String(8), nullable=True),
        sa.Column("error_code", sa.String(32), nullable=True),
        sa.Column("latency_ms", sa.BigInteger(), nullable=False),
        sa.Column("sanitized_input", JSONB(none_as_null=True), nullable=True),
        sa.Column("validated_output", JSONB(none_as_null=True), nullable=True),
        sa.CheckConstraint("latency_ms >= 0", name="ck_observer_latency"),
        sa.CheckConstraint(
            "(status = 'OK' AND fallback IS NULL AND error_code IS NULL "
            "AND output_hash IS NOT NULL AND validated_output IS NOT NULL "
            "AND sanitized_input IS NOT NULL AND input_hash IS NOT NULL "
            "AND as_of_utc IS NOT NULL) OR "
            "(status = 'DEGRADED' AND fallback = 'HOLD' AND error_code IS NOT NULL "
            "AND output_hash IS NULL AND validated_output IS NULL)",
            name="ck_observer_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("observer_analysis_runs")
