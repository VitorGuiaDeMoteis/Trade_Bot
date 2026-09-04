"""Offline contract tests: no keys, internet, Trading API or real market assumptions."""

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from packages.domain.market import SimulationSpec
from packages.domain.market_bar import MarketBar
from services.api.config import Settings
from services.market_data.alpaca_provider import AlpacaMarketDataProvider, alpaca_timeframe
from services.market_data.calendar import regular_session
from services.market_data.errors import ProviderError
from services.market_data.simulator import SimulatorMarketDataProvider
from services.strategy_engine.engine import BaseStrategy

NOW = datetime(2026, 9, 3, 17, tzinfo=UTC)
RAW = {
    "t": "2026-09-03T15:00:00Z",
    "o": "100.1234567890",
    "h": "102",
    "l": "99",
    "c": "101.125",
    "v": 123,
}
WELCOME = [{"T": "success", "msg": "connected"}]
AUTH = [{"T": "success", "msg": "authenticated"}]
SUB = [{"T": "subscription", "bars": ["SPY", "AAPL"], "updatedBars": ["SPY", "AAPL"]}]


class FakeSocket:
    def __init__(self, messages):  # type: ignore
        self.messages = list(messages)
        self.sent = []
        self.closed = False

    async def recv(self):  # type: ignore
        if not self.messages:
            raise OSError("DO_NOT_LOG_SECRET")
        message = self.messages.pop(0)
        if isinstance(message, Exception):
            raise message
        return json.dumps(message)

    async def send(self, message):  # type: ignore
        self.sent.append(json.loads(message))

    async def close(self):  # type: ignore
        self.closed = True


def provider(handler=None, **kwargs):  # type: ignore
    def default(request):  # type: ignore
        symbol = request.url.params["symbols"]
        return httpx.Response(200, json={"bars": {symbol: [RAW]}, "next_page_token": None})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler or default))
    return AlpacaMarketDataProvider(
        "fake-key",
        "fake-secret",
        "iex",
        ["SPY", "AAPL"],
        "1h",
        client=client,
        clock=lambda: NOW,
        **kwargs,
    )


def test_history_decimal_utc_closed_identity_and_endpoint():  # type: ignore
    requests = []

    def handler(request):  # type: ignore
        requests.append(request)
        # Numeric JSON decimals must not pass through binary floats.
        return httpx.Response(
            200,
            content=b'{"bars":{"SPY":[{"t":"2026-09-03T15:00:00.123Z",'
            b'"o":100.1234567890,"h":102,"l":99,"c":101.125,"v":123}]}}',
        )

    bar = asyncio.run(provider(handler).get_historical_candles("SPY", "1h"))[0]  # type: ignore
    assert isinstance(bar, MarketBar) and not hasattr(bar, "sequence")
    assert bar.open == Decimal("100.1234567890") and bar.provider == "alpaca"
    assert bar.open_time.utcoffset() == timedelta(0) and bar.open_time.microsecond == 123000
    assert bar.close_time - bar.open_time == timedelta(hours=1) and bar.is_closed
    assert str(requests[0].url).startswith("https://data.alpaca.markets/v2/stocks/bars?")
    assert requests[0].url.params["timeframe"] == "1Hour"
    assert requests[0].url.params["adjustment"] == "raw"


@pytest.mark.parametrize("symbol", ["SPY", "AAPL"])
def test_history_respects_single_requested_symbol(symbol):  # type: ignore
    seen = []

    def handler(request):  # type: ignore
        seen.append(request.url.params["symbols"])
        return httpx.Response(200, json={"bars": {symbol: [RAW]}})

    bars = asyncio.run(provider(handler).get_historical_candles(symbol, "1h"))  # type: ignore
    assert seen == [symbol] and {bar.symbol for bar in bars} == {symbol}


@pytest.mark.parametrize("timeframe", ["1m", "5m", "15m", "1d", "1Hour", "bad"])
def test_unsupported_timeframe_is_explicit(timeframe):  # type: ignore
    with pytest.raises(ValueError, match="unsupported_timeframe"):
        alpaca_timeframe(timeframe)


