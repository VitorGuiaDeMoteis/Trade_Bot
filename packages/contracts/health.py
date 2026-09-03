"""Contrato de infraestrutura v1, independente do transporte HTTP."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from packages.contracts.market import MarketDataStatus


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.1"] = "1.1"
    service: Literal["trading-bot-api"] = "trading-bot-api"
    version: Literal["0.1.0"] = "0.1.0"
    mode: Literal["SIMULADO", "DADOS REAIS / EXECUÇÃO SIMULADA"] = "DADOS REAIS / EXECUÇÃO SIMULADA"
    status: Literal["ok", "degraded"]
    database: Literal["up", "down", "schema_pending"]
    checked_at: datetime
    correlation_id: UUID
    market_data: dict
