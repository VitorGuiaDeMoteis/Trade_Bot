from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Table

from packages.contracts.decisions import RiskResponse, SignalResponse
from packages.contracts.market import CandleResponse
from packages.domain.market import SimulationSpec
from services.api.models import candles, risk_decisions, signals
from services.market_simulator.generator import CandleGenerator
from services.risk_engine.engine import RiskEngine
from services.strategy_engine.engine import BaseStrategy


@pytest.mark.parametrize(
    ("table", "response"),
    [
        (candles, CandleResponse),
        (signals, SignalResponse),
        (risk_decisions, RiskResponse),
    ],
)
def test_response_covers_every_table_column(table: Table, response: type) -> None:
    """Both decisions call sites project whole table rows into extra="forbid" models.

    A column added to a table without the matching response field makes every
    decision listing and every paper dataset build raise at request time, so pin
    the two sides together here instead of discovering it in production.
    """
    assert {c.name for c in table.c} <= set(response.model_fields)


@pytest.mark.parametrize(
    ("close", "kind", "reason"),
    [
        ("101", "BUY", "Fechamento acima da abertura."),
        ("99", "SELL", "Fechamento abaixo da abertura."),
        ("100", "HOLD", "Abertura e fechamento equivalentes. Sem ação."),
    ],
)
def test_deterministic_signal_explanation(close: str, kind: str, reason: str) -> None:
    candle = replace(
        CandleGenerator(SimulationSpec()).next_closed(1),
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("98"),
        close=Decimal(close),
    )
    now = datetime.now(UTC)
    signal = BaseStrategy().process_candle(candle, now)
    repeat = BaseStrategy().process_candle(candle, now)
    assert signal.signal_type == repeat.signal_type == kind
    assert signal.reason == repeat.reason == reason
    assert signal.strategy_version == "v1-deterministic"
    assert signal.candle_id == candle.candle_id
    with pytest.raises(ValueError, match="justificativa"):
        replace(signal, reason=" ")


@pytest.mark.parametrize(
    ("paused", "seconds", "decision", "reason"),
    [
        (False, 0, "APPROVED", "Aprovado pelas regras de risco."),
        (False, 3600, "APPROVED", "Aprovado pelas regras de risco."),
        (False, 3601, "REJECTED", "Sinal vencido (gerado há mais de 1h)."),
        (True, 0, "REJECTED", "Sistema está pausado."),
        (True, 3601, "REJECTED", "Sistema está pausado."),
    ],
)
def test_risk_boundary_and_reasons(paused: bool, seconds: int, decision: str, reason: str) -> None:
    candle = CandleGenerator(SimulationSpec()).next_closed(1)
    now = datetime.now(UTC)
    signal = BaseStrategy().process_candle(candle, now)
    result = RiskEngine().evaluate(signal, now + timedelta(seconds=seconds), paused)
    assert result.decision == decision
    assert result.reason == reason
    assert result.signal_id == signal.signal_id
