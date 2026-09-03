"""Timeframes homologados nesta etapa, sem coerção implícita."""

from datetime import timedelta

SUPPORTED_TIMEFRAMES = {"1h": timedelta(hours=1)}


def timeframe_duration(timeframe: str) -> timedelta:
    try:
        return SUPPORTED_TIMEFRAMES[timeframe]
    except KeyError as error:
        raise ValueError("unsupported_timeframe: somente 1h está validado") from error
