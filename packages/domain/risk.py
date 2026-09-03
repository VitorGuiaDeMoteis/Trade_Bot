"""Definição de domínio para Decisões do Motor de Risco."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

DecisionType = Literal["APPROVED", "REJECTED"]


@dataclass(frozen=True)
class RiskDecision:
    decision_id: UUID
    signal_id: UUID
    decision: DecisionType
    reason: str
    decided_at: datetime

    def __post_init__(self) -> None:
        if self.decided_at.utcoffset() != timedelta(0):
            raise ValueError("O relógio deve estar em UTC.")
        if self.decision == "REJECTED" and not self.reason:
            raise ValueError("Toda decisão de rejeição deve ter uma justificativa (reason).")
        if self.decision == "APPROVED" and not self.reason:
            # Mesmo aprovado, é bom ter um reason padrão como 'OK' ou justificativa do limite
            pass
