import asyncio
import json
import time
import numpy as np
import pandas as pd
from pathlib import Path
from tqdm import tqdm

from services.backtesting.artifacts import load_manifest
from services.observer.ollama_provider import OllamaProvider
from services.observer.prompt import PROMPT
from packages.contracts.observer import AIObserverSnapshot, ObserverCandle
from services.observer.features import calculate_features

async def main():
    dataset_full, base_config = load_manifest(Path("services/replay/data/large-history.json"))
    
    symbol_data = []
    for c in dataset_full.candles:
        symbol_data.append({
            'symbol': c.symbol, 'open_time': c.open_time, 'close_time': c.close_time,
            'open': float(c.open), 'high': float(c.high), 'low': float(c.low),
            'close': float(c.close), 'volume': int(c.volume)
        })
    df = pd.DataFrame(symbol_data)
    
    features_cols = [
        'return_1h', 'return_3h', 'return_6h', 'return_12h', 'return_24h',
        'ema_8', 'ema_21', 'slope_ema_8', 'slope_ema_21', 'dist_ema_8_21',
        'rsi_14', 'atr_14', 'atr_pct', 'rolling_vol_20', 'pos_range_20',
        'pos_range_50', 'dist_recent_high_20', 'dist_recent_low_20',
        'vol_rel_20', 'vol_zscore_20', 'consecutive_up', 'consecutive_down', 'momentum_10'
    ]
    
    dev_dfs = {}
    for sym, group in df.groupby('symbol'):
        g = group.sort_values("open_time").reset_index(drop=True)
        g = calculate_features(g)
        g['target_return'] = g['close'].pct_change(1).shift(-1)
        g['target'] = (g['target_return'] > 0).astype(int)
        g = g.dropna().reset_index(drop=True)
        dev_dfs[sym] = g.iloc[:int(len(g)*0.6)].copy()
        
    provider = OllamaProvider(model="qwen2.5-coder:7b") # CHANGED MODEL
    # Ensure cache invalidation
    provider.cache_file = Path("evaluations/.cache_challenger.json")
    if provider.cache_file.exists():
        provider.cache_file.unlink()
        provider._cache = {}
    
    symbols_to_test = ["SPY", "AAPL", "TSLA"]
    results = []
    
    semaphore = asyncio.Semaphore(15)
    
    for sym in symbols_to_test:
        dev_df = dev_dfs[sym]
        np.random.seed(123) # different seed just in case
        indices = np.random.choice(dev_df.index, size=min(100, len(dev_df)), replace=False)
        
        async def process(idx):
            row = dev_df.loc[idx]
            feat_dict = {c: float(row[c]) for c in features_cols}
            c_mock = ObserverCandle(
                symbol=sym, open_time=row['open_time'], close_time=row['close_time'],
                open=str(row['open']), high=str(row['high']), low=str(row['low']),
                close=str(row['close']), volume=int(row['volume']), is_closed=True
            )
            snap = AIObserverSnapshot(
                schema_version="1.1", as_of_utc=row['close_time'], provider="simulator",
                session_state="connected", symbols=(sym,), timeframe="1h",
                candles=(c_mock,), signals=(), risk_decisions=(), paper=None,
                accepted_backtest=None, features=feat_dict
            )
            t0 = time.time()
            try:
                async with semaphore:
                    out_bytes = await provider.generate(snap.payload(), PROMPT)
                out_str = out_bytes.decode("utf-8")
                parsed = json.loads(out_str)
                bias = parsed.get("bias", "UNCERTAIN")
                regime = parsed.get("regime", {}).get("label", "UNKNOWN")
            except Exception as e:
                bias = "ERROR"
                regime = "ERROR"
            t1 = time.time()
            results.append({
                'symbol': sym, 'target': int(row['target']), 'llm_bias': bias,
                'llm_regime': regime, 'latency': t1 - t0
            })
            
        tasks = [process(idx) for idx in indices]
        await asyncio.gather(*tasks)

    df_res = pd.DataFrame(results)
    valid = df_res[df_res['llm_bias'] != 'ERROR']
    
    print("\n=== LLM CHALLENGER (qwen2.5-coder:7b) ===")
    print(f"Total: {len(valid)} / {len(results)}")
    print(f"Latency mean: {valid['latency'].mean():.2f}s | p95: {valid['latency'].quantile(0.95):.2f}s")
    print(f"Regimes: {dict(valid['llm_regime'].value_counts())}")
    print(f"Biases: {dict(valid['llm_bias'].value_counts())}")
    
    if len(valid) > 0:
        preds = (valid['llm_bias'] == 'BULLISH').astype(int)
        acc = (preds == valid['target']).mean()
        print(f"Directional Accuracy: {acc*100:.2f}%")

if __name__ == "__main__":
    asyncio.run(main())