@pytest.mark.parametrize("opened", ["2026-09-03T16:00:00Z", "2026-09-03T17:00:00Z"])
def test_partial_or_grace_period_bars_are_not_emitted(opened):  # type: ignore
    def handler(request):  # type: ignore
        return httpx.Response(200, json={"bars": {"SPY": [{**RAW, "t": opened}]}})

    assert asyncio.run(provider(handler).get_historical_candles("SPY", "1h")) == []  # type: ignore


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (401, "unauthorized", False),
        (403, "feed_forbidden", False),
        (429, "historical_unavailable", True),
        (500, "historical_unavailable", True),
        (422, "historical_request_rejected", False),
    ],
)
def test_rest_errors_are_safe_and_classified(status, code, retryable, caplog):  # type: ignore
    p = provider(lambda request: httpx.Response(status, text="fake-secret"))  # type: ignore
    with pytest.raises(ProviderError) as error:
        asyncio.run(p.get_historical_candles("SPY", "1h"))
    assert error.value.code == code and error.value.retryable == retryable
    assert "fake-secret" not in caplog.text
    assert p.get_status().state == ("reconnecting" if retryable else "configuration_error")


@pytest.mark.parametrize(
    "change",
    [{"o": "NaN"}, {"l": "110"}, {"v": "1.5"}, {"t": "not-a-date"}, {"t": "2026-09-03T15:00:00"}],
)
def test_invalid_payload_not_silently_swallowed(change):  # type: ignore
    p = provider(lambda request: httpx.Response(200, json={"bars": {"SPY": [{**RAW, **change}]}}))  # type: ignore
    with pytest.raises(ProviderError, match="invalid_historical_payload"):
        asyncio.run(p.get_historical_candles("SPY", "1h"))
    assert p.get_status().state == "degraded"


def test_backfill_paginates_all_pages_in_order():  # type: ignore
    seen = []

    def handler(request):  # type: ignore
        seen.append(dict(request.url.params))
        second = "page_token" in request.url.params
        raw = RAW if second else {**RAW, "t": "2026-09-03T14:00:00Z"}
        return httpx.Response(
            200, json={"bars": {"SPY": [raw]}, "next_page_token": None if second else "next"}
        )

    bars = asyncio.run(
        provider(handler).get_historical_candles(  # type: ignore
            "SPY", "1h", limit=1, start=NOW - timedelta(hours=4)
        )
    )
    assert len(bars) == 2 and bars[0].open_time < bars[1].open_time
    assert seen[1]["page_token"] == "next" and all(q["sort"] == "asc" for q in seen)


def test_repeated_page_token_fails_instead_of_looping():  # type: ignore
    p = provider(lambda request: httpx.Response(200, json={"bars": {}, "next_page_token": "loop"}))  # type: ignore
    with pytest.raises(ProviderError, match="repeated_page_token"):
        asyncio.run(p.get_historical_candles("SPY", "1h"))


def test_duplicates_have_stable_identity_and_content_conflicts_keep_identity():  # type: ignore
    p = provider()  # type: ignore
    first = asyncio.run(p.get_historical_candles("SPY", "1h"))[0]
    again = asyncio.run(p.get_historical_candles("SPY", "1h"))[0]
    assert first == again and first.candle_id == replace(first, volume=999).candle_id


@pytest.mark.parametrize(
    "stage,code",
    [(0, 400), (1, 401), (1, 402), (1, 404), (2, 405), (2, 409), (2, 410), (0, 406), (2, 500)],
)
def test_websocket_error_ack_is_not_success(stage, code, caplog):  # type: ignore
    messages = [WELCOME, AUTH, SUB]
    messages[stage] = [{"T": "error", "code": code, "msg": "fake-secret"}]
    p = provider()  # type: ignore
    with pytest.raises(ProviderError):
        asyncio.run(p.handshake(FakeSocket(messages)))  # type: ignore
    assert p.get_status().state != "connected"
    assert "fake-secret" not in caplog.text


@pytest.mark.parametrize(
    "messages",
    [
        [AUTH],
        [WELCOME, WELCOME],
        [WELCOME, AUTH, []],
        [WELCOME, AUTH, [{"T": "subscription", "bars": ["SPY"]}]],
    ],
)
def test_missing_or_incomplete_ack_is_failure(messages):  # type: ignore
    with pytest.raises(ProviderError, match="ack_missing"):
        asyncio.run(provider().handshake(FakeSocket(messages)))  # type: ignore


def test_auth_and_subscription_acknowledged():  # type: ignore
    p, socket = provider(), FakeSocket([WELCOME, AUTH, SUB])  # type: ignore
    asyncio.run(p.handshake(socket))
    assert p.get_status().state == "connected" or p.get_status().state == "delayed"
    assert socket.sent[0]["action"] == "auth"
    assert socket.sent[1] == {
        "action": "subscribe",
        "bars": ["SPY", "AAPL"],
        "updatedBars": ["SPY", "AAPL"],
    }


