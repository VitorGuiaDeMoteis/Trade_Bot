"""Calendário local da sessão regular US; nenhuma chamada à Trading API."""

from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars
from exchange_calendars.exchange_calendar import ExchangeCalendar


@lru_cache(maxsize=16)
def _calendar(year: int) -> ExchangeCalendar:
    # Janela explícita evita depender do ano de instalação da biblioteca.
    return exchange_calendars.get_calendar(
        "XNYS", start=f"{year - 1}-01-01", end=f"{year + 1}-12-31"
    )


def regular_session(now: datetime) -> tuple[datetime, datetime] | None:
    local = now.astimezone(ZoneInfo("America/New_York"))
    calendar = _calendar(local.year)
    day = local.date().isoformat()
    if not calendar.is_session(day):
        return None
    return (
        calendar.session_open(day).to_pydatetime(),
        calendar.session_close(day).to_pydatetime(),
    )
