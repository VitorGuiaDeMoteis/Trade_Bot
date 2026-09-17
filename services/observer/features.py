import pandas as pd
import numpy as np

def calculate_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates technical features strictly based on past data (up to t).
    df expects columns: open, high, low, close, volume, open_time
    """
    df = df.copy()
    if len(df) == 0:
        return df
        
    df.sort_values("open_time", inplace=True)
    
    # Returns
    df['return_1h'] = df['close'].pct_change(1)
    df['return_3h'] = df['close'].pct_change(3)
    df['return_6h'] = df['close'].pct_change(6)
    df['return_12h'] = df['close'].pct_change(12)
    df['return_24h'] = df['close'].pct_change(24)
    
    # EMAs
    df['ema_8'] = df['close'].ewm(span=8, adjust=False).mean()
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
    
    # Slopes (pct change of EMA)
    df['slope_ema_8'] = df['ema_8'].pct_change(1)
    df['slope_ema_21'] = df['ema_21'].pct_change(1)
    
    # Distance EMA8/EMA21
    df['dist_ema_8_21'] = (df['ema_8'] - df['ema_21']) / df['ema_21']
    
    # RSI 14
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi_14'] = 100 - (100 / (1 + rs))
    df['rsi_14'] = df['rsi_14'].fillna(50)
    
    # True Range & ATR 14
    prev_close = df['close'].shift(1)
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - prev_close).abs()
    tr3 = (df['low'] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['atr_14'] = tr.rolling(window=14).mean()
    df['atr_pct'] = df['atr_14'] / df['close']
    
    # Rolling Volatility (20 periods of returns)
    df['rolling_vol_20'] = df['return_1h'].rolling(20).std()
    
    # Position in range
    recent_high_20 = df['high'].rolling(20).max()
    recent_low_20 = df['low'].rolling(20).min()
    df['pos_range_20'] = (df['close'] - recent_low_20) / (recent_high_20 - recent_low_20 + 1e-9)
    
    recent_high_50 = df['high'].rolling(50).max()
    recent_low_50 = df['low'].rolling(50).min()
    df['pos_range_50'] = (df['close'] - recent_low_50) / (recent_high_50 - recent_low_50 + 1e-9)
    
    # Distance to recent high/low
    df['dist_recent_high_20'] = (df['close'] - recent_high_20) / df['close']
    df['dist_recent_low_20'] = (df['close'] - recent_low_20) / df['close']
    
    # Volume relative & z-score
    vol_mean = df['volume'].rolling(20).mean()
    vol_std = df['volume'].rolling(20).std()
    df['vol_rel_20'] = df['volume'] / (vol_mean + 1e-9)
    df['vol_zscore_20'] = (df['volume'] - vol_mean) / (vol_std + 1e-9)
    
    # Consecutive up/down
    up = (df['return_1h'] > 0).astype(int)
    down = (df['return_1h'] < 0).astype(int)
    
    def count_consecutive(s):
        return s * (s.groupby((s != s.shift()).cumsum()).cumcount() + 1)
        
    df['consecutive_up'] = count_consecutive(up)
    df['consecutive_down'] = count_consecutive(down)
    
    # Momentum (close - close 10 bars ago) / close 10 bars ago
    df['momentum_10'] = df['close'].pct_change(10)
    
    return df
