import json
import uuid
from pathlib import Path

path = Path("services/replay/data/large-history.json")
raw = json.loads(path.read_text())
stream_id = str(uuid.uuid4())

for i, c in enumerate(raw["candles"]):
    c["candle_id"] = str(uuid.uuid4())
    c["stream_id"] = stream_id
    c["sequence"] = i + 1
    c["regime"] = None
    c["provider"] = "alpaca"

# re-encode properly with hash update
from packages.domain.backtest import digest
raw.pop("manifest_hash", None)
raw["manifest_hash"] = digest(raw)
path.write_text(json.dumps(raw, indent=2))