def test_minute_ws_bar_never_emitted_as_hourly():  # type: ignore
    async def scenario():  # type: ignore
        socket = FakeSocket(  # type: ignore
            [WELCOME, AUTH, SUB, [{"T": "b", "S": "SPY", **RAW}], [{"T": "u", "S": "SPY", **RAW}]]
        )

        async def factory():  # type: ignore
            return socket

        async def stop(delay):  # type: ignore
            raise asyncio.CancelledError

        p = provider(  # type: ignore
            lambda request: httpx.Response(200, json={"bars": {}}),
            socket_factory=factory,
            sleep=stop,
        )
        with pytest.raises(asyncio.CancelledError):
            await anext(p.subscribe())
        assert socket.closed

    asyncio.run(scenario())  # type: ignore


def test_reconnect_backoff_has_cap_and_safe_logs(caplog):  # type: ignore
    delays = []

    async def factory():  # type: ignore
        raise OSError("fake-secret")

    async def sleep(delay):  # type: ignore
        delays.append(delay)
        if len(delays) == 7:
            raise asyncio.CancelledError

    async def scenario():  # type: ignore
        p = provider(socket_factory=factory, sleep=sleep)  # type: ignore
        with pytest.raises(asyncio.CancelledError):
            await anext(p.subscribe())
        assert p.get_status().state == "reconnecting"

    asyncio.run(scenario())  # type: ignore
    assert delays == [1, 2, 5, 10, 30, 30, 30] and "fake-secret" not in caplog.text


def test_backoff_resets_only_after_stable_connection():  # type: ignore
    async def scenario():  # type: ignore
        elapsed, delays, calls = [0.0], [], [0]

        class StableSocket(FakeSocket):
            async def recv(self):  # type: ignore
                if not self.messages:
                    elapsed[0] += 61
                return await super().recv()  # type: ignore

        async def factory():  # type: ignore
            calls[0] += 1
            if calls[0] < 3:
                raise OSError()
            return StableSocket([WELCOME, AUTH, SUB])  # type: ignore

        async def sleep(delay):  # type: ignore
            delays.append(delay)
            if len(delays) == 3:
                raise asyncio.CancelledError

        p = provider(  # type: ignore
            lambda r: httpx.Response(200, json={"bars": {}}),
            socket_factory=factory,
            timer=lambda: elapsed[0],
            sleep=sleep,
        )
        with pytest.raises(asyncio.CancelledError):
            await anext(p.subscribe())
        assert delays == [1, 2, 1]

    asyncio.run(scenario())  # type: ignore


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 9, 5, 17, tzinfo=UTC),
        datetime(2026, 9, 7, 17, tzinfo=UTC),
        datetime(2026, 11, 27, 19, tzinfo=UTC),
        datetime(2026, 9, 3, 21, tzinfo=UTC),
    ],
)
def test_weekend_holiday_early_close_and_evening_not_stalled(now):  # type: ignore
    p = provider()  # type: ignore
    p.clock = lambda: now
    p._state = "connected"
    assert p.get_status().state == "market_closed"
    assert p.get_status().session == "regular"
    p._state = "configuration_error"
    assert p.get_status().state == "configuration_error"


def test_calendar_dst_transition():  # type: ignore
    before = regular_session(datetime(2026, 3, 6, 18, tzinfo=UTC))
    after = regular_session(datetime(2026, 3, 9, 18, tzinfo=UTC))
    assert before[0].hour == 14 and after[0].hour == 13  # type: ignore


@pytest.mark.parametrize(
    "values",
    [
        {"market_data_provider": "unknown"},
        {"market_data_provider": "alpaca"},
        {"market_timeframe": "1m"},
        {"market_symbols": ", ,"},
    ],
)
def test_settings_fail_early(values):  # type: ignore
    with pytest.raises(ValidationError):
        Settings(_env_file=None, postgres_password=SecretStr("test"), **values)


def test_settings_normalize_symbols_and_hide_keys():  # type: ignore
    s = Settings(
        _env_file=None,
        postgres_password=SecretStr("test"),
        market_data_provider="alpaca",
        alpaca_api_key_id=SecretStr("fake-key"),
        alpaca_api_secret_key=SecretStr("fake-secret"),
        market_symbols=" spy, AAPL, ,SPY,tsla, ",
    )
    assert s.symbols == ["SPY", "AAPL", "TSLA"]
    assert "fake-key" not in repr(s) and "fake-secret" not in repr(s)


