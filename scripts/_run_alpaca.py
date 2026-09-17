import os
from pathlib import Path

import uvicorn

from services.api.config import Settings
from services.api.main import create_app

PID_FILE = Path(__file__).resolve().parents[1] / ".runtime" / "alpaca-paper.pid"


def app_factory():
    settings = Settings(execution_mode="alpaca_paper")
    return create_app(settings, observation_only=False)


if __name__ == "__main__":
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    try:
        uvicorn.run(
            "scripts._run_alpaca:app_factory",
            factory=True,
            host="127.0.0.1",
            port=8000,
            log_level="info",
        )
    finally:
        try:
            if PID_FILE.read_text().strip() == str(os.getpid()):
                PID_FILE.unlink()
        except FileNotFoundError:
            pass
