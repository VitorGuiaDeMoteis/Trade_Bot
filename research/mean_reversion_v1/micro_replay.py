from dataclasses import dataclass


@dataclass
class MicroReplayEngine:
    capital: float = 50.0
    min_order: float = 1.0
    precision: int = 6

    def calculate_order(self, price: float, target_value: float) -> float:
        if target_value < self.min_order:
            return 0.0

        qty = target_value / price
        return round(qty, self.precision)
