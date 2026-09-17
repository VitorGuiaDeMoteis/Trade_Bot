from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

from packages.domain.market import SimulationSpec
from packages.domain.timeframes import timeframe_duration


class Settings(BaseSettings):
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
    simulator_enabled: bool = True
    paper_initial_cash: Decimal = Field(default=Decimal("10000.00"), ge=0)
    paper_fee_bps: Decimal = Field(default=Decimal("1.0"), ge=0)
    paper_slippage_bps: Decimal = Field(default=Decimal("5.0"), ge=0)
    simulator_seed: int = 42
    simulator_start: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    simulator_interval_seconds: float = Field(default=2.0, ge=0.1, le=3600)

    market_data_provider: Literal["simulator", "alpaca"] = "simulator"
    execution_mode: Literal["local_paper", "alpaca_paper"] = "local_paper"
    alpaca_api_key_id: SecretStr | None = None
    alpaca_api_secret_key: SecretStr | None = None
    alpaca_data_feed: Literal["iex", "sip"] = "iex"
    market_symbols: str = "SPY,AAPL,TSLA"
    market_timeframe: str = "1h"
    backtest_artifacts_dir: str = ".artifacts"

    @field_validator("market_symbols")
    @classmethod
    def normalize_symbols(cls, value: str) -> str:
        import re

        symbols = list(dict.fromkeys(s.strip().upper() for s in value.split(",") if s.strip()))
        if not symbols or any(not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,15}", s) for s in symbols):
            raise ValueError("configuration_error: invalid_market_symbols")
        return ",".join(symbols)

    @model_validator(mode="after")
    def validate_alpaca_credentials(self) -> "Settings":
        SimulationSpec(self.simulator_seed, self.simulator_start)
        timeframe_duration(self.market_timeframe)
        requires_alpaca = (
            self.market_data_provider == "alpaca" or self.execution_mode == "alpaca_paper"
        )
        if requires_alpaca and not (
            self.alpaca_api_key_id
            and self.alpaca_api_key_id.get_secret_value().strip()
            and self.alpaca_api_secret_key
            and self.alpaca_api_secret_key.get_secret_value().strip()
        ):
            raise ValueError("configuration_error: missing_alpaca_credentials")

        validate_database_target(self)

        return self

    @property
    def symbols(self) -> list[str]:
        return (
            ["TEST"] if self.market_data_provider == "simulator" else self.market_symbols.split(",")
        )

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


def validate_database_target(settings: Settings) -> None:
    """Validate the declared database role before an engine can be created.

    The explicit role and exact configured database names are the source of truth.
    We deliberately do not infer safety from a substring such as ``"test"``.
    ``DATABASE_URL`` is not a supported fallback anywhere in this application.
    """

    if settings.runtime_postgres_db == settings.test_postgres_db:
        raise ValueError("configuration_error: runtime and test database names must differ")

    target = (settings.postgres_host, settings.postgres_port, settings.postgres_db)
    runtime_target = (
        settings.runtime_postgres_host,
        settings.runtime_postgres_port,
        settings.runtime_postgres_db,
    )

    if settings.app_env == "test":
        if (
            settings.database_role != "test"
            or settings.postgres_db != settings.test_postgres_db
            or target == runtime_target
        ):
            raise ValueError("REFUSING TO RUN TESTS AGAINST RUNTIME DATABASE")
        return

    if settings.database_role != "runtime" or settings.postgres_db != settings.runtime_postgres_db:
        raise ValueError("configuration_error: runtime cannot connect to test database")
