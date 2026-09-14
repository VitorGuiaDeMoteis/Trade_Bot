import argparse
import asyncio
import json
import logging
import signal
import sys
import uuid
import uvicorn
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal
from collections import deque

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from packages.domain.backtest import Dataset
from packages.domain.paper import PaperConfig
from packages.domain.strategy import Signal
from packages.contracts.observer import (
    AIObserverSnapshot, ObserverCandle, ObserverSignal, ObserverPaper, ObserverPosition
)
from services.backtesting.artifacts import load_manifest
from services.backtesting.engine import replay_steps
from services.observer.engine import evaluate
from services.observer.ollama_provider import OllamaProvider
from services.api.mission_control import router as mc_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# Global State for Mission Control UI
class NightLabState:
    def __init__(self):
        self.status = "IDLE"
        self.run_id = None
        self.symbol = None
        self.step = 0
        self.total_steps = 0
        self.portfolio = None
        self.ai_status = "OK"
        self.last_ai_observation = None
        self.strategy_signal = "HOLD"
        self.timeline = []
        self.start_time = None
        self.initial_cash = "10000.00"
        self.max_drawdown = "0.00"
        self.frame = None
        self.dataset_meta = {"symbols": [], "name": "M8 Night Lab", "candles": 0}
        self.history = []


lab_state = NightLabState()

app = FastAPI(title="Night Lab API")
app.state.mission_control_mode = "night_lab"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
)
app.include_router(mc_router)

@app.get("/api/v1/mission-control/state")
def get_state():
    return JSONResponse({
        "status": lab_state.status,
        "run_id": lab_state.run_id,
        "portfolio": lab_state.portfolio or {"equity":"0","cash":"0","market_value":"0","unrealized_pnl":"0","realized_pnl":"0","fees":"0","positions":[],"orders":[],"fills":[]},
        "speed": "MAX",
        "step": lab_state.step,
        "total_steps": lab_state.total_steps,
        "dataset": lab_state.dataset_meta,
        "orders_count": 0,
        "fills_count": 0,
        "closed_trades": 0,
        "frame": lab_state.frame,
        "initial_cash": lab_state.initial_cash,
        "history": lab_state.history
    })


@app.get("/api/v1/mission-control/timeline")
def get_timeline():
    return JSONResponse(list(lab_state.timeline))

