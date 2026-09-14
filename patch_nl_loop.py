with open("scripts/night_lab.py", "r") as f:
    text = f.read()

import re

# Add history append and frame set
loop_update = """            
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
"""

text = re.sub(r'            lab_state\.portfolio = portfolio\n            if final_equity > lab_state\.peak_equity:\n                lab_state\.peak_equity = final_equity', loop_update + '            if final_equity > Decimal(lab_state.initial_cash):\n                pass', text)

# Add dataset meta init
meta_update = """        lab_state.dataset_meta = {"symbols": [sym], "name": f"NIGHT LAB: {sym}", "candles": len(candles)}
        lab_state.history = []
        logging.info(f"Starting run {run_id} for symbol {sym}")"""

text = re.sub(r'        logging\.info\(f"Starting run \{run_id\} for symbol \{sym\}"\)', meta_update, text)

with open("scripts/night_lab.py", "w") as f:
    f.write(text)
