from dataclasses import dataclass
from enum import Enum


class ForwardState(Enum):
    NOT_STARTED = "NOT_STARTED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    INVALIDATED = "INVALIDATED"
    COMPLETED_PASS = "COMPLETED_PASS"
    COMPLETED_NO_EDGE = "COMPLETED_NO_EDGE"
    TOO_SPARSE = "TOO_SPARSE"


@dataclass
class ForwardPaperEngine:
    state: ForwardState = ForwardState.NOT_STARTED
    months_elapsed: float = 0.0
    trades_executed: int = 0
    operational_failure: bool = False

    def evaluate_state(self):
        if self.operational_failure:
            self.state = ForwardState.INVALIDATED
            return

        if self.state in [
            ForwardState.PAUSED,
            ForwardState.INVALIDATED,
            ForwardState.COMPLETED_PASS,
            ForwardState.COMPLETED_NO_EDGE,
            ForwardState.TOO_SPARSE,
        ]:
            return

        if self.months_elapsed >= 24:
            if self.trades_executed >= 20:
                self.state = ForwardState.COMPLETED_PASS
            else:
                self.state = ForwardState.TOO_SPARSE
        elif self.months_elapsed >= 12:
            if self.trades_executed >= 20:
                # We can choose to stop and pass, or continue. For now, do nothing.
                return
