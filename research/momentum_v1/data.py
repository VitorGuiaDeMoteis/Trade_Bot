"""Isolated historical-data acquisition and validation."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

DEFAULT_ARTIFACTS_DIR = Path(".artifacts/research/momentum_v1")
SUBSTITUTIONS = {"SPY": "VTI", "EFA": "VXUS", "EEM": "IEMG", "TLT": "VGLT", "GLD": "IAU", "DBC": "PDBC", "VNQ": "SCHH"}


def get_file_hash(file_path: Path) -> str:
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def enforce_date_range(data: pd.DataFrame, limit_date: str = "2025-12-31") -> None:
    index = pd.DatetimeIndex(data.index).tz_localize(None)
    cutoff = pd.Timestamp(limit_date) + pd.Timedelta(days=1)
    if (index >= cutoff).any():
        raise ValueError("DATA_RANGE_VIOLATION: observations at or after 2026-01-01 are forbidden")


def _normalize_yahoo(data: pd.DataFrame) -> pd.DataFrame:
    normalized = data.copy()
    if isinstance(normalized.columns, pd.MultiIndex) and normalized.columns.nlevels == 2:
        if "Close" not in normalized.columns.get_level_values(0):
            normalized.columns = normalized.columns.swaplevel(0, 1)
    normalized.index = pd.DatetimeIndex(normalized.index).tz_localize(None).normalize()
    return normalized.sort_index().sort_index(axis=1)


def fetch_yahoo(symbols: list[str], start: str, end: str) -> pd.DataFrame:
    yf = importlib.import_module("yfinance")

    exclusive_end = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    downloaded = yf.download(symbols, start=start, end=exclusive_end, group_by="ticker", auto_adjust=True, progress=False)
    data = _normalize_yahoo(downloaded)
    if data.empty:
        raise RuntimeError("Yahoo returned no historical data")
    enforce_date_range(data, end)
    return data


def fetch_alpaca_crosscheck(symbols: list[str], start: str, end: str) -> pd.DataFrame | None:
    api_key = os.environ.get("APCA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY_ID")
    api_secret = os.environ.get("APCA_API_SECRET_KEY") or os.environ.get("ALPACA_API_SECRET_KEY")
    if not api_key or not api_secret:
        return None
    url = "https://data.alpaca.markets/v2/stocks/bars"
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}
    params: dict[str, str] = {
        "symbols": ",".join(symbols),
        "start": f"{start}T00:00:00Z",
        "end": f"{end}T23:59:59Z",
        "timeframe": "1Day",
        "adjustment": "all",
    }
    collected: dict[str, list[dict[str, object]]] = {}
    while True:
        response = requests.get(url, headers=headers, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        for symbol, bars in payload.get("bars", {}).items():
            collected.setdefault(str(symbol), []).extend(bars)
        token = payload.get("next_page_token")
        if not token:
            break
        params["page_token"] = str(token)
    if not collected:
        raise RuntimeError("Alpaca historical market-data cross-check returned no bars")
    series: list[pd.Series] = []
    for symbol, bars in collected.items():
        frame = pd.DataFrame(bars)
        frame.index = pd.to_datetime(frame["t"], utc=True).dt.tz_localize(None).dt.normalize()
        for source, label in (("o", "Open"), ("c", "Close")):
            item = frame[source].astype(float)
            item.name = (label, symbol)
            series.append(item)
    output = pd.concat(series, axis=1).sort_index()
    enforce_date_range(output, end)
    return output


def fetch_fred_dtb3(start: str, end: str) -> pd.DataFrame:
    response = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3", timeout=60)
    response.raise_for_status()
    frame = pd.read_csv(StringIO(response.text), na_values=".")
    frame["observation_date"] = pd.to_datetime(frame["observation_date"])
    frame = frame.set_index("observation_date")
    frame = frame.loc[(frame.index >= pd.Timestamp(start)) & (frame.index <= pd.Timestamp(end))]
    series = frame["DTB3"].astype(float).ffill()
    series.name = ("Close", "DTB3")
    output = series.to_frame()
    enforce_date_range(output, end)
    return output


def validate_primary_history(data: pd.DataFrame, universe: list[str], first_valid_signal: str) -> None:
    signal = pd.Timestamp(first_valid_signal)
    required_start = signal - pd.DateOffset(months=12)
    index = pd.DatetimeIndex(data.index).tz_localize(None)
    for symbol in universe:
        for field in ("Open", "Close"):
            if (field, symbol) not in data.columns:
                raise ValueError(f"PRIMARY_DATA_MISSING: {field}/{symbol}")
        closes = data[("Close", symbol)].dropna()
        if closes.empty or pd.Timestamp(closes.index[0]) > required_start:
            raise ValueError(f"INSUFFICIENT_PRIMARY_HISTORY: {symbol}")
        if closes.loc[:signal].empty or index[index <= signal].empty:
            raise ValueError(f"INSUFFICIENT_PRIMARY_HISTORY: {symbol} at first signal")


def validate_artifacts(artifacts_dir: Path, config: dict[str, object]) -> dict[str, str]:
    expected = {
        "primary_dataset_hash": artifacts_dir / "primary.parquet",
        "fred_hash": artifacts_dir / "fred_dtb3.parquet",
        "alpaca_crosscheck_hash": artifacts_dir / "alpaca_crosscheck.parquet",
        "substitution_yahoo_hash": artifacts_dir / "substitutes.parquet",
    }
    for path in expected.values():
        if not path.is_file():
            raise FileNotFoundError(f"Required research artifact is missing: {path}")
        enforce_date_range(pd.read_parquet(path))
    primary = pd.read_parquet(expected["primary_dataset_hash"])
    universe_value = config["universe"]
    if not isinstance(universe_value, list):
        raise TypeError("config.universe must be a list")
    universe = [str(symbol) for symbol in universe_value]
    data_config = config["data"]
    if not isinstance(data_config, dict):
        raise TypeError("config.data must be an object")
    validate_primary_history(primary, universe, str(data_config["first_valid_signal"]))
    return {name: get_file_hash(path) for name, path in expected.items()}


def load_market_data(artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR) -> pd.DataFrame:
    primary = pd.read_parquet(artifacts_dir / "primary.parquet").sort_index()
    primary.index = pd.DatetimeIndex(primary.index).tz_localize(None)
    fred = pd.read_parquet(artifacts_dir / "fred_dtb3.parquet").sort_index()
    fred.index = pd.DatetimeIndex(fred.index).tz_localize(None)
    dtb3 = fred[("Close", "DTB3")] if ("Close", "DTB3") in fred.columns else fred["DTB3"]
    aligned = dtb3.reindex(primary.index, method="ffill")
    if aligned.isna().any():
        raise ValueError("FRED DTB3 does not cover all primary market sessions")
    output = primary.copy()
    output[("Close", "DTB3")] = aligned.astype(float)
    return output


def fetch_data(config_path: Path, artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR) -> None:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    universe = [str(symbol) for symbol in config["universe"]]
    data_config = config["data"]
    if not isinstance(data_config, dict):
        raise TypeError("config.data must be an object")
    start, end = str(data_config["start_date"]), str(data_config["end_date"])
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    primary = fetch_yahoo(universe, start, end)
    validate_primary_history(primary, universe, str(data_config["first_valid_signal"]))
    primary.to_parquet(artifacts_dir / "primary.parquet")
    fetch_fred_dtb3(start, end).to_parquet(artifacts_dir / "fred_dtb3.parquet")
    fetch_yahoo(list(SUBSTITUTIONS.values()), start, end).to_parquet(artifacts_dir / "substitutes.parquet")
    crosscheck = fetch_alpaca_crosscheck(universe, start, end)
    if crosscheck is not None:
        crosscheck.to_parquet(artifacts_dir / "alpaca_crosscheck.parquet")
    hashes = validate_artifacts(artifacts_dir, config)
    metadata = {**hashes, "symbols": universe, "start_date": start, "end_date": end}
    (artifacts_dir / "data_meta.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
