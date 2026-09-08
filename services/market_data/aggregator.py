from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo
from dataclasses import replace

from packages.domain.market_bar import MarketBar
from packages.domain.timeframes import timeframe_duration

NY_TZ = ZoneInfo("America/New_York")


class TimeframeAggregator:
    def __init__(
        self, target_timeframes: list[str], on_candle_closed: Callable[[MarketBar], None]
    ) -> None:
        self.emit_1m = "1m" in target_timeframes
        self.target_timeframes = [tf for tf in target_timeframes if tf != "1m"]
        self.on_candle_closed = on_candle_closed
        self.partials: dict[str, MarketBar] = {}
        self.minutes_received: dict[str, set[datetime]] = {}
        self.expected_minutes = {"5m": 5, "15m": 15, "1h": 60}
        self.durations = {tf: timeframe_duration(tf) for tf in self.target_timeframes}
        self.latest_received: datetime | None = None

    def _align_time(self, dt: datetime, tf: str) -> datetime:
        ny_time = dt.astimezone(NY_TZ)
        # Regular session starts at 09:30 NY
        if ny_time.hour < 9 or (ny_time.hour == 9 and ny_time.minute < 30) or ny_time.hour >= 16:
            # Extended hours or invalid - for this v0.1 we might just align strictly
            pass

        minutes_since_930 = (ny_time.hour - 9) * 60 + ny_time.minute - 30
        if minutes_since_930 < 0:
            minutes_since_930 = 0  # Fallback for pre-market, though unsupported

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

        if self.emit_1m:
            self.on_candle_closed(bar)

        # Reject late bars
        if self.latest_received and bar.open_time < self.latest_received:
            return

        self.latest_received = max(self.latest_received or bar.open_time, bar.open_time)

        for tf in self.target_timeframes:
            aligned_open = self._align_time(bar.open_time, tf)
            aligned_close = aligned_open + self.durations[tf]

            bucket_key = f"{bar.symbol}_{tf}_{aligned_open.isoformat()}"

            # If moving to a new bucket, discard the old incomplete one
            if tf in self.partials:
                current_partial = self.partials[tf]
                if current_partial.open_time != aligned_open:
                    self.partials.pop(tf)
                    self.minutes_received.pop(tf, None)

            if tf not in self.partials:
                self.partials[tf] = MarketBar(
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
                self.minutes_received[tf] = {bar.open_time}
            else:
                if bar.open_time in self.minutes_received.get(tf, set()):
                    continue  # Duplicate minute

                partial = self.partials[tf]
                self.partials[tf] = replace(
                    partial,
                    high=max(partial.high, bar.high),
                    low=min(partial.low, bar.low),
                    close=bar.close,
                    volume=partial.volume + bar.volume,
                )
                self.minutes_received[tf].add(bar.open_time)

            if len(self.minutes_received[tf]) == self.expected_minutes[tf]:
                partial = self.partials[tf]
                self.on_candle_closed(replace(partial, is_closed=True))
                self.partials.pop(tf)
                self.minutes_received.pop(tf)
