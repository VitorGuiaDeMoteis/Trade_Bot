import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler

from services.backtesting.artifacts import load_manifest
from services.observer.features import calculate_features

FEE_PCT = 0.0005  # 0.05% por lado? The prompt before used 0.05% per trade. We'll use 0.001 (0.1%) round-trip fee + slip.
ROUND_TRIP_COST = 0.0010
MARGIN = 0.0005
THRESH = ROUND_TRIP_COST + MARGIN  # 0.15% hurdle

def run_trading_sim(df, preds, probs, conf_thresh, horizon_bars):
    """
    Simulates trading:
    If prob > conf_thresh and pred != NEUTRAL, take trade.
    Hold for `horizon_bars`. 
    """
    pnl = []
    wins = 0
    trades = 0
    
    # Track open positions to avoid overlapping trades?
    # Simplified: assume we can take multiple positions or we just take the return of the horizon directly.
    # We will just evaluate the non-overlapping or purely independent trades.
    # To be realistic and avoid overlapping capital issues, we just sum returns of taken trades (assume 1 unit each)
    
    for i in range(len(df)):
        pred = preds[i]
        prob = probs[i]
        ret = df['target_return_real'].iloc[i]  # the actual continuous return of that horizon
        
        # 1: BULLISH, 2: BEARISH, 0: NEUTRAL
        if pred == 1 and prob[1] >= conf_thresh:
            trade_pnl = ret - ROUND_TRIP_COST
            pnl.append(trade_pnl)
            trades += 1
            if trade_pnl > 0: wins += 1
        elif pred == 2 and prob[2] >= conf_thresh:
            trade_pnl = -ret - ROUND_TRIP_COST
            pnl.append(trade_pnl)
            trades += 1
            if trade_pnl > 0: wins += 1
        else:
            pnl.append(0)
            
    pnl = np.array(pnl)
    # Using simple cumulative return sum for a fixed-size bet (or compounding)
    # Since we might have overlapping, compounding could be distorted.
    # We'll use simple sum of PNL percentages as total return for evaluation.
    # For drawdown, we take the cumulative sum curve.
    cum_ret_curve = np.cumsum(pnl)
    total_ret = cum_ret_curve[-1] if len(cum_ret_curve) > 0 else 0
    
    peak = np.maximum.accumulate(cum_ret_curve)
    drawdown = cum_ret_curve - peak
    mdd = drawdown.min() if len(drawdown) > 0 else 0
    
    non_zero = pnl[pnl != 0]
    gross_profits = non_zero[non_zero > 0].sum() if len(non_zero[non_zero > 0]) > 0 else 0
    gross_losses = abs(non_zero[non_zero < 0].sum()) if len(non_zero[non_zero < 0]) > 0 else 1e-9
    pf = gross_profits / gross_losses if gross_losses > 1e-9 else 0
    
    expectancy = non_zero.mean() if len(non_zero) > 0 else 0
    win_rate = wins / trades if trades > 0 else 0
    
    return {
        'return_pct': total_ret * 100,
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
    
    horizons = [3, 6, 12]
    thresholds = [0.55, 0.60, 0.65]
    
    best_config = None
    best_expectancy = -999
    
    processed_dfs_by_horizon = {}
    
    print(f"Targeting THRESH = {THRESH*100:.2f}% (Cost + Margin)")
    
    for h in horizons:
        dev_dfs, val_dfs = [], []
        for sym, group in df.groupby('symbol'):
            g = group.sort_values("open_time").reset_index(drop=True)
            g = calculate_features(g)
            
            # Target is the return over the next H bars
            g['target_return_real'] = g['close'].pct_change(h).shift(-h)
            
            # Classes: 1 (BULLISH), 2 (BEARISH), 0 (NEUTRAL)
            def classify(ret):
                if pd.isna(ret): return np.nan
                if ret > THRESH: return 1
                elif ret < -THRESH: return 2
                else: return 0
                
            g['target_class'] = g['target_return_real'].apply(classify)
            g = g.dropna().reset_index(drop=True)
            
            n = len(g)
            dev_dfs.append(g.iloc[:int(n*0.6)].copy())
            val_dfs.append(g.iloc[int(n*0.6):int(n*0.8)].copy())
            
        full_dev = pd.concat(dev_dfs)
        full_val = pd.concat(val_dfs)
        processed_dfs_by_horizon[h] = (full_dev, full_val)
        
        X_train = full_dev[features_cols].values
        y_train = full_dev['target_class'].values.astype(int)
        
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        
        model = HistGradientBoostingClassifier(random_state=42)
        model.fit(X_train_scaled, y_train)
        
        preds_train = model.predict(X_train_scaled)
        probs_train = model.predict_proba(X_train_scaled)
        
        for conf in thresholds:
            res = run_trading_sim(full_dev, preds_train, probs_train, conf, h)
            # Find best config based on expectancy + reasonable trades in DEV
            # We want trades > 50 to avoid overfitting on 3 lucky trades
            score = res['expectancy_pct']
            
            if res['trades'] > 50 and score > best_expectancy:
                best_expectancy = score
                best_config = {
                    'horizon': h,
                    'conf_thresh': conf,
                    'model': model,
                    'scaler': scaler,
                    'dev_res': res
                }
                
    if not best_config:
        print("NO EDGE \u2014 ABANDON ML SIGNAL V1 (No config found with >50 trades on DEV)")
        return
        
    print("\n=== SELECTED CONFIGURATION (DEV) ===")
    print(f"Horizon: {best_config['horizon']}h | Confidence Thresh: {best_config['conf_thresh']}")
    print(best_config['dev_res'])
    
    print("\n=== VALIDATION RUN (SINGLE SHOT) ===")
    h = best_config['horizon']
    conf = best_config['conf_thresh']
    model = best_config['model']
    scaler = best_config['scaler']
    full_dev, full_val = processed_dfs_by_horizon[h]
    
    X_val = full_val[features_cols].values
    X_val_scaled = scaler.transform(X_val)
    preds_val = model.predict(X_val_scaled)
    probs_val = model.predict_proba(X_val_scaled)
    
    global_res = run_trading_sim(full_val, preds_val, probs_val, conf, h)
    
    print("\n--- GLOBAL VAL RESULTS ---")
    print(f"Expectancy: {global_res['expectancy_pct']:.4f}%")
    print(f"Profit Factor: {global_res['profit_factor']:.4f}")
    print(f"Net Return: {global_res['return_pct']:.4f}%")
    print(f"Max Drawdown: {global_res['max_drawdown_pct']:.4f}%")
    print(f"Win Rate: {global_res['win_rate_pct']:.2f}%")
    print(f"Trades: {global_res['trades']}")
    
    print("\n--- VAL PER SYMBOL ---")
    sym_results = {}
    for sym in full_val['symbol'].unique():
        sym_idx = full_val['symbol'] == sym
        df_sym = full_val[sym_idx]
        p_val = preds_val[sym_idx]
        pr_val = probs_val[sym_idx]
        s_res = run_trading_sim(df_sym, p_val, pr_val, conf, h)
        sym_results[sym] = s_res
        print(f"[{sym}] Trades: {s_res['trades']} | Exp: {s_res['expectancy_pct']:.4f}% | PF: {s_res['profit_factor']:.4f} | Ret: {s_res['return_pct']:.4f}%")
    
    # Check minimum criteria
    # expectancy líquida > 0
    # profit factor > 1
    # retorno líquido > 0
    # drawdown drasticamente menor que os atuais 60% (e.g. < 20%)
    # número de trades significativamente menor que 874
    # resultado não depender somente de um único ativo (at least 2 symbols with positive expectancy / trades > 0)
    
    pos_symbols = sum(1 for s, r in sym_results.items() if r['expectancy_pct'] > 0 and r['trades'] > 0)
    
    success = (
        global_res['expectancy_pct'] > 0 and
        global_res['profit_factor'] > 1 and
        global_res['return_pct'] > 0 and
        global_res['max_drawdown_pct'] > -30 and  # well below 60%
        global_res['trades'] > 0 and global_res['trades'] < 400 and
        pos_symbols >= 2
    )
    
    print("\n================ FINAL VERDICT ================")
    if success:
        print("CRITERIA MET! FROZEN POLICY READY.")
    else:
        print("NO EDGE \u2014 ABANDON ML SIGNAL V1")

if __name__ == "__main__":
    main()
