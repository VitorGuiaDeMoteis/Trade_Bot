"""Explicit, bounded Market Data smoke test. No trading endpoint or persistence."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from services.api.config import Settings
from services.market_data.alpaca_provider import AlpacaMarketDataProvider
from services.market_data.calendar import regular_session
from services.market_data.errors import ProviderError


class SmokeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    run_alpaca_smoke_test: bool = False


async def main() -> int:
    if not SmokeSettings().run_alpaca_smoke_test:
        print("SKIPPED: RUN_ALPACA_SMOKE_TEST=1 required")
        return 0
    try:
        settings = Settings(market_data_provider="alpaca")
    except ValidationError:
        print("configuration_error: check local settings and Alpaca Market Data credentials")
        return 1
    assert settings.alpaca_api_key_id and settings.alpaca_api_secret_key
    provider = AlpacaMarketDataProvider(
        api_key=settings.alpaca_api_key_id.get_secret_value(),
        secret_key=settings.alpaca_api_secret_key.get_secret_value(),
        feed=settings.alpaca_data_feed,
        symbols=["SPY"],
        timeframe="1h",
    )
    try:
        async with asyncio.timeout(45):
            bars = await provider.get_historical_candles("SPY", "1h", limit=5)
            if not bars:
                print("FAILED: no closed SPY history returned")
                return 1
            for bar in bars:
                assert bar.provider == "alpaca" and bar.symbol == "SPY" and bar.is_closed
                assert bar.open_time.utcoffset() == bar.close_time.utcoffset() == timedelta(0)
                assert bar.close_time <= datetime.now(UTC)
                assert all(
                    isinstance(p, Decimal) and p.is_finite() and p > 0
                    for p in (bar.open, bar.high, bar.low, bar.close)
                )
            print(f"PASS: {len(bars)} closed SPY 1h bars, provider=alpaca, UTC, Decimal")
            now = datetime.now(UTC)
            session = regular_session(now)
            if session is None or not session[0] <= now < session[1]:
                print("market_closed / streaming not validated (regular session)")
                return 0
            socket = await provider.socket_factory()
            try:
                await provider.handshake(socket)
                print("PASS: WebSocket authentication and subscription acknowledged")
                print("Hourly streaming not validated by this bounded handshake test")
            finally:
                await socket.close()
        return 0
    except (ProviderError, TimeoutError) as error:
        code = error.code if isinstance(error, ProviderError) else "timeout"
        print(f"FAILED: {code}")
        return 1
    except Exception:
        print("FAILED: unexpected smoke test failure (details withheld to protect credentials)")
        return 1
    finally:
        await provider.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
