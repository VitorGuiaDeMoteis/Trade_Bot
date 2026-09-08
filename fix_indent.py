import sys
with open('services/market_data/aggregator.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "if self.emit_1m:" in line:
        # The next line needs indentation
        next_line = lines[i+1]
        if next_line.strip() == "self.on_candle_closed(bar)":
            lines[i+1] = "            self.on_candle_closed(bar)\n"

with open('services/market_data/aggregator.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
