"""Offline replay entrypoint. Does not load .env or instantiate any Alpaca component."""

import argparse
from pathlib import Path

import uvicorn

from services.backtesting.artifacts import load_manifest
from services.replay.app import DEFAULT_DATASET, create_replay_app
from services.replay.runtime import SPEEDS


def main() -> None:
    parser = argparse.ArgumentParser(description="REPLAY LIVE — SIMULAÇÃO HISTÓRICA")
    parser.add_argument("--speed", type=float, choices=SPEEDS, default=1)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    dataset, config = load_manifest(args.dataset)
    app = create_replay_app(dataset, config, speed=args.speed, source=args.dataset.name)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
