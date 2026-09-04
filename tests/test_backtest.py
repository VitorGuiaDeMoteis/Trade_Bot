import ast
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_UP, localcontext
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

import pytest

from packages.domain.backtest import Dataset, encode, manifest
from packages.domain.market import Candle
from packages.domain.market_bar import MarketBar, series_id
from packages.domain.paper import PaperConfig
from services.backtesting.artifacts import load_manifest, write_artifact
from services.backtesting.engine import run


def dataset(prices: list[tuple[str, str]], symbols: tuple[str, ...] = ("SPY",)) -> Dataset:
    bars = []
    for symbol in symbols:
        for i, (opening, closing) in enumerate(prices):
            opened = datetime(2026, 1, 2, 10, tzinfo=UTC) + timedelta(hours=i)
            bar = MarketBar(
                "alpaca",
                symbol,
                "1h",
                opened,
                opened + timedelta(hours=1),
                D(opening),
                max(D(opening), D(closing)),
                min(D(opening), D(closing)),
                D(closing),
                100,
                True,
            )
            bars.append(
                Candle(
                    bar.candle_id,
                    series_id("alpaca", symbol, "1h"),
                    i + 1,
                    symbol,
                    "1h",
                    "alpaca",
                    bar.open_time,
                    bar.close_time,
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    100,
                    None,
                )
            )
    return Dataset(tuple(bars))


def test_hand_calculated_winner_loser_metrics_and_drawdown() -> None:
    data = dataset(
        [
            ("100", "101"),
            ("100", "99"),
            ("110", "110"),
            ("110", "111"),
            ("110", "109"),
            ("100", "100"),
            ("100", "100"),
        ]
    )
    result = run(data, PaperConfig(fee_bps=D(0), slippage_bps=D(0)))
    m = result["metrics"]
    for key, expected in {
        "final_equity": "10010",
        "return_pct": "0.1",
        "max_drawdown": "90",
        "max_drawdown_pct": "0.8910891089",
        "win_rate_pct": "50",
        "average_profit": "100",
        "average_loss": "-90",
        "profit_factor": "1.1111111111",
        "total_pnl_net": "10",
        "fees": "0",
        "slippage": "0",
    }.items():
        assert D(m[key]) == D(expected), key
    assert m["closed_trades"] == 2 and m["orders"] == m["fills"] == 4
    assert m["open_positions"] == 0
    assert [D(t["net_pnl"]) for t in result["trades"]] == [D(100), D(-90)]
    for frame in result["equity_curve"]:
        assert D(frame["equity"]) == D(frame["cash"]) + D(frame["market_value"])
        assert D(frame["total_pnl"]) == D(frame["realized_pnl"]) + D(frame["unrealized_pnl"]) - D(
            frame["fees"]
        )


def test_same_paper_executor_fee_and_slippage_arithmetic() -> None:
    data = dataset([("100", "101"), ("100", "99"), ("110", "110")])
    result = run(data)
    m = result["metrics"]
    assert D(m["final_equity"]) == D("10088.8660045")
    assert D(m["fees"]) == D(".1889955")
    assert D(m["slippage"]) == D(".945")
    assert D(m["closed_pnl_net"]) == D("88.8660045")
    assert m["profit_factor"] is None and m["profit_factor_status"] == "no_losses"
    assert D(
        run(data, PaperConfig(fee_bps=D(0), slippage_bps=D(0)))["metrics"]["final_equity"]
    ) == D("10100")


def test_open_position_fee_is_not_lost_or_double_counted() -> None:
    result = run(dataset([("100", "101"), ("100", "101")]))
    m = result["metrics"]
    assert m["closed_trades"] == 0 and m["open_positions"] == 1
    assert m["fills"] == 1 and len(result["signals"]) == 2
    assert m["win_rate_pct"] is None and m["profit_factor"] is None
    assert D(m["total_pnl_net"]) == D(m["unrealized_pnl_gross"]) - D(m["open_entry_fees"])
    assert D(m["open_entry_fees"]) == D(m["fees"]) == D(".090045")


@pytest.mark.parametrize("kind", ["empty", "hold", "breakeven", "loss"])
def test_degenerate_metrics_are_explicit_finite_json(kind: str) -> None:
    prices = {
        "empty": [],
        "hold": [("100", "100"), ("100", "100")],
        "breakeven": [("100", "101"), ("100", "99"), ("100", "100")],
        "loss": [("100", "101"), ("100", "99"), ("90", "90")],
    }[kind]
    result = run(dataset(prices), PaperConfig(fee_bps=D(0), slippage_bps=D(0)))
    m = result["metrics"]
    assert "Infinity" not in encode(result) and "NaN" not in encode(result)
    if kind == "loss":
        assert D(m["profit_factor"]) == 0 and D(m["win_rate_pct"]) == 0
        assert D(m["average_loss"]) == -100
    else:
        assert m["profit_factor"] is None
    if kind == "breakeven":
        assert m["breakeven_trades"] == 1 and D(m["win_rate_pct"]) == 0


def test_costs_turn_gross_breakeven_into_net_loser() -> None:
    m = run(dataset([("100", "101"), ("100", "99"), ("100", "100")]))["metrics"]
    assert m["losing_trades"] == 1 and m["winning_trades"] == 0
    assert D(m["total_pnl_net"]) < 0


