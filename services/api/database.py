from pathlib import Path
from typing import Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError

from services.api.config import Settings, validate_database_target

DatabaseStatus = Literal["up", "down", "schema_pending"]
PAPER_RUNTIME_LOCK_ID = 8_271_031_001


def get_alembic_heads() -> tuple[str, ...]:
    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    return tuple(ScriptDirectory.from_config(config).get_heads())


def get_alembic_head() -> str:
    heads = get_alembic_heads()
    if len(heads) != 1:
        rendered = ",".join(heads) if heads else "none"
        raise RuntimeError(f"alembic_expected_single_head: {rendered}")
    return heads[0]


# Compatibility for callers that display the expected revision. This value is
# derived from Alembic's graph; creating a migration never requires editing it.
SCHEMA_REVISION = get_alembic_head()


def create_database_engine(settings: Settings) -> Engine:
    validate_database_target(settings)
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        pool_timeout=3,
        connect_args={"connect_timeout": 3, "options": "-c timezone=UTC -c statement_timeout=3000"},
    )

    expected_database = settings.postgres_db

    @event.listens_for(engine, "connect")
    def verify_connected_database(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        # This is the first statement on every new DBAPI connection. No caller
        # SQL can run until PostgreSQL confirms the selected database name.
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            actual_database = cursor.fetchone()[0]
        if actual_database != expected_database:
            raise RuntimeError(
                f"database_target_mismatch: expected={expected_database} actual={actual_database}"
            )

    return engine


def check_database(engine: Engine) -> DatabaseStatus:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            if connection.scalar(text("SELECT to_regclass('public.alembic_version')")) is None:
                return "schema_pending"
            revisions = connection.scalars(text("SELECT version_num FROM alembic_version")).all()
            return "up" if revisions == [get_alembic_head()] else "schema_pending"
    except (SQLAlchemyError, RuntimeError):
        # Nunca registrar a excecao de conexao: pode conter credenciais/DSN.
        return "down"


def acquire_paper_runtime_lock(engine: Engine) -> Connection:
    connection = engine.connect()
    try:
        acquired = connection.scalar(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": PAPER_RUNTIME_LOCK_ID},
        )
        if not acquired:
            raise RuntimeError("alpaca_paper_runtime_already_active")
        return connection
    except Exception:
        connection.close()
        raise


def release_paper_runtime_lock(connection: Connection) -> None:
    try:
        connection.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": PAPER_RUNTIME_LOCK_ID},
        )
    finally:
        connection.close()


def paper_runtime_lock_available(engine: Engine) -> bool:
    try:
        connection = acquire_paper_runtime_lock(engine)
    except RuntimeError:
        return False
    release_paper_runtime_lock(connection)
    return True
