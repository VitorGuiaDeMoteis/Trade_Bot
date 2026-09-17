import asyncio
import time
import json
import numpy as np
from pathlib import Path
from collections import Counter, defaultdict

from packages.contracts.observer import AIObserverSnapshot, ObserverCandle
from services.backtesting.artifacts import load_manifest
from services.observer.ollama_provider import OllamaProvider
from services.observer.prompt import PROMPT

async def main():
    print("Loading large-history.json...")
    dataset_full, base_config = load_manifest(Path("services/replay/data/large-history.json"))
    
    symbol_candles = defaultdict(list)
    for c in dataset_full.candles:
        symbol_candles[c.symbol].append(c)
        
    for sym in symbol_candles:
        symbol_candles[sym].sort(key=lambda x: x.open_time)
        
    provider = OllamaProvider(model="qwen3:4b")
    
    metrics = {
        "requests": 0,
        "valid": 0,
        "latencies": [],
        "regimes": Counter(),
        "biases": Counter(),
        "confidences": [],
        "unique_outputs": set(),
        "by_symbol": defaultdict(lambda: {
            "requests": 0,
            "valid": 0,
            "regimes": Counter(),
            "biases": Counter(),
            "confidences": [],
            "latencies": []
        })
    }
    
    sanity_samples = defaultdict(list)
    symbols_to_test = ["SPY", "AAPL", "TSLA"]
    
    for sym in symbols_to_test:
        candles = symbol_candles[sym]
        dev_candles = candles[:int(len(candles)*0.6)]
        
        valid_start = 30
        valid_end = len(dev_candles) - 1
        
        # Taking 33 samples per symbol to finish in a reasonable time (100 total approx)
        indices = np.linspace(valid_start, valid_end, 33, dtype=int)
        
        print(f"Testing {sym}...")
        for idx in indices:
            obs_candles = dev_candles[idx-29:idx+1]
            as_of_utc = obs_candles[-1].close_time
            
            obs_candles_converted = []
            for c in obs_candles:
                obs_candles_converted.append(ObserverCandle(
                    symbol=c.symbol,
                    open_time=c.open_time,
                    close_time=c.close_time,
                    open=str(c.open),
                    high=str(c.high),
                    low=str(c.low),
                    close=str(c.close),
                    volume=int(c.volume),
                    is_closed=True
                ))
            
            snap = AIObserverSnapshot(
                schema_version="1.1",
                as_of_utc=as_of_utc,
                provider="simulator",
                session_state="connected",
                symbols=tuple([sym]),
                timeframe="1h",
                candles=tuple(obs_candles_converted),
                signals=tuple([]),
                risk_decisions=tuple([]),
                paper=None,
                accepted_backtest=None
            )
            
            t0 = time.time()
            try:
                out_bytes = await provider.generate(snap.payload(), PROMPT)
                out_str = out_bytes.decode("utf-8")
                parsed = json.loads(out_str)
                metrics["valid"] += 1
                metrics["by_symbol"][sym]["valid"] += 1
                
                regime = parsed.get("regime", {}).get("label", "UNKNOWN")
                bias = parsed.get("bias", "UNKNOWN")
                conf = parsed.get("regime", {}).get("confidence", 0.0)
                
                metrics["regimes"][regime] += 1
                metrics["biases"][bias] += 1
                metrics["confidences"].append(conf)
                metrics["unique_outputs"].add(json.dumps(parsed, sort_keys=True))
                
                metrics["by_symbol"][sym]["regimes"][regime] += 1
                metrics["by_symbol"][sym]["biases"][bias] += 1
                metrics["by_symbol"][sym]["confidences"].append(conf)
                
                if len(sanity_samples[sym]) < 3:
                    sanity_samples[sym].append({
                        "context_summary": f"Candles: {len(obs_candles_converted)}, from {obs_candles_converted[0].open_time} to {obs_candles_converted[-1].close_time}, close prices: {obs_candles_converted[0].close} -> {obs_candles_converted[-1].close}",
                        "output": parsed
                    })
                    
            except Exception as e:
                print(f"Error on {sym} idx {idx}: {e}")
            
            t1 = time.time()
            metrics["requests"] += 1
            metrics["by_symbol"][sym]["requests"] += 1
            latency = t1 - t0
            metrics["latencies"].append(latency)
            metrics["by_symbol"][sym]["latencies"].append(latency)
            
            if metrics["requests"] % 10 == 0:
                print(f"Processed {metrics['requests']} / 99 (Valid: {metrics['valid']})")

    print("\n================ CALIBRATION REPORT ================")
    print(f"AI requests: {metrics['requests']}")
    print(f"Valid Rate: {(metrics['valid']/metrics['requests']*100) if metrics['requests'] > 0 else 0:.1f}%")
    
    hits = provider.cache_hits
    misses = provider.cache_misses
    total = hits + misses
    print(f"Cache hit rate: {(hits/total*100) if total > 0 else 0:.1f}%")
    
    lats = metrics["latencies"]
    print(f"Latency mean: {np.mean(lats):.2f}s | p95: {np.percentile(lats, 95):.2f}s")
    
    print("\n--- Global Distributions ---")
    print(f"Regimes: {dict(metrics['regimes'])}")
    print(f"Biases: {dict(metrics['biases'])}")
    confs = metrics["confidences"]
    print(f"Confidence: mean={np.mean(confs):.2f}, std={np.std(confs):.2f}")
    print(f"Confidence distribution: {dict(Counter(confs))}")
    print(f"Distinct confidence values: {len(set(confs))}")
    print(f"Unique outputs: {len(metrics['unique_outputs'])} / {metrics['valid']}")
    
    print("\n--- By Symbol ---")
    for sym in symbols_to_test:
        sm = metrics["by_symbol"][sym]
        print(f"{sym}: Regimes: {dict(sm['regimes'])} | Biases: {dict(sm['biases'])}")
        
    print("\n--- Sanity Samples (3 per symbol) ---")
    for sym, samples in sanity_samples.items():
        print(f"\n[{sym}]")
        for i, s in enumerate(samples):
            print(f"  Sample {i+1}:")
            print(f"    Context: {s['context_summary']}")
            print(f"    Output: {json.dumps(s['output'], indent=2)}")

if __name__ == "__main__":
    asyncio.run(main())
