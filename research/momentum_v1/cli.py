"""Official Momentum Experiment V1.3 command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import typer

from research.momentum_v1.data import fetch_data, load_market_data
from research.momentum_v1.holdout import open_holdout
from research.momentum_v1.run_experiments import regime_metrics, run_public_period, run_sensitivity_matrix, run_substitutions
from research.momentum_v1.seal import ResearchPaths, create_seal, current_manifest_state, load_config, verify_seal

app = typer.Typer(no_args_is_help=True, help="Momentum Experiment V1.3 research-only CLI")


def _paths() -> ResearchPaths:
    return ResearchPaths.default()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


@app.command()
def fetch() -> None:
    """Fetch Yahoo primary, FRED cash, substitutions, and Alpaca cross-check data."""
    paths = _paths()
    fetch_data(paths.config, paths.artifacts)
    typer.echo("FETCH_COMPLETE")


@app.command()
def dev() -> None:
    """Run only the frozen 2007-2016 development period."""
    paths = _paths()
    config = load_config(paths)
    data = load_market_data(paths.artifacts)
    bundle = run_public_period(data, config, "development")
    output = {"period": "development", "metrics": bundle.metrics}
    _write_json(paths.artifacts / "dev_results.json", output)
    typer.echo(json.dumps(output, indent=2, ensure_ascii=False))


@app.command()
def diagnostic() -> None:
    """Run only the frozen 2017-2020 burned diagnostic period."""
    paths = _paths()
    config = load_config(paths)
    data = load_market_data(paths.artifacts)
    bundle = run_public_period(data, config, "diagnostic")
    periods = config["periods"]
    universe_value = config["universe"]
    if not isinstance(periods, dict) or not isinstance(periods.get("diagnostic"), dict) or not isinstance(universe_value, list):
        raise TypeError("Malformed research config")
    selected = periods["diagnostic"]
    start, end = str(selected["start"]), str(selected["end"])
    universe = [str(symbol) for symbol in universe_value]
    robustness = run_sensitivity_matrix(data, universe, start, end)
    substitutes = pd.read_parquet(paths.artifacts / "substitutes.parquet")
    output = {
        "period": "burned_diagnostic",
        "metrics": bundle.metrics,
        "robustness": robustness,
        "substitutions": run_substitutions(data, substitutes, universe, start, end),
        "regimes": regime_metrics(data, bundle, start, end),
    }
    _write_json(paths.artifacts / "diagnostic_results.json", output)
    typer.echo(json.dumps(output, indent=2, ensure_ascii=False))


@app.command("manifest-preview")
def manifest_preview() -> None:
    """Print current hashes without creating a seal."""
    typer.echo(json.dumps(current_manifest_state(_paths()), indent=2, ensure_ascii=False))


@app.command()
def seal() -> None:
    """Create the official immutable-input seal."""
    typer.echo(json.dumps(create_seal(_paths()), indent=2, ensure_ascii=False))


@app.command("verify-seal")
def verify_seal_command() -> None:
    """Verify that every sealed input still matches."""
    typer.echo(json.dumps(verify_seal(_paths()), indent=2, ensure_ascii=False))


@app.command()
def holdout() -> None:
    """Open the 2021-2025 final holdout exactly once."""
    result = open_holdout(_paths())
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
