import json
import asyncio
from pathlib import Path
from collections import Counter
from scripts.evaluation_lab import run_evaluation

def limit_candles():
    with open("scripts/evaluation_lab.py", "r") as f:
        content = f.read()
    with open("scripts/evaluation_lab.py.bak", "w") as f:
        f.write(content)
    content = content.replace("n = len(candles)", "n = min(len(candles), 100)")
    with open("scripts/evaluation_lab.py", "w") as f:
        f.write(content)

def restore_candles():
    with open("scripts/evaluation_lab.py.bak", "r") as f:
        content = f.read()
    with open("scripts/evaluation_lab.py", "w") as f:
        f.write(content)

async def main():
    limit_candles()
    try:
        await run_evaluation()
    finally:
        restore_candles()
        
    eval_dir = Path("evaluations")
    subdirs = sorted([d for d in eval_dir.iterdir() if d.is_dir() and (d / "progress.json").exists()], key=lambda x: x.stat().st_mtime)
    latest = subdirs[-1]
    
    with open(latest / "progress.json") as f:
        progress = json.load(f)
        
    print("\n--- SMOKE TEST RESULTS ---")
    print(f"AI requests: {progress['ai_requests']}")
    print(f"OK: {progress['ai_valid']}")
    
    req = progress['ai_requests']
    valid = progress['ai_valid']
    v_pct = (valid / req * 100) if req > 0 else 0
    print(f"Valid Rate: {v_pct:.1f}%")
    
    hits = progress.get('cache_hits', 0)
    misses = progress.get('cache_misses', 0)
    total = hits + misses
    c_pct = (hits / total * 100) if total > 0 else 0
    print(f"Cache Hit Rate: {c_pct:.1f}%")
    
    regimes = []
    biases = []
    confidences = []
    outputs = []
    
    with open(latest / "observations.jsonl") as f:
        for line in f:
            obj = json.loads(line)
            res = obj["res"]
            if res.get("status") == "OK" and res.get("validated_output"):
                vo = res["validated_output"]
                regimes.append(vo["regime"]["label"])
                biases.append(vo.get("bias", "UNCERTAIN"))
                confidences.append(vo["regime"]["confidence"])
                outputs.append(json.dumps(vo))
                
    print("\nDistributions:")
    print(f"Regimes: {dict(Counter(regimes))}")
    print(f"Biases: {dict(Counter(biases))}")
    print(f"Confidences: {dict(Counter(confidences))}")
    print(f"Unique Outputs: {len(set(outputs))} / {len(outputs)}")

    print("\nTrades Agreement:")
    import csv
    agr = []
    with open(latest / "labeled_trades.csv") as f:
        reader = csv.DictReader(f)
        for row in reader:
            agr.append(row["agreement"])
    print(f"Agreement/Divergence: {dict(Counter(agr))}")

if __name__ == "__main__":
    asyncio.run(main())
