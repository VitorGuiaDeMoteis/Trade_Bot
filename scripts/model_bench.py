import asyncio
import json
import time
import numpy as np
import pandas as pd
from pathlib import Path
from collections import Counter, defaultdict
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score
from sklearn.preprocessing import StandardScaler
from tqdm import tqdm

from services.backtesting.artifacts import load_manifest
from services.observer.ollama_provider import OllamaProvider
from services.observer.prompt import PROMPT
from packages.contracts.observer import AIObserverSnapshot, ObserverCandle
from services.observer.features import calculate_features

async def main():
    semaphore = asyncio.Semaphore(15)

    print("Loading large-history.json...")
    dataset_full, base_config = load_manifest(Path("services/replay/data/large-history.json"))
    
    # Organize to DataFrames per symbol
    symbol_data = defaultdict(list)
    for c in dataset_full.candles:
        symbol_data[c.symbol].append({
            'open_time': c.open_time,
            'close_time': c.close_time,
            'open': float(c.open),
            'high': float(c.high),
            'low': float(c.low),
            'close': float(c.close),
            'volume': int(c.volume)
        })
    
    features_cols = [
        'return_1h', 'return_3h', 'return_6h', 'return_12h', 'return_24h',
        'ema_8', 'ema_21', 'slope_ema_8', 'slope_ema_21', 'dist_ema_8_21',
        'rsi_14', 'atr_14', 'atr_pct', 'rolling_vol_20', 'pos_range_20',
        'pos_range_50', 'dist_recent_high_20', 'dist_recent_low_20',
        'vol_rel_20', 'vol_zscore_20', 'consecutive_up', 'consecutive_down', 'momentum_10'
    ]
    
    dfs = {}
    for sym, data in symbol_data.items():
        df = pd.DataFrame(data).sort_values("open_time").reset_index(drop=True)
        # Calculate features
        df = calculate_features(df)
        
        # Calculate target (next 1h return > 0)
        df['target_return'] = df['close'].pct_change(1).shift(-1)
        df['target'] = (df['target_return'] > 0).astype(int)
        
        df = df.dropna().reset_index(drop=True)
        dfs[sym] = df
        
    print("Training ML Baseline (Logistic Regression)...")
    train_dfs = []
    dev_dfs = {}
    for sym, df in dfs.items():
        n = len(df)
        dev_df = df.iloc[:int(n*0.6)].copy()
        dev_dfs[sym] = dev_df
        train_dfs.append(dev_df)
        
    full_train = pd.concat(train_dfs)
    X_train = full_train[features_cols].values
    y_train = full_train['target'].values
    
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    
    lr = LogisticRegression(max_iter=1000)
    lr.fit(X_train_scaled, y_train)
    
    print(f"ML Train Accuracy: {lr.score(X_train_scaled, y_train):.4f}")
    
    provider = OllamaProvider(model="qwen3:4b")
    
    symbols_to_test = ["SPY", "AAPL", "TSLA"]
    
    results = []
    
    for sym in symbols_to_test:
        dev_df = dev_dfs[sym]
        # Sample 100 random indices
        np.random.seed(42)
        indices = np.random.choice(dev_df.index, size=min(100, len(dev_df)), replace=False)
        indices.sort()
        
        print(f"Testing LLM on {sym} ({len(indices)} samples)...")
        
        async def process_idx(idx):
            row = dev_df.loc[idx]
            feat_dict = {c: float(row[c]) for c in features_cols}
            
            c_mock = ObserverCandle(
                symbol=sym, open_time=row['open_time'], close_time=row['close_time'],
                open=str(row['open']), high=str(row['high']), low=str(row['low']),
                close=str(row['close']), volume=int(row['volume']), is_closed=True
            )
            
            snap = AIObserverSnapshot(
                schema_version="1.1",
                as_of_utc=row['close_time'],
                provider="simulator",
                session_state="connected",
                symbols=tuple([sym]),
                timeframe="1h",
                candles=tuple([c_mock]),
                signals=tuple([]),
                risk_decisions=tuple([]),
                paper=None,
                accepted_backtest=None,
                features=feat_dict
            )
            
            t0 = time.time()
            try:
                async with semaphore:
                    out_bytes = await provider.generate(snap.payload(), PROMPT)
                out_str = out_bytes.decode("utf-8")
                parsed = json.loads(out_str)
                bias = parsed.get("bias", "UNCERTAIN")
                confidence = parsed.get("regime", {}).get("confidence", 0.0)
                regime = parsed.get("regime", {}).get("label", "UNKNOWN")
                evidence = parsed.get("regime", {}).get("evidence", [])
            except Exception as e:
                bias = "ERROR"
                confidence = 0.0
                regime = "ERROR"
                evidence = str(e)
            t1 = time.time()
            
            # ML Predict
            X_sample = scaler.transform([row[features_cols].values])
            ml_pred = lr.predict(X_sample)[0]
            ml_bias = "BULLISH" if ml_pred == 1 else "BEARISH"
            
            # Baseline (Strategy V1)
            base_pred = 1 if row['close'] > row['open'] else 0
            base_bias = "BULLISH" if base_pred == 1 else "BEARISH"
            
            results.append({
                'symbol': sym,
                'target': int(row['target']),
                'target_return': float(row['target_return']),
                'llm_bias': bias,
                'llm_confidence': confidence,
                'llm_regime': regime,
                'ml_bias': ml_bias,
                'base_bias': base_bias,
                'latency': t1 - t0
            })
            
        tasks = [process_idx(idx) for idx in indices]
        await asyncio.gather(*tasks)
            
    res_df = pd.DataFrame(results)
    
    # Filter out ERRORS
    valid_df = res_df[res_df['llm_bias'] != 'ERROR'].copy()
    
    print("\n================ MODEL BENCH REPORT ================")
    print(f"Total evaluated: {len(valid_df)} / {len(results)}")
    print(f"Latency mean: {valid_df['latency'].mean():.2f}s | p95: {valid_df['latency'].quantile(0.95):.2f}s")
    
    # LLM Stats
    print("\n--- LLM Observer (qwen3:4b + features) ---")
    print(f"Regimes: {dict(valid_df['llm_regime'].value_counts())}")
    print(f"Biases: {dict(valid_df['llm_bias'].value_counts())}")
    print(f"Confidences: {dict(valid_df['llm_confidence'].value_counts())}")
    
    def eval_model(col_name):
        df_eval = valid_df[valid_df[col_name].isin(["BULLISH", "BEARISH"])]
        if len(df_eval) == 0:
            return 0, 0, 0, 0, 0
        preds = (df_eval[col_name] == "BULLISH").astype(int)
        y = df_eval['target']
        acc = accuracy_score(y, preds)
        prec = precision_score(y, preds, zero_division=0)
        rec = recall_score(y, preds, zero_division=0)
        # Policy return: long if bullish, short if bearish
        pnl = np.where(preds == 1, df_eval['target_return'], -df_eval['target_return']).sum() * 100
        return acc, prec, rec, pnl, len(df_eval)
        
    print("\n--- Performance ---")
    for name, col in [("Strategy Baseline", "base_bias"), ("ML (LogisticRegression)", "ml_bias"), ("LLM (Qwen3)", "llm_bias")]:
        acc, prec, rec, pnl, n = eval_model(col)
        print(f"[{name}] Acc: {acc*100:.1f}% | Prec (Bull): {prec*100:.1f}% | Recall (Bull): {rec*100:.1f}% | Net PnL: {pnl:.2f}% | Trades: {n}")
        
    print("\n--- ML Feature Importance (Top 5) ---")
    coefs = pd.Series(lr.coef_[0], index=features_cols)
    print(coefs.abs().sort_values(ascending=False).head(5))
    
if __name__ == "__main__":
    asyncio.run(main())
