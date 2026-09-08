from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from packages.domain.market_bar import MarketBar
from packages.domain.timeframes import timeframe_duration

NY_TZ = ZoneInfo("America/New_York")


class TimeframeAggregator:
    def __init__(
        self, 
        target_timeframes: list[str], 
        on_candle_closed: Callable[[MarketBar], None],
        on_gap: Callable[[str, str], None] | None = None,
        on_recovery: Callable[[str, str], None] | None = None,
    ) -> None:
        self.emit_1m = "1m" in target_timeframes
        self.target_timeframes = [tf for tf in target_timeframes if tf != "1m"]
        self.on_candle_closed = on_candle_closed
        self.on_gap = on_gap
        self.on_recovery = on_recovery
        self.partials: dict[tuple[str, str], MarketBar] = {}
        self.minutes_received: dict[tuple[str, str], set[datetime]] = {}
        self.expected_minutes = {"5m": 5, "15m": 15, "1h": 60}
        self.durations = {tf: timeframe_duration(tf) for tf in self.target_timeframes}
        self.latest_received: dict[str, datetime] = {}

    def _align_time(self, dt: datetime, tf: str) -> datetime | None:
        ny_time = dt.astimezone(NY_TZ)
        # Regular session starts at 09:30 NY, ends at 16:00
        if ny_time.hour < 9 or (ny_time.hour == 9 and ny_time.minute < 30) or ny_time.hour >= 16:
            return None

        minutes_since_930 = (ny_time.hour - 9) * 60 + ny_time.minute - 30

        # 15:30-16:00 is not a full 1h candle (only 30m)
        if tf == "1h" and minutes_since_930 >= 360:
            return None

        if tf == "1h":
            aligned_minutes = (minutes_since_930 // 60) * 60
        elif tf == "15m":
            aligned_minutes = (minutes_since_930 // 15) * 15
        elif tf == "5m":
            aligned_minutes = (minutes_since_930 // 5) * 5
        else:
            aligned_minutes = minutes_since_930

        aligned_ny = ny_time.replace(hour=9, minute=30, second=0, microsecond=0)
        from datetime import timedelta

        aligned_ny += timedelta(minutes=aligned_minutes)
        return aligned_ny.astimezone(dt.tzinfo or ZoneInfo("UTC"))

    def process(self, bar: MarketBar) -> None:
        if bar.timeframe != "1m":
            self.on_candle_closed(bar)
            return

        # Operational candles are regular-session only, including emitted 1m bars.
        if self._align_time(bar.open_time, "1m") is None:
            return

        latest = self.latest_received.get(bar.symbol)
        if latest and bar.open_time < latest:
            return
        if latest == bar.open_time:
            return

        self.latest_received[bar.symbol] = bar.open_time
        if self.emit_1m:
            self.on_candle_closed(bar)

        for tf in self.target_timeframes:
            aligned_open = self._align_time(bar.open_time, tf)
            if not aligned_open:
                continue
            aligned_close = aligned_open + self.durations[tf]

            key = (bar.symbol, tf)

            # If moving to a new bucket, close the old incomplete one
            if key in self.partials:
                current_partial = self.partials[key]
                if current_partial.open_time != aligned_open:
                    expected = self.expected_minutes[tf]
                    actual = len(self.minutes_received.get(key, set()))
                    if actual < expected:
                        import logging

                        logging.getLogger("trading_bot.market").error(
                            f"aggregator_gap_detected_{actual}_of_{expected}_for_{key}"
                        )
                        if self.on_gap:
                            self.on_gap(bar.symbol, tf)
                        self.partials.pop(key)
                        self.minutes_received.pop(key, None)
                    else:
                        self.on_candle_closed(replace(current_partial, is_closed=True))
                        if self.on_recovery:
                            self.on_recovery(bar.symbol, tf)
                        self.partials.pop(key)
                        self.minutes_received.pop(key, None)

            if key not in self.partials:
                self.partials[key] = MarketBar(
                    provider=bar.provider,
                    symbol=bar.symbol,
                    timeframe=tf,
                    open_time=aligned_open,
                    close_time=aligned_close,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    is_closed=False,
                )
                self.minutes_received[key] = {bar.open_time}
            else:
                if bar.open_time in self.minutes_received.get(key, set()):
                    continue  # Duplicate minute

                partial = self.partials[key]
                self.partials[key] = replace(
                    partial,
                    high=max(partial.high, bar.high),
                    low=min(partial.low, bar.low),
                    close=bar.close,
                    volume=partial.volume + bar.volume,
                )
                self.minutes_received[key].add(bar.open_time)

            if len(self.minutes_received[key]) == self.expected_minutes[tf]:
                partial = self.partials[key]
                self.on_candle_closed(replace(partial, is_closed=True))
                if self.on_recovery:
                    self.on_recovery(bar.symbol, tf)
                self.partials.pop(key)
                self.minutes_received.pop(key)
