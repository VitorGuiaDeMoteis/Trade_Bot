from unittest.mock import AsyncMock, patch, MagicMock
import httpx
import pytest
from decimal import Decimal
import asyncio
from packages.domain.risk import RiskDecision
from packages.domain.paper import PaperBook, PaperResult
from services.paper_executor.alpaca import AlpacaPaperExecutor
from uuid import uuid4
from datetime import datetime, timezone

@pytest.fixture
def mock_httpx():
    with patch("httpx.AsyncClient.post") as mock_post:
        yield mock_post

def test_execute_approved_buy_succeeds(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "123"}
    mock_httpx.return_value.__aenter__.return_value = mock_resp

    executor = AlpacaPaperExecutor("test", "test")
    risk = RiskDecision(decision_id=uuid4(), signal_id=uuid4(), decision="APPROVED", reason="OK", decided_at=datetime.now(timezone.utc))
    
    async def run():
        return await executor.execute(
            book=None,
            symbol="SPY",
            side="BUY",
            reference=Decimal("100.0"),
            quantity=1,
            risk=risk
        )
    
    result = asyncio.run(run())
    assert result.status == "FILLED"
    assert result.reason == "order_submitted"
    
    mock_httpx.assert_called_once()
    args, kwargs = mock_httpx.call_args
    assert "client_order_id" in kwargs["json"]
    assert kwargs["json"]["client_order_id"] == f"agy-{risk.decision_id}-{risk.signal_id}"

def test_execute_duplicate_client_order_id(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.status_code = 422
    mock_resp.json.return_value = {"message": "order_id must be unique"}
    mock_httpx.return_value.__aenter__.return_value = mock_resp

    executor = AlpacaPaperExecutor("test", "test")
    risk = RiskDecision(decision_id=uuid4(), signal_id=uuid4(), decision="APPROVED", reason="OK", decided_at=datetime.now(timezone.utc))
    
    async def run():
        return await executor.execute(
            book=None,
            symbol="SPY",
            side="BUY",
            reference=Decimal("100.0"),
            quantity=1,
            risk=risk
        )
        
    result = asyncio.run(run())
    
    assert result.status == "NO_ACTION"
    assert result.reason == "duplicate_client_order_id"
