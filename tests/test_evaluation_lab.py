import os
import time
import json
import subprocess
from pathlib import Path

def test_evaluation_lab_interruption(tmp_path):
    env = os.environ.copy()
    
    # Start the process
    process = subprocess.Popen(
        ["python", "scripts/evaluation_lab.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Let it run for 10 seconds to generate some output and progress
    time.sleep(10)
    
    # Send SIGINT (Ctrl+C)
    process.send_signal(subprocess.signal.SIGINT)
    
    # Wait for it to finish gracefully
    stdout, stderr = process.communicate(timeout=15)
    
    # Find the evaluations directory (newest one)
    eval_dir = Path("evaluations")
    subdirs = sorted([d for d in eval_dir.iterdir() if d.is_dir()], key=os.path.getmtime)
    assert len(subdirs) > 0, "No evaluation directory created"
    
    latest_run = subdirs[-1]
    
    # Verify progress.json
    progress_file = latest_run / "progress.json"
    assert progress_file.exists()
    
    with open(progress_file, "r") as f:
        progress = json.load(f)
        
    assert progress["status"] == "INTERRUPTED", f"Status should be INTERRUPTED, got {progress['status']}"
    assert progress["current_candle"] > 0, "No candles processed"
    
    # Verify other files exist
    pass # observations.jsonl might not be created if no AI call finished
    assert (latest_run / "labeled_trades.csv").exists(), "labeled_trades.csv missing"
    
    # Try reading the CSV
    with open(latest_run / "labeled_trades.csv", "r") as f:
        header = f.readline()
        assert "symbol,split,timestamp" in header
        
    # Check if report generated
    assert (latest_run / "report.md").exists() or progress["trades"] == 0, "Report missing despite trades"

