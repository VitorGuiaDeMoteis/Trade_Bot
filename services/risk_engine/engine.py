"""Motor de risco determinístico da v0.1 (M2)."""

from datetime import datetime, timedelta
from uuid import uuid4

from packages.domain.risk import RiskDecision
from packages.domain.strategy import Signal


class RiskEngine:
    def evaluate(self, signal: Signal, current_time: datetime, system_paused: bool = False) -> RiskDecision:
        """Avalia um sinal emitido pela estratégia e aprova ou bloqueia."""
        
        if system_paused:
            return RiskDecision(
                decision_id=uuid4(),
                signal_id=signal.signal_id,
                decision="REJECTED",
                reason="Sistema está pausado.",
                decided_at=current_time,
            )

        # Regra de vencimento
        if current_time - signal.generated_at > timedelta(hours=1):
            return RiskDecision(
                decision_id=uuid4(),
                signal_id=signal.signal_id,
                decision="REJECTED",
                reason="Sinal vencido (gerado há mais de 1h).",
                decided_at=current_time,
            )

        # Se passou por tudo
        return RiskDecision(
            decision_id=uuid4(),
            signal_id=signal.signal_id,
            decision="APPROVED",
            reason="Aprovado pelas regras de risco.",
            decided_at=current_time,
        )