def test_no_lookahead_current_closes_or_future_suffix() -> None:
    early = dataset([("100", "101"), ("100", "1000000")], ("AAPL", "SPY"))
    report = run(early)
    assert [o["quantity"] for o in report["outcomes"]] == [9, 9]
    assert all(D(o["reference_price"]) == 100 for o in report["outcomes"])
    extended = dataset([("100", "101"), ("100", "1000000"), ("1000000", "1")], ("AAPL", "SPY"))
    later = run(extended)
    assert report["equity_curve"] == later["equity_curve"][:2]
    for a, b in zip(report["outcomes"], later["outcomes"], strict=False):
        for key in ("status", "reason", "quantity", "price", "fee", "slippage", "realized_pnl"):
            assert a[key] == b[key]
    for outcome in later["outcomes"]:
        assert outcome["signal"]["generated_at"] <= outcome["executed_at"]


def test_hold_and_expired_risk_do_not_call_executor() -> None:
    bars = dataset([("100", "101"), ("100", "100"), ("100", "100")]).candles
    delayed = Dataset(
        (
            bars[0],
            *[
                replace(
                    b,
                    open_time=b.open_time + timedelta(days=1),
                    close_time=b.close_time + timedelta(days=1),
                )
                for b in bars[1:]
            ],
        )
    )
    with patch(
        "services.backtesting.engine.PaperExecutor.execute",
        side_effect=AssertionError("unexpected execution"),
    ):
        result = run(delayed)
    assert result["metrics"]["orders"] == 0
    assert [o["reason"] for o in result["outcomes"]] == ["risk_rejected", "hold"]


def test_input_order_context_and_restart_do_not_change_result(tmp_path: Path) -> None:
    data = dataset([("100", "101"), ("100", "99"), ("110", "110")], ("TSLA", "AAPL", "SPY"))
    expected = run(data)
    assert expected == run(Dataset(tuple(reversed(data.candles))))
    assert expected == run(data, PaperConfig(D("10000.00"), D("1.0"), D("5.0")))
    with localcontext() as ctx:
        ctx.prec = 12
        ctx.rounding = ROUND_UP
        assert expected == run(data)
    path = tmp_path / "frozen.json"
    write_artifact(path, manifest(data, PaperConfig()))
    loaded, config = load_manifest(path)
    assert encode(run(loaded, config)) == encode(expected)
    raw = json.loads(path.read_text())
    raw["candles"][0]["close"] = "200"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="hash"):
        load_manifest(path)


def test_full_allocation_no_margin_or_short() -> None:
    result = run(
        dataset([("100", "101"), ("100", "101")], tuple(f"A{i:02}" for i in range(12))),
        PaperConfig(fee_bps=D(0), slippage_bps=D(0)),
    )
    assert result["metrics"]["fills"] == 10
    assert result["metrics"]["orders"] == 12
    assert D(result["equity_curve"][-1]["cash"]) == 0
    assert all(p["quantity"] == 10 for p in result["positions"])
    assert [o["reason"] for o in result["outcomes"]][-2:] == ["insufficient_simulated_cash"] * 2


@pytest.mark.parametrize("damage", ["duplicate", "partial", "overlap", "float"])
def test_invalid_dataset_fails_before_execution(damage: str) -> None:
    bars = dataset([("100", "101"), ("100", "101")], ("AAPL", "SPY")).candles
    with pytest.raises((ValueError, TypeError)):
        if damage == "duplicate":
            Dataset((*bars, bars[0]))
        elif damage == "partial":
            Dataset((replace(bars[0], is_closed=False),))
        elif damage == "overlap":
            Dataset(
                (
                    bars[0],
                    replace(
                        bars[1],
                        open_time=bars[1].open_time + timedelta(minutes=30),
                        close_time=bars[1].close_time + timedelta(minutes=30),
                    ),
                )
            )
        else:
            Dataset((replace(bars[0], open=100.0),))  # type: ignore[arg-type]


def test_dataset_and_artifact_failure_cannot_partially_change_state(tmp_path: Path) -> None:
    data = dataset([("100", "101")])
    with pytest.raises(FrozenInstanceError):
        data.candles = ()  # type: ignore[misc]
    path = tmp_path / "report.json"
    path.write_text("previous")
    with patch("services.backtesting.artifacts.os.replace", side_effect=OSError("disk error")):
        with pytest.raises(OSError):
            write_artifact(path, run(data))
    assert path.read_text() == "previous"
    assert not list(tmp_path.glob("*.tmp"))


def test_core_has_no_database_network_or_live_paper_imports() -> None:
    path = Path("services/backtesting/engine.py")
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith(
                ("services.api", "services.market_data", "sqlalchemy", "httpx")
            )


@pytest.mark.parametrize("damage", ["cost", "version", "float", "missing"])
def test_manifest_rejects_config_tampering_and_unsupported_payloads(
    tmp_path: Path, damage: str
) -> None:
    from packages.domain.backtest import digest

    path = tmp_path / "input.json"
    write_artifact(path, manifest(dataset([("100", "101")]), PaperConfig()))
    raw = json.loads(path.read_text())
    if damage == "cost":
        raw["config"]["fee_bps"] = "100"  # keep old checksum: do not silently change fees
    else:
        if damage == "version":
            raw["engine_version"] = "future-unknown"
        elif damage == "float":
            raw["candles"][0]["open"] = 100.0
        else:
            del raw["candles"][0]["open"]
        raw.pop("manifest_hash")
        raw["manifest_hash"] = digest(raw)
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        load_manifest(path)


def test_component_version_change_requires_explicit_manifest_version() -> None:
    with patch("services.backtesting.engine.BaseStrategy.VERSION", "different-strategy"):
        with pytest.raises(ValueError, match="version"):
            run(dataset([("100", "101")]))
