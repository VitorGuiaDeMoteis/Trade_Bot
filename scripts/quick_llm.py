import asyncio
import json
import pandas as pd
from pathlib import Path

from services.backtesting.artifacts import load_manifest
from services.observer.ollama_provider import OllamaProvider
from services.observer.prompt import PROMPT
from packages.contracts.observer import AIObserverSnapshot, ObserverCandle
from services.observer.features import calculate_features

async def main():
    dataset_full, base_config = load_manifest(Path("services/replay/data/large-history.json"))
    symbol_data = []
    for c in dataset_full.candles:
        if c.symbol == 'SPY':
            symbol_data.append({
                'symbol': c.symbol, 'open_time': c.open_time, 'close_time': c.close_time,
                'open': float(c.open), 'high': float(c.high), 'low': float(c.low),
                'close': float(c.close), 'volume': int(c.volume)
            })
    df = pd.DataFrame(symbol_data).sort_values("open_time").reset_index(drop=True)
    df = calculate_features(df).dropna().reset_index(drop=True)
    
    provider = OllamaProvider(model="qwen2.5-coder:7b")
    
    features_cols = [
        'return_1h', 'return_3h', 'return_6h', 'return_12h', 'return_24h',
        'ema_8', 'ema_21', 'slope_ema_8', 'slope_ema_21', 'dist_ema_8_21',
        'rsi_14', 'atr_14', 'atr_pct', 'rolling_vol_20', 'pos_range_20',
        'pos_range_50', 'dist_recent_high_20', 'dist_recent_low_20',
        'vol_rel_20', 'vol_zscore_20', 'consecutive_up', 'consecutive_down', 'momentum_10'
    ]
    
    for i in range(10):
        row = df.iloc[i+100]
        feat_dict = {c: float(row[c]) for c in features_cols}
        c_mock = ObserverCandle(
            symbol='SPY', open_time=row['open_time'], close_time=row['close_time'],
            open=str(row['open']), high=str(row['high']), low=str(row['low']),
            close=str(row['close']), volume=int(row['volume']), is_closed=True
        )
        snap = AIObserverSnapshot(
            schema_version="1.1", as_of_utc=row['close_time'], provider="simulator",
            session_state="connected", symbols=('SPY',), timeframe="1h",
            candles=(c_mock,), signals=(), risk_decisions=(), paper=None,
            accepted_backtest=None, features=feat_dict
        )
        print(f"Calling Ollama {i+1}...")
        try:
            out_bytes = await provider.generate(snap.payload(), PROMPT)
            parsed = json.loads(out_bytes.decode('utf-8'))
            print(f"Result {i+1}: {parsed.get('regime', {}).get('label')} | Bias: {parsed.get('bias')}")
        except Exception as e:
            print(f"Error {i+1}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
