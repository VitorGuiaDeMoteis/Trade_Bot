"""Read-only PostgreSQL snapshot; freezes candles without touching the live paper run."""

from sqlalchemy import Engine, select, text

from packages.contracts.market import CandleResponse
from packages.domain.backtest import Dataset
from packages.domain.market import Candle
from services.api.models import candles


def freeze(engine: Engine, provider: str, symbols: tuple[str, ...]) -> Dataset:
    if provider not in {"alpaca", "simulator"} or not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("backtest_invalid_series_selection")
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as c, c.begin():
        c.execute(text("SET TRANSACTION READ ONLY"))
        rows = c.execute(
            select(candles).where(
                candles.c.provider == provider,
                candles.c.symbol.in_(symbols),
                candles.c.timeframe == "1h",
            )
        ).mappings()
        dataset = Dataset(
            tuple(Candle(**CandleResponse.model_validate(dict(r)).model_dump()) for r in rows)
        )
        if {bar.symbol for bar in dataset.candles} != set(symbols):
            raise ValueError("backtest_requested_series_missing")
        return dataset
