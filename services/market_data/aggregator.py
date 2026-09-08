from collections.abc import Callable
from datetime import datetime

from packages.domain.market_bar import MarketBar
from packages.domain.timeframes import timeframe_duration


class TimeframeAggregator:
    def __init__(
        self, target_timeframes: list[str], on_candle_closed: Callable[[MarketBar], None]
    ) -> None:
        self.target_timeframes = target_timeframes
        self.on_candle_closed = on_candle_closed
        self.partials: dict[str, MarketBar] = {}
        self.durations = {tf: timeframe_duration(tf) for tf in target_timeframes}

    def _align_time(self, dt: datetime, tf: str) -> datetime:
        if tf == "1h":
            return dt.replace(minute=0, second=0, microsecond=0)
        elif tf == "15m":
            return dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)
        elif tf == "5m":
            return dt.replace(minute=(dt.minute // 5) * 5, second=0, microsecond=0)
        elif tf == "1m":
            return dt.replace(second=0, microsecond=0)
        return dt

    def process(self, bar: MarketBar) -> None:
        if bar.timeframe != "1m":
            self.on_candle_closed(bar)
            return

        for tf in self.target_timeframes:
            aligned_open = self._align_time(bar.open_time, tf)
            aligned_close = aligned_open + self.durations[tf]

            if tf in self.partials:
                partial = self.partials[tf]
                if partial.open_time != aligned_open:
                    from dataclasses import replace
                    self.on_candle_closed(replace(partial, is_closed=True))
                    self.partials.pop(tf)

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
            else:
                from dataclasses import replace
                partial = self.partials[tf]
                self.partials[tf] = replace(
                    partial,
                    high=max(partial.high, bar.high),
                    low=min(partial.low, bar.low),
                    close=bar.close,
                    volume=partial.volume + bar.volume,
                )

            if bar.close_time >= aligned_close:
                from dataclasses import replace
                partial = self.partials[tf]
                self.on_candle_closed(replace(partial, is_closed=True))
                self.partials.pop(tf)
