from dataclasses import dataclass
from typing import Any


@dataclass
class GatesResult:
    passed: bool
    gates: dict[str, bool]
    details: dict[str, Any]


def evaluate_gates(
    primary_metrics: dict[str, float],
    b1_metrics: dict[str, float],
    cost_2x_metrics: dict[str, float],
    substitutions_passed: bool,
    leave_one_out_passed: bool,
    sensitivities_passed: int,
) -> GatesResult:

    gates = {}

    # 1. Sharpe > B1 Sharpe + 0.15
    b1_sharpe = float(b1_metrics.get("Sharpe", 0.0))
    p_sharpe = float(primary_metrics.get("Sharpe", 0.0))
    gates["G1_Sharpe_Premium"] = p_sharpe > (b1_sharpe + 0.15)

    # 2. MaxDD < 0.70 * B1 MaxDD
    b1_maxdd = float(b1_metrics.get("MaxDD", 1.0))
    p_maxdd = float(primary_metrics.get("MaxDD", 1.0))
    gates["G2_MaxDD_Relative"] = p_maxdd < (0.70 * b1_maxdd)

    # 3. MaxDD < 25%
    gates["G3_MaxDD_Absolute"] = p_maxdd < 0.25

    # 4. Calmar > B1 Calmar
    b1_calmar = float(b1_metrics.get("Calmar", 0.0))
    p_calmar = float(primary_metrics.get("Calmar", 0.0))
    gates["G4_Calmar"] = p_calmar > b1_calmar

    # 5. survives 2x costs
    cost2x_sharpe = float(cost_2x_metrics.get("Sharpe", 0.0))
    cost2x_maxdd = float(cost_2x_metrics.get("MaxDD", 1.0))
    # Survive implies Sharpe > B1 Sharpe and MaxDD < 25%? The rule doesn't define "survives",
    # but based on sensitivity: Sharpe > B1 AND MaxDD < 25%.
    gates["G5_Cost2x"] = (cost2x_sharpe > b1_sharpe) and (cost2x_maxdd < 0.25)

    # 6. ETF substitution stability
    gates["G6_Substitutions"] = substitutions_passed

    # 7. leave-one-out stability
    gates["G7_LeaveOneOut"] = leave_one_out_passed

    # 8. >=4/6 sensitivity variants supportive
    gates["G8_Sensitivities"] = sensitivities_passed >= 4

    passed = all(gates.values())

    return GatesResult(
        passed=passed,
        gates=gates,
        details={
            "primary_sharpe": p_sharpe,
            "b1_sharpe": b1_sharpe,
            "primary_maxdd": p_maxdd,
            "b1_maxdd": b1_maxdd,
            "primary_calmar": p_calmar,
            "b1_calmar": b1_calmar,
            "cost2x_sharpe": cost2x_sharpe,
            "cost2x_maxdd": cost2x_maxdd,
            "sensitivities_passed": sensitivities_passed,
        },
    )
