"""The snapshot write must stay inside the NOT NULL contract it depends on.

`AlpacaPaperWorker._save_broker_snapshot` deliberately RAISES
(`invalid_broker_buying_power`) instead of writing NULL when the broker omits
`buying_power`, and AGENT_STATE.md records that as a deliberate decision rather
than an oversight: allowing NULL "would require a migration and would leave the
snapshot row's real-vs-absent status invisible in Mission Control".

That decision is only valid while `broker_portfolio_snapshots.buying_power` is
NOT NULL. The column is created NOT NULL in `db6f20ef0e19` and nothing later
alters it, but that was verified by GREP and recorded only in prose, so the two
sides of the contract could drift apart silently:

- relax the column to nullable and swap `_decimal` for `_optional_decimal` at
  the write site: an absent field publishes a snapshot row with no buying power,
  the exact `dict.get(key, 0)` fail-open class this worker's numerics already
  got wrong once (see test_worker_broker_numeric_fail_closed.py);
- keep the raise but relax the column: the fail-closed path is now unreachable
  for NULL and the documented decision no longer describes the schema.

Neither breakage raises anything at the time it lands, so pin the contract
executable here. The check reads the worker's ACTUAL insert (captured by a stub
engine that never opens a connection) and asserts every column it writes is
declared NOT NULL in the model metadata the migration must match.

Pure unit tests: no Postgres, no broker, no DB mutation, no migration run.
"""

from pathlib import Path

from services.alpaca_paper.worker import AlpacaPaperWorker
from services.api.models import broker_portfolio_snapshots

ACCOUNT = {
    "status": "ACTIVE",
    "cash": "500",
    "equity": "1000",
    "portfolio_value": "1000",
    "buying_power": "4000",
}

POSITION = {
    "symbol": "AAPL",
    "qty": "1",
    "avg_entry_price": "10",
    "current_price": "15",
    "market_value": "15",
    "unrealized_pl": "5",
}

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_MIGRATION = (
    REPO_ROOT
    / "infrastructure/docker/migrations/versions/db6f20ef0e19_m7_broker_portfolio_snapshots.py"
)


class _RecordingConnection:
    """Captures statements so the written row can be inspected without a DB."""

    def __init__(self) -> None:
        self.executed: list = []

    def execute(self, statement, *args, **kwargs):
        self.executed.append((statement, args, kwargs))
        return self


class _StubEngine:
    """Minimal engine: records executes, never touches a database."""

    def __init__(self) -> None:
        self.connection = _RecordingConnection()

    def begin(self):
        return self

    def __enter__(self):
        return self.connection

    def __exit__(self, *exc_info):
        return False


def _written_columns() -> set[str]:
    """Column names the worker actually writes, taken from the real statement."""
    engine = _StubEngine()
    AlpacaPaperWorker(engine, None, None)._save_broker_snapshot(ACCOUNT, [POSITION], "ACTIVE")

    assert engine.connection.executed, "snapshot write did not reach the engine"
    statement = engine.connection.executed[0][0]
    written = set(statement.compile().params)
    # `on_conflict_do_update` compiles the SET clause's `excluded.<col>` refs into
    # params too; keep only names that are real columns of the table.
    return {name for name in written if name in broker_portfolio_snapshots.c}


def test_snapshot_write_covers_buying_power():
    """The field the raise-not-NULL decision is ABOUT must actually be written.

    Without this the two tests below could pass vacuously if the write site
    quietly stopped persisting `buying_power` altogether.
    """
    assert "buying_power" in _written_columns()


def test_every_written_snapshot_column_is_not_null():
    """No column the worker fills may be nullable: it never writes NULL.

    `_decimal` raises on an unsourceable value instead of substituting one, so a
    nullable column here would only ever receive NULL from a future
    `_optional_decimal` conversion -- the fail-open this contract forbids.
    """
    nullable = sorted(
        name for name in _written_columns() if broker_portfolio_snapshots.c[name].nullable
    )

    assert nullable == []


def test_buying_power_is_not_null_in_model_metadata():
    """The NOT NULL assumption the worker's raise decision rests on, executable."""
    assert broker_portfolio_snapshots.c.buying_power.nullable is False


def test_buying_power_created_not_null_in_its_migration():
    """Guard the migration itself, not just the model metadata.

    `services/api/models.py` and the Alembic migration are two separate
    declarations of the same table. The worker relies on the DATABASE constraint,
    so metadata agreeing with a migration that had relaxed it would prove
    nothing. No migration run is needed to read the declaration.
    """
    source = SNAPSHOT_MIGRATION.read_text(encoding="utf-8")

    assert "'buying_power'" in source, "buying_power column vanished from the migration"
    declaration = next(
        line
        for line in source.splitlines()
        if "buying_power" in line and "Column" in line
    )
    assert "nullable=False" in declaration, (
        "buying_power is no longer NOT NULL, but _save_broker_snapshot still RAISES "
        "instead of writing NULL -- the deliberate decision in AGENT_STATE.md no "
        "longer matches the schema"
    )


def test_no_later_migration_rewrites_the_snapshot_table():
    """Only the creating migration may touch `broker_portfolio_snapshots`.

    A future migration could relax `buying_power` without editing the file
    asserted above, so pin that the creating migration is still the only author
    of this table at head.
    """
    versions_dir = SNAPSHOT_MIGRATION.parent
    others = sorted(
        path.name
        for path in versions_dir.glob("*.py")
        if path.name != SNAPSHOT_MIGRATION.name
        and "broker_portfolio_snapshots" in path.read_text(encoding="utf-8")
    )

    assert others == []
