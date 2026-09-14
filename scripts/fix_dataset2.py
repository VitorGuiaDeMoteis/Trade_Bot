import json
from pathlib import Path
from packages.domain.backtest import Dataset
from services.backtesting.artifacts import load_manifest, Candle, CandleResponse

path = Path("services/replay/data/large-history.json")
raw = json.loads(path.read_text())

candles_obj = tuple(Candle(**CandleResponse.model_validate(c).model_dump()) for c in raw["candles"])
ds = Dataset(candles_obj)
raw["dataset_hash"] = ds.hash

from packages.domain.backtest import digest
raw.pop("manifest_hash", None)
raw["manifest_hash"] = digest(raw)
path.write_text(json.dumps(raw, indent=2))
