"""Conservative initial allocation, including transaction costs in the 10% cap."""

from decimal import ROUND_FLOOR, Decimal

from packages.domain.paper import ZERO, money


def entry_quantity(equity: Decimal, fill_price: Decimal, fee_bps: Decimal) -> int:
    if equity <= ZERO or fill_price <= ZERO:
        return 0
    budget = money(equity * Decimal("0.10"))
    unit_cost = fill_price * (Decimal("1") + fee_bps / Decimal("10000"))
    quantity = int((budget / unit_cost).to_integral_value(rounding=ROUND_FLOOR))
    # Fee rounding must never cross the allocation ceiling.
    while (
        quantity
        and money(fill_price * quantity) + money(fill_price * quantity * fee_bps / Decimal("10000"))
        > budget
    ):
        quantity -= 1
    return quantity
