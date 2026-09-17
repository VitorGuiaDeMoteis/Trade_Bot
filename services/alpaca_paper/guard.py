from decimal import Decimal
from typing import Any


class ExecutionGuard:
    MAX_NOTIONAL_PER_TRADE = Decimal("10.00")
    MAX_TOTAL_EXPOSURE = Decimal("30.00")
    DAILY_LOSS_LIMIT = Decimal("5.00")
    ALLOWED_SYMBOLS = {"SPY", "AAPL", "TSLA"}
    DUST_THRESHOLD_VALUE = Decimal("1.00")

    @classmethod
    def evaluate(
        cls,
        side: str,
        symbol: str,
        positions: list[dict[str, Any]],
        snapshot: dict[str, Any] | None,
        last_equity: Decimal | None = None,
        in_flight: list[dict[str, Any]] | None = None,
        blocked_symbols: list[str] | None = None,
        *,
        state_known: bool = True,
    ) -> tuple[bool, str | None]:
        if not state_known:
            return False, "Broker state desconhecido ou reconciliação incompleta"
        if blocked_symbols is None:
            blocked_symbols = []
        if symbol not in cls.ALLOWED_SYMBOLS:
            return False, f"Ativo {symbol} não permitido na V1"

        if not in_flight:
            in_flight = []

        pending_buys = Decimal("0")
        pending_sells = Decimal("0")
        total_in_flight_exposure = Decimal("0")

        for flight in in_flight:
            if flight["symbol"] == symbol:
                if flight["side"] == "BUY":
                    pending_buys += Decimal("1")  # count of pending BUY orders
                elif flight["side"] == "SELL":
                    pending_sells += Decimal(str(flight.get("quantity", 0)))
            if flight["side"] == "BUY":
                flight_notional = flight.get("requested_notional")
                if flight_notional:
                    total_in_flight_exposure += Decimal(str(flight_notional))

        pos_map = {p["symbol"]: p for p in positions}
        current_pos = pos_map.get(symbol)
        current_mv = (
            Decimal(str(current_pos.get("market_value", "0"))) if current_pos else Decimal("0")
        )
        current_qty = (
            Decimal(str(current_pos.get("qty", current_pos.get("quantity", "0"))))
            if current_pos
            else Decimal("0")
        )

        available_qty = current_qty - pending_sells

        if side == "BUY":
            if snapshot and last_equity:
                equity = Decimal(str(snapshot.get("equity", 0)))
                if last_equity - equity >= cls.DAILY_LOSS_LIMIT:
                    return (
                        False,
                        f"Circuit breaker diário atingido (Perda >= ${cls.DAILY_LOSS_LIMIT})",
                    )
            elif not snapshot or not last_equity:
                # DAILY BREAKER: FAIL CLOSED
                return False, "Equity indisponível para checagem do Daily Breaker"

            if current_pos and current_qty > 0:
                # "NÃO permitir novo BUY se existe qty > 0 do símbolo, mesmo que seja dust."
                return False, "Máximo 1 posição aberta por símbolo (no pyramiding)"

            if pending_buys > 0:
                return False, "Máximo 1 posição aberta por símbolo (no pyramiding) [in-flight]"

            total_exposure = sum(
                Decimal(str(p.get("market_value", 0)))
                for p in positions
                if Decimal(str(p.get("qty", p.get("quantity", 0)))) > 0
            )
            if any(
                flight["side"] == "BUY" and flight.get("requested_notional") is None
                for flight in in_flight
            ):
                return False, "Exposição de BUY in-flight desconhecida"
            if (
                total_exposure + total_in_flight_exposure + cls.MAX_NOTIONAL_PER_TRADE
                > cls.MAX_TOTAL_EXPOSURE
            ):
                return (
                    False,
                    f"Exposição máxima total de ${cls.MAX_TOTAL_EXPOSURE} "
                    "atingida (incluindo in-flight)",
                )

        elif side == "SELL":
            if not current_pos or available_qty <= 0:
                return (
                    False,
                    "Operação vendida a descoberto (SHORT) proibida na V1 (qty indisponível)",
                )
            if symbol in blocked_symbols and current_mv < cls.DUST_THRESHOLD_VALUE:
                return False, f"Posição dust {symbol} bloqueada por rejeição recente."

        return True, None
