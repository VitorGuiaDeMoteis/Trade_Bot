with open("scripts/night_lab.py", "r") as f:
    text = f.read()

import re
text = re.sub(r'"candles": \[\s*\{\s*"symbol":.*?\s*\}\s*for c in \[event\["candle"\]\]\s*\]', '"candles": [event["candle"]]', text, flags=re.DOTALL)
with open("scripts/night_lab.py", "w") as f:
    f.write(text)
