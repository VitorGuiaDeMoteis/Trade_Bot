from decimal import Decimal, InvalidOperation
from typing import Any


class ExecutionGuard:
    MAX_NOTIONAL_PER_TRADE = Decimal("10.00")
    MAX_TOTAL_EXPOSURE = Decimal("30.00")
    DAILY_LOSS_LIMIT = Decimal("5.00")
    ALLOWED_SYMBOLS = {"SPY", "AAPL", "TSLA"}
    DUST_THRESHOLD_VALUE = Decimal("1.00")

    @staticmethod
    def _optional_decimal(value: Any) -> Decimal | None:
        """Parse an OPTIONAL broker numeric field.

        Returns None when the field is absent or unparsable so callers can fail
        closed instead of silently substituting a bogus value (e.g. 0).
        """
        if value is None:
            return None
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if not result.is_finite():
            return None
        return result

    @classmethod
    def _net_positions(cls, positions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Collapse the broker's position rows into ONE netted entry per symbol.

        The broker can report the same symbol on more than one row (hedged legs,
        partial lots). Collapsing them with a last-row-wins map made every
        verdict below depend on the ORDER the broker happened to list rows in,
        and disagreed with `PaperAlpacaWorker`, which nets all rows for a symbol
        before sizing a SELL -- two components holding two different numbers for
        the SAME position. Netting here keeps one definition of a position.

        `*_known` reports whether EVERY row for that symbol yielded a usable
        number. One unsourceable leg makes the net unknown: inventing the
        missing leg as 0 would state a position the broker never reported, so
        callers fail closed on it.
        """
        netted: dict[str, dict[str, Any]] = {}
        for position in positions:
            symbol = position.get("symbol")
            if not isinstance(symbol, str) or not symbol:
                # Unattributable row: `evaluate` rejects the payload before
                # reaching here, so netting it is defensive only.
                continue
            entry = netted.setdefault(
                symbol,
                {
                    "qty": Decimal("0"),
                    "market_value": Decimal("0"),
                    "qty_known": True,
                    "market_value_known": True,
                },
            )
            qty = cls._optional_decimal(position.get("qty", position.get("quantity")))
            if qty is None:
                entry["qty_known"] = False
            else:
                entry["qty"] += qty
            market_value = cls._optional_decimal(position.get("market_value"))
            if market_value is None:
                entry["market_value_known"] = False
            else:
                entry["market_value"] += market_value
        return netted

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
        unknown_in_flight_sell_qty = False
        unknown_in_flight_buy_notional = False

        for flight in in_flight:
            flight_side = flight.get("side")
            if flight["symbol"] == symbol:
                if flight_side == "BUY":
                    pending_buys += Decimal("1")  # count of pending BUY orders
                elif flight_side == "SELL":
                    # A pending SELL with an unsourceable quantity must NOT be
                    # treated as zero: doing so overstates how much of the
                    # position is still available and allows a second SELL that
                    # oversells into a short position.
                    flight_qty = cls._optional_decimal(flight.get("quantity"))
                    if flight_qty is None:
                        unknown_in_flight_sell_qty = True
                    else:
                        pending_sells += flight_qty
            if flight_side == "BUY":
                flight_notional = cls._optional_decimal(flight.get("requested_notional"))
                if flight_notional is not None:
                    total_in_flight_exposure += flight_notional
                else:
                    unknown_in_flight_buy_notional = True

        net_positions = cls._net_positions(positions)
        current_pos = net_positions.get(symbol)
        # Same rule for the symbol being traded: an open position whose qty or
        # market_value cannot be sourced makes both the pyramiding check and the
        # exposure sum unusable, so it is reported as unknown instead of zero.
        current_qty_raw = current_mv_raw = None
        if current_pos is not None:
            current_qty_raw = (
                current_pos["qty"] if current_pos["qty_known"] else None
            )
            current_mv_raw = (
                current_pos["market_value"]
                if current_pos["market_value_known"]
                else None
            )
        current_mv = current_mv_raw if current_mv_raw is not None else Decimal("0")
        current_qty = current_qty_raw if current_qty_raw is not None else Decimal("0")

        # Quantity is required by BOTH branches: BUY needs it for the pyramiding
        # check, SELL needs it to prove a position exists. market_value is only
        # required for BUY (exposure); a SELL must keep working when it is absent.
        if current_pos is not None and current_qty_raw is None:
            return False, f"Quantidade da posição {symbol} indisponível"
        if side == "BUY" and current_pos is not None and current_mv_raw is None:
            return False, f"Valor de mercado da posição {symbol} indisponível"

        available_qty = current_qty - pending_sells

        if side == "BUY":
            # DAILY BREAKER: both sides of the delta must be independently sourced.
            # A missing/unparsable current equity must NOT be coerced to 0: that
            # would compare a real baseline against an invented value, and for any
            # last_equity below DAILY_LOSS_LIMIT the delta stays under the limit and
            # the breaker is silently bypassed. Fail closed instead.
            # Both fail-closed paths below keep the shared "Equity indisponível"
            # prefix, but name WHICH side of the delta was unsourceable. The two
            # causes have different remediations (a missing broker `last_equity`
            # baseline vs a missing/unparsable current `equity`), and an operator
            # reading only the rejection reason could not tell them apart.
            if not last_equity:
                return False, (
                    "Equity indisponível para checagem do Daily Breaker "
                    "(baseline last_equity ausente ou inválido)"
                )
            equity = cls._optional_decimal(snapshot.get("equity")) if snapshot else None
            if equity is None:
                return False, (
                    "Equity indisponível para checagem do Daily Breaker "
                    "(equity atual ausente ou inválido no snapshot da corretora)"
                )
            if last_equity - equity >= cls.DAILY_LOSS_LIMIT:
                return (
                    False,
                    f"Circuit breaker diário atingido (Perda >= ${cls.DAILY_LOSS_LIMIT})",
                )

            if current_pos and current_qty > 0:
                # "NÃO permitir novo BUY se existe qty > 0 do símbolo, mesmo que seja dust."
                return False, "Máximo 1 posição aberta por símbolo (no pyramiding)"

            if pending_buys > 0:
                return False, "Máximo 1 posição aberta por símbolo (no pyramiding) [in-flight]"

            # Exposure is summed from the NETTED map, one entry per symbol. The
            # broker can list a symbol on several rows (hedged legs, partial
            # lots); adding each row's market_value GROSS charged a hedged pair
            # for exposure it did not hold and tripped the cap for the wrong
            # reason. Fail-closed rules are unchanged -- an unsourceable qty or
            # market_value on ANY leg still refuses the BUY.
            total_exposure = Decimal("0")
            for position_symbol, net in net_positions.items():
                if not net["qty_known"]:
                    # Cannot tell whether this position holds exposure, so it
                    # cannot be excluded from the cap without failing open.
                    return False, (
                        f"Quantidade da posição {position_symbol} "
                        "indisponível para o cálculo de exposição"
                    )
                if net["qty"] > 0:
                    if not net["market_value_known"]:
                        return False, (
                            f"Exposição da posição {position_symbol} indisponível"
                        )
                    total_exposure += net["market_value"]
            if unknown_in_flight_buy_notional:
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
            if unknown_in_flight_sell_qty:
                return False, (
                    f"Quantidade de SELL in-flight desconhecida para {symbol} "
                    "(risco de venda a descoberto)"
                )
            if not current_pos or available_qty <= 0:
                return (
                    False,
                    "Operação vendida a descoberto (SHORT) proibida na V1 (qty indisponível)",
                )
            if symbol in blocked_symbols and current_mv < cls.DUST_THRESHOLD_VALUE:
                return False, f"Posição dust {symbol} bloqueada por rejeição recente."

        return True, None
