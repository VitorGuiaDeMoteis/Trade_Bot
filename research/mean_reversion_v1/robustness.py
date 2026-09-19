def get_substitutions() -> dict[str, str]:
    return {"SPY": "VOO", "IWM": "VTWO", "EFA": "VEA", "EEM": "IEMG"}


def generate_leave_one_out_universes(base_universe: list[str]) -> list[list[str]]:
    universes = []
    for i in range(len(base_universe)):
        sub = base_universe.copy()
        sub.pop(i)
        universes.append(sub)
    return universes


def get_qqq_robustness_universe() -> list[str]:
    # 5 ETFs, 20% each
    return ["SPY", "IWM", "EFA", "EEM", "QQQ"]
