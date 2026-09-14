import json
import uuid
import asyncio
import dataclasses
from pathlib import Path
from decimal import Decimal
import pandas as pd
from datetime import datetime

from services.replay.runtime import replay_steps
from services.backtesting.artifacts import Dataset, Candle, load_manifest
from packages.domain.paper import PaperConfig
from services.observer.engine import evaluate
from services.observer.ollama_provider import OllamaProvider
from packages.contracts.observer import AIObserverSnapshot, ObserverPaper, ObserverCandle, ObserverSignal, ObserverPosition, ObserverRisk
from collections import defaultdict

async def run_evaluation():
    eval_id = str(uuid.uuid4())
    out_dir = Path(f"evaluations/{eval_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print("Loading large-history.json...")
    dataset_full, base_config = load_manifest(Path("services/replay/data/large-history.json"))
    symbol_candles = defaultdict(list)
    for c in dataset_full.candles:
        symbol_candles[c.symbol].append(c)
        
    for sym in symbol_candles:
        symbol_candles[sym].sort(key=lambda x: x.open_time)
        
    provider = OllamaProvider(model="qwen3:4b")
    
    labeled_trades = []
    observations = []
    
    for sym, candles in symbol_candles.items():
        n = len(candles)
        splits = {
            "DEV": candles[:int(n*0.6)],
            "VAL": candles[int(n*0.6):int(n*0.8)],
            "TEST": candles[int(n*0.8):]
        }
        
        for split_name, split_candles in splits.items():
            if not split_candles:
                continue
            print(f"Running {sym} - {split_name} ({len(split_candles)} candles)")
            
            dataset = Dataset(tuple(split_candles))
            config = dataclasses.replace(base_config)
            
            entries = {}
            step_count = 0
            
            latest_ai_regime = "UNCERTAIN"
            latest_ai_confidence = 0.0
            latest_ai_bias = "HOLD"
            latest_ai_flags = []
            
            for frame in replay_steps(dataset, config):
                step_count += 1
                c_outcomes = frame["outcomes"]
                c_signals = frame["signals"]
                c_candles = frame["candles"]
                portfolio = frame["portfolio"]
                
                current_signal = c_signals[-1]["signal_type"] if c_signals else "HOLD"
                should_observe = (current_signal in ["BUY", "SELL"]) or (step_count % 50 == 0) or (step_count == 1)
                
                if should_observe and c_candles:
                    positions = []
                    for p in portfolio.get("positions", []):
                        try:
                            positions.append(ObserverPosition(
                                symbol=p["symbol"],
                                quantity=int(p["quantity"]),
                                average_price=str(p["average_price"])
                            ))
                        except Exception:
                            pass
                            
                    paper = ObserverPaper(
                        as_of_utc=datetime.fromisoformat(portfolio["timestamp"]),
                        cash=str(portfolio["cash"]),
                        equity=str(portfolio["equity"]),
                        total_pnl=str(portfolio["total_pnl"]),
                        positions=tuple(positions),
                        paused=False
                    )
                    
                    obs_candles = []
                    for c in c_candles[-1:]:
                        if isinstance(c, dict):
                            c_dict = c.copy()
                        else:
                            c_dict = dataclasses.asdict(c)
                        for k in ["timeframe", "provider", "candle_id", "stream_id", "sequence", "regime"]:
                            c_dict.pop(k, None)
                        if isinstance(c_dict.get("open_time"), str):
                            c_dict["open_time"] = datetime.fromisoformat(c_dict["open_time"])
                        if isinstance(c_dict.get("close_time"), str):
                            c_dict["close_time"] = datetime.fromisoformat(c_dict["close_time"])
                        obs_candles.append(ObserverCandle(**c_dict))
                    
                    obs_signals = [
                        ObserverSignal(
                            symbol=sym,
                            strategy_version="v1-deterministic",
                            signal_type=s.signal_type if not isinstance(s, dict) else s["signal_type"],
                            generated_at=datetime.fromisoformat(portfolio["timestamp"])
                        ) for s in c_signals
                    ]
                    
                    snapshot = AIObserverSnapshot(
                        schema_version="1.0",
                        as_of_utc=datetime.fromisoformat(portfolio["timestamp"]),
                        timeframe="1h",
                        provider="simulator",
                        session_state="connected",
                        symbols=tuple([sym]),
                        candles=tuple(obs_candles),
                        signals=tuple(obs_signals),
                        risk_decisions=tuple([]),
                        paper=paper,
                        accepted_backtest=None
                    )
                    
                    res = await evaluate(snapshot, provider, enabled=True, timeout=120.0)
                    observations.append({"sym": sym, "split": split_name, "step": step_count, "res": res})
                    
                    if res["status"] == "OK" and res.get("validated_output"):
                        vo = res["validated_output"]
                        latest_ai_regime = vo["regime"]["label"]
                        latest_ai_confidence = float(vo["regime"]["confidence"])
                        flags = [f["code"] for f in vo["risk_flags"]] if vo.get("risk_flags") else []
                        latest_ai_flags = flags
                        
                        if latest_ai_regime == "BULL":
                            latest_ai_bias = "BUY"
                        elif latest_ai_regime == "BEAR":
                            latest_ai_bias = "SELL"
                        else:
                            latest_ai_bias = "HOLD"

                for outcome in c_outcomes:
                    if outcome.get("status") == "FILLED":
                        c_symbol = outcome["symbol"]
                        if c_symbol not in entries:
                            entries[c_symbol] = outcome
                            entries[c_symbol]["ai_regime"] = latest_ai_regime
                            entries[c_symbol]["ai_confidence"] = latest_ai_confidence
                            entries[c_symbol]["ai_bias"] = latest_ai_bias
                            entries[c_symbol]["ai_flags"] = latest_ai_flags
                            entries[c_symbol]["strategy_signal"] = current_signal
                        else:
                            entry = entries.pop(c_symbol)
                            fee_entry = Decimal(str(entry.get("fee", 0)))
                            fee_exit = Decimal(str(outcome.get("fee", 0)))
                            fees = fee_entry + fee_exit
                            realized = Decimal(str(outcome.get("realized_pnl", 0)))
                            net = realized - fees
                            
                            agreement = "AGREEMENT" if entry["ai_bias"] == entry["strategy_signal"] else "DIVERGENCE"
                            if entry["ai_bias"] == "HOLD":
                                agreement = "NEUTRAL"
                                
                            ret_pct = (net / (Decimal(str(entry.get("price", 1))) * Decimal(str(entry.get("quantity", 1))))) * 100
                                
                            labeled_trades.append({
                                "symbol": sym,
                                "split": split_name,
                                "timestamp": entry.get("executed_at", ""),
                                "strategy_signal": entry["strategy_signal"],
                                "ai_regime": entry["ai_regime"],
                                "ai_bias": entry["ai_bias"],
                                "ai_confidence": entry["ai_confidence"],
                                "ai_risk_flags": ",".join(entry["ai_flags"]),
                                "agreement": agreement,
                                "entry_price": float(entry.get("price", 0)),
                                "exit_price": float(outcome.get("price", 0)),
                                "net_pnl": float(net),
                                "return_pct": float(ret_pct),
                                "win": 1 if net > 0 else 0
                            })
                            
    await provider.close()
    
    df = pd.DataFrame(labeled_trades)
    df.to_csv(out_dir / "labeled_trades.csv", index=False)
    
    with open(out_dir / "observations.json", "w") as f:
        json.dump(observations, f, default=str)
        
    print(f"Total trades collected: {len(df)}")
    
    results = []
    
    for split in ["DEV", "VAL", "TEST"]:
        split_df = df[df["split"] == split]
        if len(split_df) == 0:
            continue
            
        def calc_metrics(subset, policy_name):
            if len(subset) == 0:
                return {"split": split, "policy": policy_name, "trades": 0, "win_rate": 0, "net_pnl": 0}
            win_rate = subset["win"].mean() * 100
            net = subset["net_pnl"].sum()
            return {
                "split": split,
                "policy": policy_name,
                "trades": len(subset),
                "win_rate": win_rate,
                "net_pnl": net
            }
            
        results.append(calc_metrics(split_df, "baseline_normal"))
        results.append(calc_metrics(split_df[split_df["agreement"] == "AGREEMENT"], "only_agreement"))
        
        for conf in [60, 70, 80, 90]:
            cond = ~((split_df["agreement"] == "DIVERGENCE") & (split_df["ai_confidence"] >= conf/100.0))
            results.append(calc_metrics(split_df[cond], f"block_div_{conf}"))

    res_df = pd.DataFrame(results)
    res_df.to_csv(out_dir / "policy_comparison.csv", index=False)
    
    report = f"# AI Evaluation Lab Report\n\nTotal trades: {len(df)}\n\n"
    report += res_df.to_markdown()
    
    with open(out_dir / "report.md", "w") as f:
        f.write(report)
        
    print(f"Done! Check {out_dir}/report.md")

if __name__ == "__main__":
    asyncio.run(run_evaluation())
