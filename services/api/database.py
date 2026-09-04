from typing import Literal

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from services.api.config import Settings

SCHEMA_REVISION = "0008_m3_paper"
DatabaseStatus = Literal["up", "down", "schema_pending"]


def create_database_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        pool_timeout=3,
        connect_args={"connect_timeout": 3, "options": "-c timezone=UTC -c statement_timeout=3000"},
    )


def check_database(engine: Engine) -> DatabaseStatus:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            if connection.scalar(text("SELECT to_regclass('public.alembic_version')")) is None:
                return "schema_pending"
            revisions = connection.scalars(text("SELECT version_num FROM alembic_version")).all()
            return "up" if revisions == [SCHEMA_REVISION] else "schema_pending"
    except SQLAlchemyError:
        # Nunca registrar a excecao de conexao: pode conter credenciais/DSN.
        return "down"
