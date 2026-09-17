"""Opt-in demo runtime. Reuse M7 reconciliation, never process pending submits."""

import asyncio
import logging
from typing import Any

from services.alpaca_paper.adapter import AlpacaPaperAdapter
from services.alpaca_paper.worker import AlpacaPaperWorker

logger = logging.getLogger("trading_bot.observation")


class ObservationAdapter(AlpacaPaperAdapter):
    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if method != "GET":
            raise ValueError("observation_only: Alpaca writes are forbidden")
        return await super()._request(method, path, **kwargs)


class ObservationWorker(AlpacaPaperWorker):
    async def _run(self) -> None:
        async with self.adapter:
            logger.info("Observation worker started: Paper GET only; submission disabled")
            while self.running:
                try:
                    await self.reconcile_once()
                    logger.info(
                        "Observation reconciliation: %s",
                        "degraded" if self.degraded else "snapshot refreshed",
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await self._enter_degraded("observation_reconciliation_failed")
                    logger.warning("Observation reconciliation failed; keeping last snapshot")
                await asyncio.sleep(3)
