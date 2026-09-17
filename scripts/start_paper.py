import uvicorn
from fastapi import FastAPI
from services.api.config import Settings
from services.api.main import create_app

def create_active_paper_app() -> FastAPI:
    settings = Settings(execution_mode="alpaca_paper")
    # By default observation_only is False
    return create_app(settings)

if __name__ == "__main__":
    uvicorn.run(
        "scripts.start_paper:create_active_paper_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )
