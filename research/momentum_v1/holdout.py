"""One-shot final holdout orchestration."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable

import pandas as pd

from research.momentum_v1.data import load_market_data
from research.momentum_v1.gates import evaluate_gates
from research.momentum_v1.micro_replay import run_micro_replay
from research.momentum_v1.run_experiments import (
    confidence_intervals,
    regime_metrics,
    run_core,
    run_sensitivity_matrix,
    run_substitutions,
)
from research.momentum_v1.seal import ResearchPaths, load_config, verify_seal

Evaluator = Callable[[ResearchPaths, dict[str, object], dict[str, object]], dict[str, object]]


def _period(config: dict[str, object], name: str) -> tuple[str, str]:
    periods = config.get("periods")
    if not isinstance(periods, dict) or not isinstance(periods.get(name), dict):
        raise KeyError(name)
    selected = periods[name]
    return str(selected["start"]), str(selected["end"])


def _numeric(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Expected numeric metric")
    return float(value)


def _micro_summary(data: pd.DataFrame, result: object, universe: list[str], config: dict[str, object]) -> dict[str, object]:
    from research.momentum_v1.engine import BacktestResult

    if not isinstance(result, BacktestResult):
        raise TypeError("Winner result must be a BacktestResult")
    micro_config = config.get("micro_replay")
    if not isinstance(micro_config, dict):
        raise TypeError("config.micro_replay must be an object")
    targets = result.target_weights.dropna(how="all").fillna(0.0)
    replay = run_micro_replay(
        data,
        universe,
        targets,
        initial_capital=_numeric(micro_config["initial_capital"]),
        min_notional=_numeric(micro_config["minimum_notional"]),
        frac_precision=int(_numeric(micro_config["fractional_precision"])),
    )
    records = replay.records
    below_minimum = int(records["orders_below_minimum"].sum())
    executable = below_minimum == 0 and float(records["cash_residual"].min()) >= -0.01
    return {
        "EXECUTABLE_WITH_50_USD": "YES" if executable else "NO",
        "reason": "All target orders clear the minimum and rounding remains cash-safe."
        if executable
        else "At least one target order is below minimum or rounding exhausts cash.",
        "last_position_dollars": replay.position_dollars.iloc[-1].to_dict(),
        "last_fractional_quantities": replay.quantities.iloc[-1].to_dict(),
        "orders_below_minimum": below_minimum,
        "total_rounding_residual": float(records["rounding_residual"].sum()),
        "average_cash_residual": float(records["cash_residual"].mean()),
        "max_cash_residual": float(records["cash_residual"].max()),
        "average_effective_positions": float(records["effective_positions"].mean()),
        "turnover_dollars": float(records["turnover_dollars"].sum()),
        "average_turnover_pct": float(records["turnover_pct"].mean()),
        "average_friction_pct_nav": float(records["friction_pct_nav"].mean()),
        "tracking_error": float(records["tracking_error"].mean()),
    }


def evaluate_real_holdout(paths: ResearchPaths, config: dict[str, object], seal_data: dict[str, object]) -> dict[str, object]:
    start, end = _period(config, "holdout")
    if (start, end) != ("2021-01-01", "2025-12-31"):
        raise ValueError("Holdout bounds differ from the frozen protocol")
    universe_value = config.get("universe")
    if not isinstance(universe_value, list):
        raise TypeError("config.universe must be a list")
    universe = [str(symbol) for symbol in universe_value]
    data = load_market_data(paths.artifacts)
    bundle = run_core(data, universe, start, end)
    robustness = run_sensitivity_matrix(data, universe, start, end)
    substitutes = pd.read_parquet(paths.artifacts / "substitutes.parquet")
    substitutions = run_substitutions(data, substitutes, universe, start, end)
    regimes = regime_metrics(data, bundle, start, end)
    bootstrap_config = config.get("bootstrap")
    if not isinstance(bootstrap_config, dict):
        raise TypeError("config.bootstrap must be an object")
    intervals = confidence_intervals(
        bundle,
        str(seal_data["protocol_seal_hash"]),
        int(_numeric(bootstrap_config["samples"])),
        int(_numeric(bootstrap_config["block_size_months"])),
    )
    gates = evaluate_gates(bundle.metrics, robustness, substitutions)
    decision = str(gates["final_decision"])
    micro: dict[str, object] | None = None
    if decision in {"AM", "RAM"}:
        micro = _micro_summary(data, bundle.results[decision], universe, config)
    return {
        "period": {"start": start, "end": end},
        "metrics": bundle.metrics,
        "confidence_intervals_95": intervals,
        "robustness": robustness,
        "substitutions": substitutions,
        "regimes": regimes,
        "gates": gates,
        "micro_50": micro,
    }


def _format_metric(value: object) -> str:
    return value if isinstance(value, str) else f"{_numeric(value):.6f}"


def _render_result(result: dict[str, object], seal_data: dict[str, object], marker: dict[str, object]) -> str:
    metrics = result["metrics"]
    gates = result["gates"]
    if not isinstance(metrics, dict) or not isinstance(gates, dict):
        raise TypeError("Malformed holdout result")
    columns = [
        "CAGR",
        "Sharpe",
        "Sortino",
        "MaxDD",
        "Calmar",
        "Ann_Vol",
        "Worst_12m",
        "Annual_Turnover",
        "Trades_Per_Year",
        "Cash_Pct",
        "Average_Positions",
    ]
    lines = [
        "# Momentum Experiment V1.3 — Final Result",
        "",
        f"Protocol seal: `{seal_data['protocol_seal_hash']}`",
        f"Holdout opened: `{marker['opened_at']}`",
        "",
        "## Sealed manifest",
        "",
        "```json",
        json.dumps(seal_data, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Holdout marker",
        "",
        "```json",
        json.dumps(marker, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Holdout metrics",
        "",
        "| Strategy | " + " | ".join(columns) + " |",
        "|---|" + "---:|" * len(columns),
    ]
    for name in ("B0", "B1", "B2", "AM", "RAM"):
        row = metrics[name]
        if not isinstance(row, dict):
            raise TypeError("Malformed strategy metrics")
        lines.append(f"| {name} | " + " | ".join(_format_metric(row[column]) for column in columns) + " |")
    lines.extend(["", "## AM gates", ""])
    am_gates = gates["am_gates"]
    if isinstance(am_gates, dict):
        lines.extend(f"- {'PASS' if value else 'FAIL'} — {name}" for name, value in am_gates.items())
    lines.extend(["", "## RAM gates", ""])
    ram_gates = gates["ram_gates"]
    if isinstance(ram_gates, dict):
        lines.extend(f"- {('PASS' if value is True else 'FAIL' if value is False else value)} — {name}" for name, value in ram_gates.items())
    lines.extend(
        [
            "",
            "## Final decision",
            "",
            str(gates["final_decision"]),
            "",
            "## $50 micro-capital replay",
            "",
            json.dumps(result.get("micro_50"), indent=2, ensure_ascii=False),
            "",
            "## Known limitations",
            "",
            "- Yahoo adjusted history can be revised by the provider.",
            "- Alpaca is a cross-check over its available overlap, not the primary source.",
            "- DTB3 cash accrual uses the same canonical series for B0 and excess-return metrics.",
            "- The engine models next-session-open execution and pre-registered friction, not intraday market impact.",
            "",
            "Paper V1 and its running worktree were untouched. No broker orders were sent.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_final_reports(paths: ResearchPaths, result: dict[str, object], seal_data: dict[str, object], marker: dict[str, object]) -> None:
    rendered = _render_result(result, seal_data, marker)
    (paths.root / "MOMENTUM_EXP1_FINAL_RESULT.md").write_text(rendered, encoding="utf-8")
    gates = result.get("gates")
    if not isinstance(gates, dict):
        raise TypeError("Malformed holdout gates")
    handoff = (
        "# Momentum Experiment V1.3 — Final Handoff\n\n"
        f"Seal: `{seal_data['protocol_seal_hash']}`\n\n"
        f"Holdout marker: `{marker['opened_at']}` (`{marker['status']}`)\n\n"
        f"Decision: **{gates['final_decision']}**\n\n"
        "See `MOMENTUM_EXP1_FINAL_RESULT.md` and the immutable artifacts under `.artifacts/research/momentum_v1/`.\n\n"
        "Paper V1 was untouched. No order or LIVE trading endpoint was used.\n"
    )
    (paths.root / "MOMENTUM_EXP1_FINAL_HANDOFF.md").write_text(handoff, encoding="utf-8")


def open_holdout(paths: ResearchPaths, evaluator: Evaluator = evaluate_real_holdout) -> dict[str, object]:
    if paths.marker.exists():
        raise RuntimeError("HOLDOUT_ALREADY_BURNED")
    seal_data = verify_seal(paths)
    manifest = seal_data["manifest"]
    if not isinstance(manifest, dict):
        raise TypeError("Malformed seal manifest")
    marker: dict[str, object] = {
        "opened_at": dt.datetime.now(dt.UTC).isoformat(),
        "status": "OPENED",
        "protocol_seal_hash": seal_data["protocol_seal_hash"],
        "source_tree_hash": manifest["source_tree_hash"],
        "config_hash": manifest["config_hash"],
        "dataset_hashes": {
            "primary": manifest["primary_dataset_hash"],
            "fred": manifest["fred_hash"],
            "crosscheck": manifest["crosscheck_hashes"],
            "substitutions": manifest["substitution_dataset_hashes"],
        },
        "base_git_sha": manifest["base_git_sha"],
    }
    paths.marker.write_text(json.dumps(marker, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        result = evaluator(paths, load_config(paths), seal_data)
        output = {
            "protocol_seal_hash": seal_data["protocol_seal_hash"],
            "holdout_opened": marker,
            **result,
        }
        (paths.artifacts / "holdout_results.json").write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        marker["status"] = "COMPLETED"
        paths.marker.write_text(json.dumps(marker, indent=2, ensure_ascii=False), encoding="utf-8")
        if evaluator is evaluate_real_holdout:
            _write_final_reports(paths, output, seal_data, marker)
        return output
    except Exception as error:
        marker["status"] = "FAILED"
        marker["error"] = f"{type(error).__name__}: {error}"
        paths.marker.write_text(json.dumps(marker, indent=2, ensure_ascii=False), encoding="utf-8")
        raise
