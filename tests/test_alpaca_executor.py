import asyncio
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from services.paper_executor.alpaca import AlpacaPaperBroker


@pytest.fixture
def mock_httpx():
    with patch("httpx.AsyncClient.post") as mock_post:
        yield mock_post

def test_execute_approved_buy_succeeds(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "123", "status": "submitted"}
    mock_httpx.return_value = mock_resp

    executor = AlpacaPaperBroker("test", "test")
    client_id = f"agy-{uuid4()}-{uuid4()}"
    
    async def run():
        return await executor.submit_order(
            symbol="SPY",
            side="BUY",
            quantity=1,
            client_order_id=client_id
        )
    
    result = asyncio.run(run())
    assert result.status == "submitted"
    assert result.broker_order_id == "123"
    assert result.client_order_id == ""
    
    mock_httpx.assert_called_once()
    args, kwargs = mock_httpx.call_args
    assert "client_order_id" in kwargs["json"]
    assert kwargs["json"]["client_order_id"] == client_id

def test_execute_duplicate_client_order_id(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.status_code = 422
    mock_resp.json.return_value = {"message": "order_id must be unique"}
    mock_httpx.return_value = mock_resp
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError('error', request=MagicMock(), response=mock_resp)

    executor = AlpacaPaperBroker("test", "test")
    client_id = f"agy-{uuid4()}-{uuid4()}"
    
    async def run():
        return await executor.submit_order(
            symbol="SPY",
            side="BUY",
            quantity=1,
            client_order_id=client_id
        )
        
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(run())
