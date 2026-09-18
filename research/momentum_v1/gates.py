"""Mechanical evaluation of the pre-registered holdout gates."""

from __future__ import annotations

from typing import cast

from research.momentum_v1.metrics import MetricValue

type GateValue = bool | str


def _number(metrics: dict[str, MetricValue], name: str) -> float:
    value = metrics[name]
    if isinstance(value, str):
        raise TypeError(f"{name} is a status value, not numeric")
    return value


def _core_am(am: dict[str, MetricValue], b1: dict[str, MetricValue]) -> bool:
    return (
        _number(am, "Sharpe") > _number(b1, "Sharpe") + 0.15
        and _number(am, "MaxDD") < 0.70 * _number(b1, "MaxDD")
        and _number(am, "Calmar") > _number(b1, "Calmar")
    )


def _group(robustness: dict[str, object], name: str) -> dict[str, dict[str, MetricValue]]:
    value = robustness.get(name)
    if not isinstance(value, dict) or not all(isinstance(item, dict) for item in value.values()):
        raise TypeError(f"Malformed robustness group: {name}")
    return cast(dict[str, dict[str, MetricValue]], value)


def _nested_group(robustness: dict[str, object], name: str) -> dict[str, dict[str, dict[str, MetricValue]]]:
    value = robustness.get(name)
    if not isinstance(value, dict):
        raise TypeError(f"Malformed robustness group: {name}")
    if not all(isinstance(inner, dict) and all(isinstance(item, dict) for item in inner.values()) for inner in value.values()):
        raise TypeError(f"Malformed nested robustness group: {name}")
    return cast(dict[str, dict[str, dict[str, MetricValue]]], value)


def evaluate_gates(
    metrics: dict[str, dict[str, MetricValue]],
    robustness: dict[str, object],
    substitutions: dict[str, dict[str, object]],
) -> dict[str, object]:
    am = metrics["AM"]
    ram = metrics["RAM"]
    b1 = metrics["B1"]
    am_sharpe = _number(am, "Sharpe")
    ram_sharpe = _number(ram, "Sharpe")

    costs = _nested_group(robustness, "costs")
    am_sensitivities = _group(robustness, "am")
    lookbacks = _group(robustness, "lookbacks")
    leave_one_out = _group(robustness, "leave_one_out")
    ram_sensitivities = _group(robustness, "ram")
    cost_10 = costs["10"]
    sensitivity_support = sum(_core_am(candidate, b1) for candidate in am_sensitivities.values())
    lookback_sharpes = {key: _number(value, "Sharpe") for key, value in lookbacks.items()}
    isolated_12m_peak = lookback_sharpes["12"] > lookback_sharpes["10"] and lookback_sharpes["12"] > lookback_sharpes["14"]

    substitution_stable = True
    for item in substitutions.values():
        baseline = item["AM_baseline"]
        replacement = item["AM_substitution"]
        if not isinstance(baseline, dict) or not isinstance(replacement, dict):
            raise TypeError("Malformed substitution metrics")
        baseline_sharpe = _number(baseline, "Sharpe")
        replacement_sharpe = _number(replacement, "Sharpe")
        if baseline_sharpe * replacement_sharpe < 0.0 or _number(replacement, "MaxDD") > 0.20:
            substitution_stable = False

    loo_reductions = {
        symbol: (am_sharpe - _number(candidate, "Sharpe")) / abs(am_sharpe) if am_sharpe != 0.0 else float("inf")
        for symbol, candidate in leave_one_out.items()
    }
    loo_hard_stop = any(reduction > 0.50 for reduction in loo_reductions.values())
    am_hard_stops = {
        "Sharpe >= 0.30": am_sharpe >= 0.30,
        "MaxDD <= 20%": _number(am, "MaxDD") <= 0.20,
        "No leave-one-out Sharpe reduction >50%": not loo_hard_stop,
    }
    am_gates: dict[str, bool] = {
        "Sharpe_AM > Sharpe_B1 + 0.15": am_sharpe > _number(b1, "Sharpe") + 0.15,
        "MaxDD_AM < 0.70 * MaxDD_B1": _number(am, "MaxDD") < 0.70 * _number(b1, "MaxDD"),
        "Calmar_AM > Calmar_B1": _number(am, "Calmar") > _number(b1, "Calmar"),
        "Survives 10 bps round-trip": _core_am(cost_10["AM"], cost_10["B1"]),
        "ETF substitutions structurally stable": substitution_stable,
        "10m/12m/14m has no isolated 12m peak": not isolated_12m_peak,
        ">=2 AM sensitivities support core conclusion": sensitivity_support >= 2,
        **am_hard_stops,
    }
    am_pass = all(am_gates.values())

    if not am_pass:
        ram_gates: dict[str, GateValue] = {
            "Sharpe_RAM > Sharpe_AM + 0.10": "NOT_APPLICABLE",
            "MaxDD_RAM < 1.30 * MaxDD_AM": "NOT_APPLICABLE",
            "K=3 robust vs K=2/K=4": "NOT_APPLICABLE",
            "Extra turnover justified by extra Sharpe": "NOT_APPLICABLE",
            "RAM MaxDD <=25%": "NOT_APPLICABLE",
        }
        ram_pass = False
    else:
        k2 = _number(ram_sensitivities["R1"], "Sharpe")
        k4 = _number(ram_sensitivities["R2"], "Sharpe")
        k3_isolated_peak = ram_sharpe > k2 and ram_sharpe > k4
        extra_turnover = _number(ram, "Annual_Turnover") - _number(am, "Annual_Turnover")
        ram_gates = {
            "Sharpe_RAM > Sharpe_AM + 0.10": ram_sharpe > am_sharpe + 0.10,
            "MaxDD_RAM < 1.30 * MaxDD_AM": _number(ram, "MaxDD") < 1.30 * _number(am, "MaxDD"),
            "K=3 robust vs K=2/K=4": not k3_isolated_peak,
            "Extra turnover justified by extra Sharpe": extra_turnover <= 0.0 or ram_sharpe > am_sharpe + 0.10,
            "RAM MaxDD <=25%": _number(ram, "MaxDD") <= 0.25,
        }
        ram_pass = all(value is True for value in ram_gates.values())

    decision = "RAM" if am_pass and ram_pass else "AM" if am_pass else "MOMENTUM — NO EDGE"
    return {
        "am_gates": am_gates,
        "am_pass": am_pass,
        "am_sensitivity_support_count": sensitivity_support,
        "leave_one_out_sharpe_reductions": loo_reductions,
        "ram_gates": ram_gates,
        "ram_pass": ram_pass,
        "final_decision": decision,
    }
