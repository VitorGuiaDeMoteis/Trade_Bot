with open("scripts/night_lab.py", "r") as f:
    text = f.read()

new_state = """    def __init__(self):
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
"""

new_api = """@app.get("/api/v1/mission-control/state")
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
"""

text = text.replace('    def __init__(self):\n        self.status = "IDLE"\n        self.run_id = None\n        self.symbol = None\n        self.step = 0\n        self.total_steps = 0\n        self.portfolio = None\n        self.ai_status = "OK"\n        self.last_ai_observation = None\n        self.strategy_signal = "HOLD"\n        self.timeline = deque(maxlen=20)\n        self.start_time = datetime.now(timezone.utc)\n        self.initial_cash = Decimal(0)\n        self.max_drawdown = Decimal(0)\n        self.peak_equity = Decimal(0)', new_state)

text = text.replace('@app.get("/api/v1/mission-control/state")\ndef get_state():\n    equity = Decimal(lab_state.portfolio["equity"]) if lab_state.portfolio else Decimal(0)\n    cash = Decimal(lab_state.portfolio["cash"]) if lab_state.portfolio else Decimal(0)\n    unrealized = Decimal(lab_state.portfolio["unrealized_pnl"]) if lab_state.portfolio else Decimal(0)\n    realized = Decimal(lab_state.portfolio["realized_pnl"]) if lab_state.portfolio else Decimal(0)\n    return JSONResponse({\n        "status": lab_state.status,\n        "run_id": lab_state.run_id,\n        "symbol": lab_state.symbol,\n        "progress": f"{lab_state.step}/{lab_state.total_steps}" if lab_state.total_steps else "0/0",\n        "equity": str(equity),\n        "cash": str(cash),\n        "unrealized_pnl": str(unrealized),\n        "realized_pnl": str(realized),\n        "max_drawdown": str(lab_state.max_drawdown),\n        "ai_status": lab_state.ai_status,\n        "strategy_signal": lab_state.strategy_signal,\n        "last_ai_observation": lab_state.last_ai_observation,\n        "uptime": str(datetime.now(timezone.utc) - lab_state.start_time).split(\'.\')[0]\n    })', new_api)

with open("scripts/night_lab.py", "w") as f:
    f.write(text)
