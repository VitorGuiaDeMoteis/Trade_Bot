"""PostgreSQL: candle + evento atômicos, leitura paginada e replay durável."""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4, uuid5

from sqlalchemy import Connection, Engine, RowMapping, func, select, text
from sqlalchemy.dialects.postgresql import insert

from packages.contracts.market import CandleEvent, CandleResponse
from packages.domain.market import Candle
from services.api.models import candles, system_events, signals, risk_decisions
from services.market_simulator.generator import CandleGenerator
from services.strategy_engine.engine import BaseStrategy
from services.risk_engine.engine import RiskEngine


class CursorReset(ValueError):
    """Cursor pertence a um histórico que não está mais disponível."""


@dataclass(frozen=True)
class HistoryPage:
    candles: list[CandleResponse]
    cursor: int
    high_watermark: int
    has_more: bool
    last_updated_at: datetime | None


def candle_response(row: RowMapping) -> CandleResponse:
    return CandleResponse.model_validate({name: row[name] for name in Candle.__dataclass_fields__})


class MarketStore:
    def __init__(
        self,
        engine: Engine,
        stream_id: UUID,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        strategy: BaseStrategy | None = None,
        risk: RiskEngine | None = None,
    ) -> None:
        self.engine = engine
        self.stream_id = stream_id
        self.clock = clock
        self.strategy = strategy
        self.risk = risk

    def _persist(self, connection: Connection, candle: Candle) -> CandleEvent:
        if candle.stream_id != self.stream_id:
            raise ValueError("Stream incorreto.")
        inserted = connection.scalar(
            insert(candles)
            .values(**asdict(candle))
            .on_conflict_do_nothing()
            .returning(candles.c.candle_id)
        )
        if inserted is not None:
            event = CandleEvent(
                event_id=uuid5(candle.candle_id, "market.candle.closed"),
                occurred_at=self.clock(),
                correlation_id=uuid4(),
                stream_id=self.stream_id,
                sequence=candle.sequence,
                payload=CandleResponse.model_validate(candle),
            )
            connection.execute(
                system_events.insert().values(
                    event_id=event.event_id,
                    candle_id=candle.candle_id,
                    stream_id=self.stream_id,
                    sequence=event.sequence,
                    event_type=event.event_type,
                    schema_version=event.schema_version,
                    occurred_at=event.occurred_at,
                    correlation_id=event.correlation_id,
                )
            )
            if self.strategy is not None:
                signal = self.strategy.process_candle(candle, event.occurred_at)
                connection.execute(
                    signals.insert().values(**asdict(signal))
                )
                if self.risk is not None:
                    decision = self.risk.evaluate(signal, event.occurred_at)
                    connection.execute(
                        risk_decisions.insert().values(**asdict(decision))
                    )
            return event
        row = (
            connection.execute(
                select(candles, system_events)
                .join(system_events)
                .where(
                    (
                        (candles.c.stream_id == self.stream_id) & (candles.c.sequence == candle.sequence)
                    ) | (
                        (candles.c.provider == candle.provider) & 
                        (candles.c.symbol == candle.symbol) & 
                        (candles.c.timeframe == candle.timeframe) & 
                        (candles.c.open_time == candle.open_time)
                    )
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ValueError("No matching row found after conflict.")
        
        # We don't strictly compare candle_response(row) == candle because sequences might differ,
        # but we can compare the core market data properties to ensure no content conflict.
        existing_candle = candle_response(row)
        if (existing_candle.open != candle.open or
            existing_candle.high != candle.high or
            existing_candle.low != candle.low or
            existing_candle.close != candle.close or
            existing_candle.volume != candle.volume):
            raise ValueError("Conflito de conteúdo para candle já persistido.")
            
        return self._event(row)

    def append(self, candle: Candle) -> CandleEvent:
        with self.engine.begin() as connection:
            event = self._persist(connection, candle)
        # Só retorna ao produtor após o commit das duas tabelas.
        return event

    def advance(self, generator: CandleGenerator) -> CandleEvent:
        with self.engine.begin() as connection:
            # Serializa a seleção do último candle + avanço para este stream.
            lock_id = int.from_bytes(self.stream_id.bytes[:8], signed=True)
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
            last = connection.execute(
                select(candles.c.sequence, candles.c.close)
                .where(candles.c.stream_id == self.stream_id)
                .order_by(candles.c.sequence.desc())
                .limit(1)
            ).first()
            candle = generator.next_closed(
                int(last.sequence) + 1 if last else 1,
                Decimal(last.close) if last else Decimal("100.0000"),
            )
            event = self._persist(connection, candle)
        return event

    def history(
        self, limit: int, after: int | None = None, through: int | None = None
    ) -> HistoryPage:
        if not 1 <= limit <= 500 or (after is not None and after < 0):
            raise ValueError("Limite/cursor inválido.")
        with self.engine.connect() as connection:
            latest = int(
                connection.scalar(
                    select(func.coalesce(func.max(candles.c.sequence), 0)).where(
                        candles.c.stream_id == self.stream_id
                    )
                )
                or 0
            )
            upper = latest if through is None else through
            if upper < 0 or upper > latest or (after is not None and after > upper):
                raise CursorReset("Cursor fora do histórico.")
            query = select(candles).where(
                candles.c.stream_id == self.stream_id,
                candles.c.sequence <= upper,
            )
            if after is None:
                query = query.order_by(candles.c.sequence.desc()).limit(limit)
            else:
                query = (
                    query.where(candles.c.sequence > after)
                    .order_by(candles.c.sequence)
                    .limit(limit)
                )
            rows = list(connection.execute(query).mappings())
            if after is None:
                rows.reverse()
            values = [candle_response(row) for row in rows]
            cursor = values[-1].sequence if values else (after or 0)
            updated = connection.scalar(
                select(system_events.c.occurred_at)
                .where(
                    system_events.c.stream_id == self.stream_id, system_events.c.sequence <= cursor
                )
                .order_by(system_events.c.sequence.desc())
                .limit(1)
            )
        return HistoryPage(values, cursor, upper, cursor < upper, updated)

    def _event(self, row: RowMapping) -> CandleEvent:
        return CandleEvent(
            event_id=row["event_id"],
            occurred_at=row["occurred_at"],
            correlation_id=row["correlation_id"],
            stream_id=row["stream_id"],
            sequence=row["sequence"],
            payload=candle_response(row),
        )

    def events_after(self, cursor: int, limit: int = 100) -> list[CandleEvent]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(candles, system_events)
                .join(system_events)
                .where(candles.c.stream_id == self.stream_id, candles.c.sequence > cursor)
                .order_by(candles.c.sequence)
                .limit(limit)
            ).mappings()
            return [self._event(row) for row in rows]