async def run_lab(args, dataset, base_config):
    provider = OllamaProvider(model=args.model)
    symbols = set(c.symbol for c in dataset.candles)
    experiments = []
    for sym in symbols:
        sym_candles = [c for c in dataset.candles if c.symbol == sym]
        experiments.append((sym, sym_candles))
    
    logging.info(f"Loaded dataset with {len(dataset.candles)} total candles. Found {len(experiments)} symbols to test.")
    
    lab_state.status = "RUNNING"
    lab_state.total_steps = sum(len(e[1]) for e in experiments)
    global_step = 0

    for sym, candles in experiments:
        if lab_state.status == "STOPPING":
            break
        
        run_id = str(uuid.uuid4())
        lab_state.run_id = run_id
        lab_state.symbol = sym
        lab_state.peak_equity = base_config.initial_cash
        lab_state.max_drawdown = Decimal(0)
        
        run_dir = Path(f"runs/{run_id}")
        run_dir.mkdir(parents=True, exist_ok=True)
        
        lab_state.dataset_meta = {"symbols": [sym], "name": f"NIGHT LAB: {sym}", "candles": len(candles)}
        lab_state.history = []
        logging.info(f"Starting run {run_id} for symbol {sym}")
        
        sym_dataset = Dataset(tuple(candles))
        config_path = run_dir / "config.json"
        config_path.write_text(json.dumps({"symbol": sym, "capital": str(base_config.initial_cash)}, indent=2))
        
        events_file = open(run_dir / "events.jsonl", "a", encoding="utf-8")
        ai_file = open(run_dir / "ai_observations.jsonl", "a", encoding="utf-8")
        trades_file = open(run_dir / "trades.csv", "a", encoding="utf-8")
        
        step_iter = replay_steps(sym_dataset, base_config)
        step_count = 0
        equity_list = []
        initial_cash = base_config.initial_cash
        final_equity = initial_cash
        
        for frame in step_iter:
            if lab_state.status == "STOPPING":
                break
                
            step_count += 1
            global_step += 1
            lab_state.step = global_step
            
            portfolio = frame["portfolio"]
            c_signals = frame["signals"]
            c_outcomes = frame["outcomes"]
            c_candles = frame["candles"]
            
            final_equity = Decimal(portfolio["equity"])
            equity_list.append(f"{portfolio['timestamp']},{final_equity}")
            
            
            lab_state.portfolio = portfolio
            lab_state.frame = {
                "portfolio": portfolio,
                "candles": c_candles,
                "signals": c_signals,
                "outcomes": c_outcomes
            }
            if c_candles:
                lab_state.history.append(c_candles[-1])
                if len(lab_state.history) > 100:
                    lab_state.history.pop(0)
            if final_equity > Decimal(lab_state.initial_cash):
                pass
            dd = (lab_state.peak_equity - final_equity) / lab_state.peak_equity * Decimal(100)
            if dd > lab_state.max_drawdown:
                lab_state.max_drawdown = dd
            
            current_signal = "HOLD"
            if c_signals:
                current_signal = c_signals[-1]["signal_type"]
            lab_state.strategy_signal = current_signal
            
            event = {
                "step": step_count,
                "timestamp": portfolio["timestamp"],
                "candle": c_candles[-1] if c_candles else None,
                "portfolio": portfolio,
                "signals": c_signals,
                "outcomes": c_outcomes
            }
            events_file.write(json.dumps(event, cls=DecimalEncoder) + "\n")
            
            should_observe = (step_count == 1) or (current_signal in ["BUY", "SELL"]) or (step_count % 50 == 0)
            if should_observe and c_candles:
                timestamp = datetime.fromisoformat(portfolio["timestamp"])
                obs_candles = []
                for c in [event["candle"]]:
                    obs_candles.append(ObserverCandle(
                        symbol=sym,
                        open_time=datetime.fromisoformat(c["open_time"]),
                        close_time=datetime.fromisoformat(c["close_time"]) if "close_time" in c else timestamp,
                        open=str(c["open"]),
                        high=str(c["high"]),
                        low=str(c["low"]),
                        close=str(c["close"]),
                        volume=c["volume"],
                        is_closed=True
                    ))
                
                obs_signals = [
                    ObserverSignal(
                        symbol=sym,
                        strategy_version="v1-deterministic",
                        signal_type=s["signal_type"],
                        generated_at=timestamp
                    ) for s in c_signals
                ]
                
                obs_positions = [
                    ObserverPosition(
                        symbol=p["symbol"],
                        quantity=str(p["quantity"]),
                        average_price=str(p["average_price"]),
                        current_price=str(p["current_price"]),
                        market_value=str(p["market_value"]),
                        unrealized_pnl=str(p["unrealized_pnl"])
                    ) for p in frame.get("positions", [])
                ]
                
                obs_paper = ObserverPaper(
                    as_of_utc=timestamp,
                    paused=False,
                    cash=str(portfolio["cash"]),
                    equity=str(portfolio["equity"]),
                    total_pnl=str(portfolio["total_pnl"]),
                    positions=tuple(obs_positions)
                )
                
                try:
                    snapshot = AIObserverSnapshot(
                        schema_version="1.0",
                        as_of_utc=timestamp,
                        provider="simulator",
                        session_state="connected",
                        symbols=(sym,),
                        timeframe="1h",
                        candles=tuple(obs_candles),
                        signals=tuple(obs_signals),
                        risk_decisions=tuple(),
                        paper=obs_paper,
                        accepted_backtest=None
                    )
                    
                    res = await evaluate(snapshot, provider, enabled=True, timeout=15)
                    lab_state.ai_status = res["status"]
                    if res["status"] == "OK":
                        val = res["validated_output"]
                        lab_state.last_ai_observation = {
                            "regime": val["regime"]["label"],
                            "confidence": val["regime"]["confidence"],
                            "evidence": val["regime"]["evidence"]
                        }
                    else:
                        lab_state.last_ai_observation = None
                        
                    ai_record = {
                        "step": step_count,
                        "timestamp": portfolio["timestamp"],
                        "strategy_signal": current_signal,
                        "observation": res
                    }
                    ai_file.write(json.dumps(ai_record, cls=DecimalEncoder) + "\n")
                    
                    lab_state.timeline.append({
                        "id": str(uuid.uuid4()),
                        "type": "ai_observation",
                        "timestamp": portfolio["timestamp"],
                        "payload": res
                    })
                    
                except Exception as e:
                    lab_state.ai_status = "DEGRADED"
                    ai_file.write(json.dumps({"step": step_count, "error": str(e), "status": "DEGRADED"}) + "\n")
                    logging.warning(f"AI Observer failed: {e}")
            
            if step_count % 10 == 0:
                events_file.flush()
                ai_file.flush()
                trades_file.flush()
                # Yield control loop for API responsiveness
                await asyncio.sleep(0.01)
                
        events_file.close()
        ai_file.close()
        trades_file.close()
        
        (run_dir / "equity_curve.csv").write_text("timestamp,equity\n" + "\n".join(equity_list))
        
        summary = {
            "run_id": run_id,
            "symbol": sym,
            "candles": step_count,
            "initial_capital": str(initial_cash),
            "final_equity": str(final_equity),
            "return_pct": str((final_equity / initial_cash - 1) * 100) + "%",
            "max_drawdown_pct": str(lab_state.max_drawdown)
        }
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        logging.info(f"Completed run {run_id} for {sym}. Saved summary.")
        
    lab_state.status = "FINISHED"
    await provider.close()
    logging.info("Night Lab finished.")


def main():
    parser = argparse.ArgumentParser(description="M8 Night Lab — AI Observer")
    parser.add_argument("--dataset", type=Path, default=Path("services/replay/data/large-history.json"))
    parser.add_argument("--model", type=str, default="qwen3:4b")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    try:
        dataset, base_config = load_manifest(args.dataset)
    except FileNotFoundError:
        logging.error(f"Dataset {args.dataset} not found.")
        sys.exit(1)
        
    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        task = asyncio.create_task(run_lab(args, dataset, base_config))
        yield
        lab_state.status = "STOPPING"
        await task
        
    app.router.lifespan_context = lifespan
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")

if __name__ == "__main__":
    main()
