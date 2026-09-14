"""Run with: .venv/bin/python -m scripts.mission_control"""

import uvicorn
from fastapi import FastAPI

from services.api.config import Settings
from services.api.main import create_app


def create_observation_app() -> FastAPI:
    settings = Settings(execution_mode="alpaca_paper")
    return create_app(settings, observation_only=True)


if __name__ == "__main__":
    uvicorn.run(
        "scripts.mission_control:create_observation_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )
