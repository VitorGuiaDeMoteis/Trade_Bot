import sys

with open('services/market_data/aggregator.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace(
    "self.target_timeframes = target_timeframes",
    "self.emit_1m = \"1m\" in target_timeframes\n        self.target_timeframes = [tf for tf in target_timeframes if tf != \"1m\"]"
)
text = text.replace(
    "self.durations = {tf: timeframe_duration(tf) for tf in target_timeframes}",
    "self.durations = {tf: timeframe_duration(tf) for tf in self.target_timeframes}"
)

# And now add 1m emission.
target = '''    def process(self, bar: MarketBar) -> None:
        if bar.timeframe != "1m":
            self.on_candle_closed(bar)
            return

        # Reject late bars'''

replacement = '''    def process(self, bar: MarketBar) -> None:
        if bar.timeframe != "1m":
            self.on_candle_closed(bar)
            return

        if self.emit_1m:
            self.on_candle_closed(bar)

        # Reject late bars'''

text = text.replace(target, replacement)

with open('services/market_data/aggregator.py', 'w', encoding='utf-8') as f:
    f.write(text)
