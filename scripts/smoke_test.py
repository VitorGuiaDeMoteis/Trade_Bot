import json
import asyncio
from pathlib import Path
from collections import Counter
from scripts.evaluation_lab import run_evaluation

async def main() -> None:
    # NOTE: this harness used to "cap" the run by rewriting the tracked module
    # scripts/evaluation_lab.py in place (and leaving a .bak beside it). The
    # anchor string it patched no longer exists, so the rewrite did nothing but
    # touch tracked production source and risk leaving it mangled on a crash.
    # Bounding an evaluation must be done by passing a limit, never by editing
    # repository files at runtime.
    await run_evaluation()

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
