"""Timeframes homologados nesta etapa, sem coerção implícita."""

from datetime import timedelta

SUPPORTED_TIMEFRAMES = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
}


def timeframe_duration(timeframe: str) -> timedelta:
    try:
        return SUPPORTED_TIMEFRAMES[timeframe]
    except KeyError as error:
        raise ValueError(f"unsupported_timeframe: {timeframe} não é um timeframe válido") from error
