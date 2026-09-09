import pytest
from httpx import AsyncClient, MockTransport, Response

from services.alpaca_paper.adapter import AlpacaPaperAdapter, AlpacaPaperError


@pytest.mark.anyio
async def test_missing_credentials():
    with pytest.raises(AlpacaPaperError, match="Credentials missing"):
        AlpacaPaperAdapter("", "")


@pytest.mark.anyio
async def test_paper_url_enforced():
    def handler(request):
        assert str(request.url).startswith("https://paper-api.alpaca.markets/v2/")
        return Response(200, json={"id": "fake"})

    client = AsyncClient(transport=MockTransport(handler))
    async with AlpacaPaperAdapter("key", "secret", client=client) as adapter:
        res = await adapter.get_account()
        assert res["id"] == "fake"


@pytest.mark.anyio
async def test_error_classification():
    def handler_429(request):
        return Response(429, json={"message": "error"})

    def handler_403(request):
        return Response(403, json={"message": "error"})

    def handler_502(request):
        return Response(502, json={"message": "error"})

    async with AlpacaPaperAdapter(
        "k", "s", client=AsyncClient(transport=MockTransport(handler_429))
    ) as adapter:
        with pytest.raises(AlpacaPaperError) as exc:
            await adapter.get_account()
        assert exc.value.code == "rate_limit"
        assert exc.value.retryable is True

    async with AlpacaPaperAdapter(
        "k", "s", client=AsyncClient(transport=MockTransport(handler_403))
    ) as adapter:
        with pytest.raises(AlpacaPaperError) as exc:
            await adapter.get_account()
        assert exc.value.code == "client_error"
        assert exc.value.retryable is False

    async with AlpacaPaperAdapter(
        "k", "s", client=AsyncClient(transport=MockTransport(handler_502))
    ) as adapter:
        with pytest.raises(AlpacaPaperError) as exc:
            await adapter.get_account()
        assert exc.value.code == "server_error"
        assert exc.value.retryable is True
