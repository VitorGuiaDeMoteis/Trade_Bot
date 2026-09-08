import sys
import re

with open('services/market_data/aggregator.py', 'r', encoding='utf-8') as f:
    text = f.read()
    
# We want to store original targets and check if 1m is in it before emitting 1m
text = text.replace(
    "self.target_timeframes = [tf for tf in target_timeframes if tf != \"1m\"]",
    "self.emit_1m = \"1m\" in target_timeframes\n        self.target_timeframes = [tf for tf in target_timeframes if tf != \"1m\"]"
)

text = text.replace(
    "self.on_candle_closed(bar)",
    "if self.emit_1m:\n            self.on_candle_closed(bar)",
    1 # Only replace the first occurrence which is in process(bar) for 1m
)

with open('services/market_data/aggregator.py', 'w', encoding='utf-8') as f:
    f.write(text)

# Also fix the engine.py string encoding
with open('services/strategy_engine/engine.py', 'r', encoding='utf-8') as f:
    engine_text = f.read()

# Replace any weird Sem a..o. with "Sem ação."
engine_text = re.sub(r'Sem a.*?o\.', 'Sem ação.', engine_text)
with open('services/strategy_engine/engine.py', 'w', encoding='utf-8') as f:
    f.write(engine_text)
