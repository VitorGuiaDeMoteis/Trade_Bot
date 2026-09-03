from datetime import UTC, datetime
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

from packages.domain.market import SimulationSpec


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "test"] = "local"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "trading_bot_dev"
    postgres_user: str = "trading_bot_dev"
    postgres_password: SecretStr
    simulator_enabled: bool = True
    simulator_seed: int = 42
    simulator_start: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    simulator_interval_seconds: float = Field(default=2.0, ge=0.1, le=3600)

    market_data_provider: str = "simulator"
    alpaca_api_key_id: str | None = None
    alpaca_api_secret_key: SecretStr | None = None
    alpaca_data_feed: str = "iex"
    market_symbols: str = "SPY,AAPL,TSLA"
    market_timeframe: str = "1h"

    @model_validator(mode="after")
    def validate_simulator(self) -> "Settings":
        SimulationSpec(self.simulator_seed, self.simulator_start)
        return self

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
