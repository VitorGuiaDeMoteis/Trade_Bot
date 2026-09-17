import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, precision_score, recall_score,
    confusion_matrix, roc_auc_score, brier_score_loss
)
from sklearn.preprocessing import StandardScaler

from services.backtesting.artifacts import load_manifest
from services.observer.features import calculate_features

FEE_PCT = 0.0005  # 0.05% por trade

def evaluate_ml(name, model, X_test, y_test, df_test, symbol="GLOBAL"):
    preds = model.predict(X_test)
    probs = model.predict_proba(X_test)[:, 1]
    
    acc = accuracy_score(y_test, preds)
    bacc = balanced_accuracy_score(y_test, preds)
    prec_bull = precision_score(y_test, preds, pos_label=1, zero_division=0)
    rec_bull = recall_score(y_test, preds, pos_label=1, zero_division=0)
    prec_bear = precision_score(y_test, preds, pos_label=0, zero_division=0)
    rec_bear = recall_score(y_test, preds, pos_label=0, zero_division=0)
    cm = confusion_matrix(y_test, preds)
    try:
        roc = roc_auc_score(y_test, probs)
    except:
        roc = 0.5
    brier = brier_score_loss(y_test, probs)
    
    return {
        'model': name,
        'symbol': symbol,
        'acc': acc, 'bacc': bacc, 
        'prec_bull': prec_bull, 'rec_bull': rec_bull,
        'prec_bear': prec_bear, 'rec_bear': rec_bear,
        'roc_auc': roc, 'brier': brier, 'cm': cm.tolist(),
        'preds': preds, 'probs': probs
    }

def run_simulation(df, policy_name, signal_col, prob_col=None):
    # Strategy V1: signal_col = 'BUY' (1), 'SELL' (0), 'HOLD' (np.nan)
    df_sim = df.copy()
    
    # Calculate returns for holding 1 period
    pnl = []
    trades = 0
    wins = 0
    
    for i in range(len(df_sim)):
        sig = df_sim.iloc[i][signal_col]
        ret = df_sim.iloc[i]['target_return']
        if pd.isna(sig):
            pnl.append(0)
            continue
            
        trades += 1
        trade_pnl = ret if sig == 1 else -ret
        trade_pnl -= (2 * FEE_PCT) # round trip
        
        pnl.append(trade_pnl)
        if trade_pnl > 0:
            wins += 1
            
    pnl = np.array(pnl)
    cum_ret = np.prod(1 + pnl) - 1
    
    # max drawdown
    cum_series = np.cumprod(1 + pnl)
    peak = np.maximum.accumulate(cum_series)
    drawdown = (cum_series - peak) / peak
    mdd = drawdown.min()
    
    gross_profits = pnl[pnl > 0].sum() if len(pnl[pnl > 0]) > 0 else 0
    gross_losses = abs(pnl[pnl < 0].sum()) if len(pnl[pnl < 0]) > 0 else 1e-9
    pf = gross_profits / gross_losses if gross_losses > 1e-9 else 0
    
    expectancy = pnl.mean() if len(pnl) > 0 else 0
    win_rate = wins / trades if trades > 0 else 0
    
    return {
        'policy': policy_name,
        'return_pct': cum_ret * 100,
        'max_drawdown_pct': mdd * 100,
        'profit_factor': pf,
        'expectancy_pct': expectancy * 100,
        'win_rate_pct': win_rate * 100,
        'trades': trades
    }

def main():
    print("Loading large-history.json...")
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
    
    dev_dfs, val_dfs = [], []
    for sym, group in df.groupby('symbol'):
        g = group.sort_values("open_time").reset_index(drop=True)
        g = calculate_features(g)
        g['target_return'] = g['close'].pct_change(1).shift(-1)
        g['target'] = (g['target_return'] > 0).astype(int)
        g = g.dropna().reset_index(drop=True)
        
        n = len(g)
        dev_dfs.append(g.iloc[:int(n*0.6)].copy())
        val_dfs.append(g.iloc[int(n*0.6):int(n*0.8)].copy())
        
    full_dev = pd.concat(dev_dfs)
    full_val = pd.concat(val_dfs)
    
    X_train = full_dev[features_cols].values
    y_train = full_dev['target'].values
    
    X_val = full_val[features_cols].values
    y_val = full_val['target'].values
    
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    
    models = {
        'LogisticRegression': LogisticRegression(max_iter=1000),
        'HistGradientBoosting': HistGradientBoostingClassifier(random_state=42),
        'RandomForest': RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
    }
    
    print("\n--- Training ML Models on DEV ---")
    val_results = []
    
    for name, model in models.items():
        model.fit(X_train_scaled, y_train)
        
        # Eval global
        res = evaluate_ml(name, model, X_val_scaled, y_val, full_val)
        val_results.append(res)
        
        # Eval per symbol
        for sym in full_val['symbol'].unique():
            sym_idx = full_val['symbol'] == sym
            X_sym = X_val_scaled[sym_idx]
            y_sym = y_val[sym_idx]
            df_sym = full_val[sym_idx]
            val_results.append(evaluate_ml(name, model, X_sym, y_sym, df_sym, symbol=sym))
            
    print("\n--- ML Validation Metrics (GLOBAL) ---")
    for r in val_results:
        if r['symbol'] == 'GLOBAL':
            print(f"{r['model']}: Acc={r['acc']:.4f}, B-Acc={r['bacc']:.4f}, " 
                  f"BullPrec={r['prec_bull']:.4f}, BullRec={r['rec_bull']:.4f}, "
                  f"BearPrec={r['prec_bear']:.4f}, ROC_AUC={r['roc_auc']:.4f}, Brier={r['brier']:.4f}")
            
    print("\n--- Counterfactual Trading Simulation on VAL ---")
    # Base strategy:
    full_val['base_signal'] = (full_val['close'] > full_val['open']).astype(int)
    
    best_model = models['HistGradientBoosting']
    val_probs = best_model.predict_proba(X_val_scaled)[:, 1]
    full_val['ml_prob_bull'] = val_probs
    
    # Policies:
    # 1. Base Strategy
    print(run_simulation(full_val, "Base Strategy (v1-det)", 'base_signal'))
    
    # 2. Block BUY if ML prob < 0.48 (Bearish confidence)
    #    Block SELL if ML prob > 0.52 (Bullish confidence)
    def ml_filter(row):
        sig = row['base_signal']
        prob = row['ml_prob_bull']
        if sig == 1 and prob < 0.48: return np.nan
        if sig == 0 and prob > 0.52: return np.nan
        return sig
    full_val['filter_1'] = full_val.apply(ml_filter, axis=1)
    print(run_simulation(full_val, "Base + Block(Prob < 0.48 / > 0.52)", 'filter_1'))
    
    # 3. Only Trade on ML Agreement
    def ml_agreement(row):
        sig = row['base_signal']
        ml_bull = row['ml_prob_bull'] > 0.5
        if sig == 1 and ml_bull: return 1
        if sig == 0 and not ml_bull: return 0
        return np.nan
    full_val['filter_2'] = full_val.apply(ml_agreement, axis=1)
    print(run_simulation(full_val, "Base + Strict Agreement", 'filter_2'))
    
    # 4. Pure ML Strategy (Trade every bar on ML prob > 0.5)
    full_val['pure_ml'] = (full_val['ml_prob_bull'] > 0.5).astype(int)
    print(run_simulation(full_val, "Pure ML Policy", 'pure_ml'))

if __name__ == "__main__":
    main()
