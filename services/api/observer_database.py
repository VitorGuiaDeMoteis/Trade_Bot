"""Trusted host connection settings; no market-data or execution configuration."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, Engine, create_engine


class ObserverDatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )
    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "trading_bot_dev"
    postgres_user: str = "trading_bot_dev"
    postgres_password: SecretStr


def create_observer_database() -> Engine:
    settings = ObserverDatabaseSettings()
    url = URL.create(
        "postgresql+psycopg",
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        username=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        pool_timeout=3,
        connect_args={"connect_timeout": 3, "options": "-c timezone=UTC -c statement_timeout=3000"},
    )
