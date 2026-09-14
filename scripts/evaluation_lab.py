import json
import uuid
import asyncio
import dataclasses
from pathlib import Path
from decimal import Decimal
import pandas as pd  # type: ignore
from datetime import datetime
import sys
import time
import csv
import typing

from services.replay.runtime import replay_steps  # type: ignore
from services.backtesting.artifacts import Dataset, Candle, load_manifest  # type: ignore
from packages.domain.paper import PaperConfig
from services.observer.engine import evaluate
from services.observer.ollama_provider import OllamaProvider
from packages.contracts.observer import AIObserverSnapshot, ObserverPaper, ObserverCandle, ObserverSignal, ObserverPosition

async def run_evaluation() -> None:
    eval_id = str(uuid.uuid4())
    out_dir = Path(f"evaluations/{eval_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print("Loading large-history.json...")
    dataset_full, base_config = load_manifest(Path("services/replay/data/large-history.json"))
    
    from collections import defaultdict
    symbol_candles = defaultdict(list)
    for c in dataset_full.candles:
        symbol_candles[c.symbol].append(c)
        
    for sym in symbol_candles:
        symbol_candles[sym].sort(key=lambda x: x.open_time)
        
    provider = OllamaProvider(model="qwen3:4b")
    
    labeled_trades = []
    
    trades_path = out_dir / "labeled_trades.csv"
    obs_path = out_dir / "observations.jsonl"
    progress_path = out_dir / "progress.json"
    
    with open(trades_path, "w", newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "symbol", "split", "timestamp", "strategy_signal", "ai_status", "error_code", "ai_regime", 
            "ai_bias", "ai_confidence", "ai_risk_flags", "agreement", 
            "entry_price", "exit_price", "net_pnl", "return_pct", "win"
        ])
        
    progress: dict[str, typing.Any] = {
        "status": "RUNNING",
        "symbol": None,
        "split": None,
        "current_candle": 0,
        "total_processed": 0,
        "ai_requests": 0,
        "ai_valid": 0,
        "ai_invalid": 0,
        "ai_timeouts": 0,
        "ai_degraded": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "trades": 0,
        "timestamp": datetime.now().isoformat()
    }
    
    def save_progress() -> None:
        progress["timestamp"] = datetime.now().isoformat()
        with open(progress_path, "w") as f:
            json.dump(progress, f, indent=2)

    save_progress()
    last_flush_time = time.time()
    
    try:
        for sym, candles in symbol_candles.items():
            n = min(len(candles), 200)
            splits = {
                "DEV": candles[:int(n*0.6)],
                "VAL": candles[int(n*0.6):int(n*0.8)],
                "TEST": candles[int(n*0.8):]
            }
            
            for split_name, split_candles in splits.items():
                if not split_candles:
                    continue
                
                progress["symbol"] = sym
                progress["split"] = split_name
                progress["current_candle"] = 0
                
                dataset = Dataset(tuple(split_candles))
                config = dataclasses.replace(base_config)
                
                entries = {}
                step_count = 0
                
                latest_ai_status = "INVALID"
                latest_ai_error = "NO_DATA"
                latest_ai_regime = "UNCERTAIN"
                latest_ai_confidence = 0.0
                latest_ai_bias = "HOLD"
                latest_ai_flags = []
                
                for frame in replay_steps(dataset, config):
                    step_count += 1
                    progress["total_processed"] += 1
                    progress["current_candle"] = step_count
                    
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
                        for c in c_candles[-30:]:
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
                                signal_type=s["signal_type"] if isinstance(s, dict) else s.signal_type,
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
                            signals=tuple([]),
                            risk_decisions=tuple([]),
                            paper=None,
                            accepted_backtest=None
                        )
                        
                        res = await evaluate(snapshot, provider, enabled=True, timeout=120.0)
                        
                        obs_line = json.dumps({"sym": sym, "split": split_name, "step": step_count, "res": res}, default=str)
                        with open(obs_path, "a") as f:
                            f.write(obs_line + "\n")
                        
                        progress["ai_requests"] += 1
                        
                        # Determine AI Status precisely
                        if res["status"] == "OK" and res.get("validated_output"):
                            latest_ai_status = "OK"
                            latest_ai_error = ""
                            progress["ai_valid"] += 1
                        else:
                            latest_ai_error = res.get("error_code", "UNKNOWN")
                            if latest_ai_error == "TIMEOUT":
                                latest_ai_status = "TIMEOUT"
                                progress["ai_timeouts"] += 1
                            elif latest_ai_error in ["PROVIDER_DEGRADED", "MODEL_UNAVAILABLE"]:
                                latest_ai_status = "DEGRADED"
                                progress["ai_degraded"] += 1
                            else:
                                latest_ai_status = "INVALID"
                                progress["ai_invalid"] += 1
                        
                        # Update latest AI metrics
                        if latest_ai_status == "OK":
                            vo = res["validated_output"]
                            latest_ai_regime = vo["regime"]["label"]
                            latest_ai_confidence = float(vo["regime"]["confidence"])
                            flags = [f["code"] for f in vo["risk_flags"]] if vo.get("risk_flags") else []
                            latest_ai_flags = flags
                            
                            latest_ai_bias = vo.get("bias", "UNCERTAIN")
                        else:
                            latest_ai_regime = "UNCERTAIN"
                            latest_ai_confidence = 0.0
                            latest_ai_bias = "HOLD"
                            latest_ai_flags = []

                    for outcome in c_outcomes:
                        if outcome.get("status") == "FILLED":
                            c_symbol = outcome["symbol"]
                            if c_symbol not in entries:
                                entries[c_symbol] = outcome
                                entries[c_symbol]["ai_status"] = latest_ai_status
                                entries[c_symbol]["ai_error"] = latest_ai_error
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
                                
                                # Agreement is ONLY valid if AI is OK
                                agreement = "INVALID"
                                if entry["ai_status"] == "OK":
                                    if (entry["ai_bias"] == "BULLISH" and entry["strategy_signal"] == "BUY") or (entry["ai_bias"] == "BEARISH" and entry["strategy_signal"] == "SELL"):
                                        agreement = "AGREEMENT"
                                    elif entry["ai_bias"] in ["UNCERTAIN", "NEUTRAL"] or entry["strategy_signal"] == "HOLD":
                                        agreement = "NEUTRAL"
                                    else:
                                        agreement = "DIVERGENCE"
                                
                                ret_pct = (net / (Decimal(str(entry.get("price", 1))) * Decimal(str(entry.get("quantity", 1))))) * 100
                                
                                t_row = [
                                    sym, split_name, entry.get("executed_at", ""), entry["strategy_signal"],
                                    entry["ai_status"], entry["ai_error"], entry["ai_regime"], entry["ai_bias"], entry["ai_confidence"],
                                    ",".join(entry["ai_flags"]), agreement, float(entry.get("price", 0)),
                                    float(outcome.get("price", 0)), float(net), float(ret_pct),
                                    1 if net > 0 else 0
                                ]
                                
                                with open(trades_path, "a", newline='') as f:
                                    writer = csv.writer(f)
                                    writer.writerow(t_row)
                                    
                                labeled_trades.append(t_row)
                                progress["trades"] += 1

                    if time.time() - last_flush_time > 1.0:
                        save_progress()
                        
                        hits = provider.cache_hits
                        misses = provider.cache_misses
                        total_cache = hits + misses
                        progress["cache_hits"] = hits
                        progress["cache_misses"] = misses
                        cache_pct = (hits / total_cache * 100) if total_cache > 0 else 0
                        
                        req = progress["ai_requests"]
                        valid = progress["ai_valid"]
                        v_pct = (valid / req * 100) if req > 0 else 0
                        
                        sys.stdout.write(f"\r{sym} {split_name} {step_count}/{len(split_candles)} | Trades {progress['trades']} | AI OK {valid}/{req} ({v_pct:.1f}%) | Cache {cache_pct:.0f}%  ")
                        sys.stdout.flush()
                        last_flush_time = time.time()
                        
            print()

        progress["status"] = "COMPLETED"
    except KeyboardInterrupt:
        print("\nInterrupted by user!")
        progress["status"] = "INTERRUPTED"
    except Exception as e:
        print(f"\nError occurred: {e}")
        progress["status"] = "INTERRUPTED"
    finally:
        save_progress()
        await provider.close()
        
        df = pd.DataFrame(labeled_trades, columns=[
            "symbol", "split", "timestamp", "strategy_signal", "ai_status", "error_code", "ai_regime", 
            "ai_bias", "ai_confidence", "ai_risk_flags", "agreement", 
            "entry_price", "exit_price", "net_pnl", "return_pct", "win"
        ])
        
        results = []
        for split in ["DEV", "VAL", "TEST"]:
            split_df = df[df["split"] == split]
            if len(split_df) == 0:
                continue
                
            def calc_metrics(subset: pd.DataFrame, policy_name: str, current_split: str = split) -> dict[str, typing.Any]:
                if len(subset) == 0:
                    return {"split": current_split, "policy": policy_name, "trades": 0, "win_rate": 0, "net_pnl": 0}
                win_rate = subset["win"].mean() * 100
                net = subset["net_pnl"].sum()
                return {
                    "split": current_split,
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

        if results:
            res_df = pd.DataFrame(results)
            res_df.to_csv(out_dir / "policy_comparison.csv", index=False)
            
            report = f"# AI Evaluation Lab Report\n\nTotal trades: {len(df)}\nStatus: {progress['status']}\n\n"
            report += f"**AI Stats:**\nRequests: {progress['ai_requests']}\nOK: {progress['ai_valid']}\nINVALID: {progress['ai_invalid']}\nTIMEOUT: {progress['ai_timeouts']}\nDEGRADED: {progress['ai_degraded']}\n\n"
            report += res_df.to_markdown()
            
            with open(out_dir / "report.md", "w") as f:
                f.write(report)
                
            print(f"\nDone! Check {out_dir}/report.md")
        else:
            print("\nNo trades collected. Check progress.json")

if __name__ == "__main__":
    asyncio.run(run_evaluation())
