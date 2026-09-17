"""Trusted host connection settings; no market-data or execution configuration."""

from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, Engine

from services.api.config import validate_database_target
from services.api.database import create_database_engine


class ObserverDatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )
    app_env: Literal["local", "test"] = "local"
    database_role: Literal["runtime", "test"] = "runtime"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "trading_bot_dev"
    postgres_user: str = "trading_bot_dev"
    postgres_password: SecretStr
    runtime_postgres_host: str = "127.0.0.1"
    runtime_postgres_port: int = Field(default=5432, ge=1, le=65535)
    runtime_postgres_db: str = "trading_bot_dev"
    test_postgres_db: str = "trading_bot_test"

    @model_validator(mode="after")
    def validate_target(self) -> "ObserverDatabaseSettings":
        validate_database_target(self)  # type: ignore[arg-type]
        return self

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
        )


def create_observer_database() -> Engine:
    settings = ObserverDatabaseSettings()
    return create_database_engine(settings)  # type: ignore[arg-type]
