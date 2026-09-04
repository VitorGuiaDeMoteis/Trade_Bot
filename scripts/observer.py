"""Explicit local Observer CLI; no automatic AI execution in FastAPI's lifecycle."""

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from packages.contracts.observer import MAX_INPUT_BYTES, AIObserverSnapshot, canonical
from services.api.database import check_database
from services.api.observer_database import create_observer_database
from services.api.observer_source import collect
from services.api.observer_store import analyze
from services.backtesting.artifacts import write_artifact
from services.observer.isolated import IsolatedProvider
from services.observer.provider import FakeProvider, ModelProvider
from services.observer.real import RealIsolatedProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="M5 Observer: análise sem autoridade de execução")
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot")
    snapshot.add_argument("--as-of", type=datetime.fromisoformat, required=True)
    snapshot.add_argument("--provider", choices=["alpaca", "simulator"], required=True)
    snapshot.add_argument("--symbols", nargs="+", required=True)
    snapshot.add_argument(
        "--session-state",
        choices=["connected", "market_closed", "delayed", "degraded", "offline"],
        default="offline",
    )
    snapshot.add_argument("--output", type=Path, required=True)
    snapshot.add_argument("--backtest", type=Path)
    snapshot.add_argument("--accepted-hash")
    run = commands.add_parser("analyze")
    run.add_argument("input", type=Path)
    run.add_argument("--analysis-id", type=UUID, required=True)
    run.add_argument("--enabled", action="store_true")
    run.add_argument("--timeout", type=float, default=2)
    run.add_argument("--image", help="Optional prebuilt, reviewed OCI image sha256 digest")
    run.add_argument("--real-image", help="Reviewed offline deepseek OCI image sha256 digest")
    run.add_argument(
        "--real-gpu", action="store_true", help="Reviewed GPU image on existing device 0"
    )
    args = parser.parse_args()
    engine = create_observer_database()
    try:
        if check_database(engine) != "up":
            raise ValueError("observer_schema_unavailable")
        if args.command == "snapshot":
            accepted = None
            if args.backtest:
                from services.api.backtest_routes import _load_and_validate_report

                accepted = _load_and_validate_report(args.backtest)
                if accepted["result_hash"] != args.accepted_hash:
                    raise ValueError("observer_backtest_not_accepted")
            value = collect(
                engine,
                as_of=args.as_of,
                provider=args.provider,
                session_state=args.session_state,
                symbols=tuple(args.symbols),
                accepted_report=accepted,
            )
            write_artifact(args.output, json.loads(value.payload()))
            print(
                canonical({"input_hash": value.input_hash, "bytes": len(value.payload())}).decode()
            )
        else:
            provider: ModelProvider = FakeProvider()
            if args.real_gpu and not args.real_image:
                raise ValueError("observer_gpu_requires_real_image")
            if args.image and args.real_image:
                raise ValueError("observer_choose_one_profile")
            if args.real_image:
                docker = shutil.which("docker")
                provider = RealIsolatedProvider(
                    Path(docker).resolve() if docker else None, args.real_image, gpu=args.real_gpu
                )
            if args.image:
                docker = shutil.which("docker")
                provider = IsolatedProvider(Path(docker).resolve() if docker else None, args.image)
            try:
                with args.input.open("rb") as input_file:
                    data = input_file.read(MAX_INPUT_BYTES + 1)
                if len(data) > MAX_INPUT_BYTES:
                    raise ValueError("observer_snapshot_too_large")
                value_or_none = AIObserverSnapshot.model_validate_json(data)
                value_or_none.payload()
            except (OSError, ValueError):
                value_or_none = None
            result = analyze(
                engine,
                args.analysis_id,
                value_or_none,
                provider,
                enabled=args.enabled,
                timeout=args.timeout,
            )
            print(
                canonical(
                    {
                        "analysis_id": str(result["analysis_id"]),
                        "status": result["status"],
                        "fallback": result["fallback"],
                        "error_code": result["error_code"],
                    }
                ).decode()
            )
    except (ValueError, OSError, SQLAlchemyError):
        parser.exit(1, "observer_operation_failed; no financial change\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
