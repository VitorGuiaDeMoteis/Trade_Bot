"""Paces the M4 iterator. No database, credentials, broker or financial engine here."""

import asyncio
from collections import deque
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from packages.domain.backtest import Dataset, encode
from packages.domain.paper import PaperConfig
from services.backtesting.engine import replay_steps

SPEEDS = (0.5, 1, 5, 20)


class ReplayRuntime:
    def __init__(
        self,
        dataset: Dataset,
        config: PaperConfig,
        *,
        speed: float = 1,
        source: str = "spy-history.json",
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if speed not in SPEEDS:
            raise ValueError("replay_speed_must_be_0.5_1_5_or_20")
        self.dataset, self.config, self.speed, self.source = dataset, config, speed, source
        self.clock = clock
        self.session_id = str(uuid4())
        self.total = len({c.open_time for c in dataset.candles})
        self.steps = replay_steps(dataset, config)
        self.status = "READY"
        self.frame: dict[str, Any] | None = None
        self.report: dict[str, Any] | None = None
        self.events: deque[dict[str, Any]] = deque(maxlen=400)
        self.orders: deque[dict[str, Any]] = deque(maxlen=20)
        self.fills: deque[dict[str, Any]] = deque(maxlen=20)
        self.history: deque[dict[str, Any]] = deque(maxlen=60)
        self.orders_count = self.fills_count = self.sequence = 0
        self.updated_at: str | None = None
        self.task: asyncio.Task[None] | None = None
        self._event("REPLAY", "READY · arquivo histórico local; execução exclusivamente simulada")

    def _event(self, kind: str, text: str, timestamp: str | None = None) -> None:
        self.sequence += 1
        self.events.append(
            {
                "sequence": self.sequence,
                "kind": kind,
                "text": text,
                "timestamp": timestamp,
                "recorded_at": self.clock().isoformat(),
            }
        )

    def advance(self) -> None:
        """Called by the process clock only, never by a request handler."""
        if self.status in {"COMPLETED", "ERROR"}:
            return
        try:
            frame = next(self.steps)
        except StopIteration as finished:
            self._complete(finished.value)
            return
        self.status = "RUNNING"
        self.frame = frame
        self.updated_at = self.clock().isoformat()
        for candle in frame["candles"]:
            self.history.append(candle)
            self._event("CANDLE", f"{candle['symbol']} received", candle["open_time"])
        for outcome in frame["outcomes"]:
            signal, risk = outcome["signal"], outcome["risk"]
            decision = "BLOCKED" if risk["decision"] == "REJECTED" else risk["decision"]
            self._event(
                "RISK",
                f"{decision} · {signal['signal_type']} · {risk['reason']}",
                outcome["executed_at"],
            )
            if outcome["order_id"]:
                order = {
                    "order_id": outcome["order_id"],
                    "symbol": outcome["symbol"],
                    "side": signal["signal_type"],
                    "quantity": outcome["quantity"],
                    "filled_quantity": outcome["quantity"] if outcome["fill_id"] else 0,
                    "status": outcome["status"],
                    "reason": outcome["reason"],
                    "requested_at": outcome["executed_at"],
                }
                self.orders.appendleft(order)
                self.orders_count += 1
                self._event(
                    "ORDER",
                    f"{order['side']} {order['quantity']} {order['symbol']}"
                    f" · {order['status']} · {order['reason']}",
                    outcome["executed_at"],
                )
            elif outcome["reason"] != "hold":
                self._event("EXECUTOR", f"NO ACTION · {outcome['reason']}", outcome["executed_at"])
            if outcome["fill_id"]:
                self.fills.appendleft(
                    {
                        "fill_id": outcome["fill_id"],
                        "order_id": outcome["order_id"],
                        "symbol": outcome["symbol"],
                        "quantity": outcome["quantity"],
                        "price": outcome["price"],
                        "fee": outcome["fee"],
                        "filled_at": outcome["executed_at"],
                    }
                )
                self.fills_count += 1
                self._event(
                    "FILL",
                    f"{outcome['quantity']} {outcome['symbol']} @ ${outcome['price']}",
                    outcome["executed_at"],
                )
        for signal in frame["signals"]:
            self._event(
                "STRATEGY",
                signal["signal_type"]
                + (" · sem ação" if signal["signal_type"] == "HOLD" else " · próxima abertura"),
                signal["generated_at"],
            )
        self._event(
            "PORTFOLIO", f"equity ${frame['portfolio']['equity']}", frame["portfolio"]["timestamp"]
        )
        if frame["portfolio"]["step"] == self.total:
            try:
                next(self.steps)
            except StopIteration as finished:
                self._complete(finished.value)

    def _complete(self, report: dict[str, Any]) -> None:
        self.report = report
        self.status = "COMPLETED"
        self.updated_at = self.clock().isoformat()
        self._event("REPLAY", "COMPLETED · fim do dataset; carteira final preservada")

    async def _run(self) -> None:
        try:
            while self.status not in {"COMPLETED", "ERROR"}:
                self.advance()
                if self.status == "RUNNING":
                    await asyncio.sleep(1 / self.speed)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.status = "ERROR"
            self.updated_at = self.clock().isoformat()
            self._event("REPLAY", "ERROR · processamento interrompido; último estado preservado")

    def start(self) -> None:
        if self.task is None:
            self.task = asyncio.create_task(self._run(), name="historical-replay")

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.steps.close()

    def snapshot(self, after: int = 0) -> dict[str, Any]:
        import json

        portfolio = (
            self.frame["portfolio"]
            if self.frame
            else {
                "step": 0,
                "cash": self.config.initial_cash,
                "equity": self.config.initial_cash,
                "market_value": "0",
                "realized_pnl": "0",
                "unrealized_pnl": "0",
                "fees": "0",
                "total_pnl": "0",
            }
        )
        return json.loads(  # type: ignore[no-any-return]
            encode(
                deepcopy(
                    {
                        "mode": "REPLAY",
                        "session_id": self.session_id,
                        "status": self.status,
                        "speed": self.speed,
                        "updated_at": self.updated_at,
                        "dataset": {
                            "name": self.source,
                            "hash": self.dataset.hash,
                            "candles": len(self.dataset.candles),
                            "symbols": sorted({c.symbol for c in self.dataset.candles}),
                            "from": self.dataset.candles[0].open_time
                            if self.dataset.candles
                            else None,
                            "through": self.dataset.candles[-1].close_time
                            if self.dataset.candles
                            else None,
                        },
                        "initial_cash": self.config.initial_cash,
                        "total_steps": self.total,
                        "step": portfolio["step"],
                        "frame": self.frame,
                        "portfolio": {
                            **portfolio,
                            "positions": self.frame["positions"] if self.frame else [],
                            "orders": list(self.orders),
                            "fills": list(self.fills),
                        },
                        "orders_count": self.orders_count,
                        "fills_count": self.fills_count,
                        "closed_trades": self.frame["closed_trades"] if self.frame else 0,
                        "history": list(self.history),
                        "events": [e for e in self.events if e["sequence"] > after],
                        "events_truncated": bool(
                            self.events and after and after < self.events[0]["sequence"] - 1
                        ),
                        "last_sequence": self.sequence,
                        "result_hash": self.report["result_hash"] if self.report else None,
                    }
                )
            )
        )