def test_simulator_keeps_deterministic_price_chain():  # type: ignore
    p = SimulatorMarketDataProvider(SimulationSpec())
    bars = asyncio.run(p.get_historical_candles("TEST", "1h", 3))
    assert bars[1] == p.generator.next_closed(2, bars[0].close)
    assert bars == asyncio.run(p.get_historical_candles("TEST", "1h", 3))
    with pytest.raises(ValueError):
        asyncio.run(p.get_historical_candles("SPY", "1h"))


def test_strategy_rejects_partial():  # type: ignore
    candle = SimulatorMarketDataProvider(SimulationSpec()).generator.next_closed(1)
    with pytest.raises(ValueError, match="partial"):
        BaseStrategy().process_candle(replace(candle, is_closed=False), NOW)


def test_smoke_skipped_without_network(monkeypatch, capsys):  # type: ignore
    from scripts import smoke_test

    def forbidden(*args, **kwargs):  # type: ignore
        pytest.fail("Smoke opened a provider without opt-in")

    monkeypatch.setattr(smoke_test, "AlpacaMarketDataProvider", forbidden)
    assert asyncio.run(smoke_test.main()) == 0
    assert "SKIPPED" in capsys.readouterr().out


def test_transport_failure_is_retryable_and_redacted(caplog):  # type: ignore
    def handler(request):  # type: ignore
        raise httpx.ConnectError("fake-secret", request=request)

    with pytest.raises(ProviderError, match="historical_transport") as error:
        asyncio.run(provider(handler).get_historical_candles("SPY", "1h"))  # type: ignore
    assert error.value.retryable and "fake-secret" not in caplog.text


def test_unexpected_symbol_payload_fails():  # type: ignore
    p = provider(lambda r: httpx.Response(200, json={"bars": {"TSLA": [RAW]}}))  # type: ignore
    with pytest.raises(ProviderError, match="invalid_historical_payload"):
        asyncio.run(p.get_historical_candles("SPY", "1h"))


def test_price_beyond_database_precision_is_not_silently_rounded():  # type: ignore
    p = provider(  # type: ignore
        lambda r: httpx.Response(200, json={"bars": {"SPY": [{**RAW, "o": "100.12345678901"}]}})
    )
    with pytest.raises(ProviderError, match="invalid_historical_payload"):
        asyncio.run(p.get_historical_candles("SPY", "1h"))


def test_configuration_error_never_prints_secret_input():  # type: ignore
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            postgres_password=SecretStr("test"),
            market_data_provider="alpaca",
            alpaca_api_key_id=SecretStr("secret-input"),
            alpaca_api_secret_key=None,
        )
    assert "configuration_error" in str(error.value)
    assert "secret-input" not in str(error.value)


@pytest.mark.parametrize("status,retryable", [(401, False), (403, False), (429, True), (503, True)])
def test_http_websocket_handshake_failure_is_classified(monkeypatch, status, retryable):  # type: ignore
    from websockets.datastructures import Headers
    from websockets.exceptions import InvalidStatus
    from websockets.http11 import Response

    import services.market_data.alpaca_provider as module

    async def rejected(*args, **kwargs):  # type: ignore
        raise InvalidStatus(Response(status, "fake-secret", Headers(), b"fake-secret"))

    monkeypatch.setattr(module, "connect", rejected)
    with pytest.raises(ProviderError) as error:
        asyncio.run(provider()._connect())  # type: ignore
    assert error.value.retryable == retryable
    assert "fake-secret" not in str(error.value)


def test_opted_in_smoke_closed_session_is_bounded_and_skips_stream(monkeypatch, capsys):  # type: ignore
    from scripts import smoke_test

    monkeypatch.setenv("RUN_ALPACA_SMOKE_TEST", "1")
    settings = Settings(
        _env_file=None,
        postgres_password=SecretStr("test"),
        alpaca_api_key_id=SecretStr("fake-key"),
        alpaca_api_secret_key=SecretStr("fake-secret"),
    )
    p = provider()  # type: ignore
    monkeypatch.setattr(smoke_test, "Settings", lambda **kwargs: settings)
    monkeypatch.setattr(smoke_test, "AlpacaMarketDataProvider", lambda **kwargs: p)
    monkeypatch.setattr(smoke_test, "regular_session", lambda now: None)
    assert asyncio.run(smoke_test.main()) == 0
    output = capsys.readouterr().out
    assert "PASS" in output and "market_closed / streaming not validated" in output
    assert "fake-key" not in output and "fake-secret" not in output
