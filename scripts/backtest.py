"""M4 core CLI: freeze local candles, then replay entirely offline into a JSON report."""

import argparse
from decimal import Decimal
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from packages.domain.backtest import encode, manifest
from packages.domain.paper import PaperConfig
from services.backtesting.artifacts import load_manifest, write_artifact
from services.backtesting.engine import run
from services.backtesting.source import freeze


def main() -> None:
    parser = argparse.ArgumentParser(description="BACKTEST / SIMULAÇÃO HISTÓRICA LOCAL")
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("freeze")
    snapshot.add_argument("--provider", choices=["alpaca", "simulator"], required=True)
    snapshot.add_argument("--symbols", nargs="+", required=True)
    snapshot.add_argument("--initial-cash", type=Decimal, default=Decimal("10000"))
    snapshot.add_argument("--fee-bps", type=Decimal, default=Decimal("1"))
    snapshot.add_argument("--slippage-bps", type=Decimal, default=Decimal("5"))
    snapshot.add_argument("--output", type=Path, required=True)
    replay = commands.add_parser("run")
    replay.add_argument("input", type=Path)
    replay.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "freeze":
            config = PaperConfig(args.initial_cash, args.fee_bps, args.slippage_bps)
            # Settings/DB are needed only here. Replay does not read .env or start a provider.
            from services.api.config import Settings
            from services.api.database import check_database, create_database_engine

            engine = create_database_engine(Settings())
            try:
                if check_database(engine) != "up":
                    raise ValueError("backtest_database_or_schema_unavailable")
                dataset = freeze(engine, args.provider, tuple(args.symbols))
            finally:
                engine.dispose()
            write_artifact(args.output, manifest(dataset, config))
            print(
                encode(
                    {
                        "mode": "BACKTEST",
                        "candles": len(dataset.candles),
                        "dataset_hash": dataset.hash,
                    }
                )
            )
        else:
            if args.input.resolve() == args.output.resolve():
                raise ValueError("backtest_output_cannot_replace_input")
            dataset, config = load_manifest(args.input)
            result = run(dataset, config)
            write_artifact(args.output, result)
            print(encode(result["metrics"]))
    except SQLAlchemyError:
        parser.exit(1, "backtest_database_unavailable\n")
    except (OSError, ValueError, ArithmeticError):
        parser.exit(1, "backtest_invalid_input_or_artifact; no result published\n")


if __name__ == "__main__":
    main()
