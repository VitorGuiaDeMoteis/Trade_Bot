from alembic import context

from services.api.config import get_settings
from services.api.database import create_database_engine
from services.api.models import metadata

target_metadata = metadata


def run_migrations() -> None:
    if context.is_offline_mode():
        context.configure(
            url=get_settings().database_url,
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_database_engine(get_settings())
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


run_migrations()
