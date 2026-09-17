import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from services.observer.features import calculate_features

def test_no_look_ahead():
    # Create 100 random candles
    np.random.seed(42)
    dates = [datetime(2023, 1, 1) + timedelta(hours=i) for i in range(100)]
    closes = np.cumprod(1 + np.random.normal(0, 0.01, 100)) * 100
    highs = closes * (1 + np.random.uniform(0, 0.01, 100))
    lows = closes * (1 - np.random.uniform(0, 0.01, 100))
    opens = closes * (1 + np.random.normal(0, 0.005, 100))
    vols = np.random.randint(100, 1000, 100)
    
    df1 = pd.DataFrame({
        'open_time': dates,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': vols
    })
    
    # Calculate features on full set
    feat1 = calculate_features(df1)
    
    # Mutate the future (t >= 50) and recalculate
    df2 = df1.copy()
    df2.loc[50:, 'close'] *= 1.5 
    df2.loc[50:, 'high'] *= 1.5
    df2.loc[50:, 'volume'] *= 2
    
    feat2 = calculate_features(df2)
    
    # Verify features at t=49 match exactly between both runs
    t_idx = 49
    row1 = feat1.iloc[t_idx]
    row2 = feat2.iloc[t_idx]
    
    for col in feat1.select_dtypes(include=[np.number]).columns:
        if pd.isna(row1[col]) and pd.isna(row2[col]):
            continue
        assert np.isclose(row1[col], row2[col]), f"Feature {col} leaked future data!"

