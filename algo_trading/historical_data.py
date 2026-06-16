from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from algo_trading.data import (
    BinanceMarketDataClient,
    HistoricalMarketDataClient,
    MAG7_STOCK_SYMBOLS,
    MOEX_BLUECHIP_SYMBOLS,
    MoexSharesMarketDataClient,
    YahooFuturesMarketDataClient,
    load_candles_from_csv,
    trim_candles_to_retention,
    write_candles_to_csv,
)
from algo_trading.models import Candle

HISTORICAL_DATA_DIR = os.environ.get("HISTORICAL_DATA_DIR", "historical_data")
HISTORICAL_CSV_RETENTION_DAYS = int(
    os.environ.get(
        "HISTORICAL_CSV_RETENTION_DAYS",
        os.environ.get("HISTORICAL_RETENTION_DAYS", "1095"),
    )
)
HISTORICAL_CSV_PAGE_LIMIT = int(os.environ.get("HISTORICAL_CSV_PAGE_LIMIT", "1000"))

_MILLISECONDS_PER_DAY = 24 * 60 * 60 * 1000
_CRYPTO_SPOT_MARKET = "crypto_spot"
_CME_FUTURES_MARKET = "cme_futures"
_COMMODITIES_MARKET = "commodities"
_MAG7_STOCKS_MARKET = "mag7_stocks"
_RUSSIAN_BLUECHIPS_MARKET = "russian_bluechips"
_SUPPORTED_INTERVALS = {
    "1m",
    "3m",
    "5m",
    "10m",
    "15m",
    "30m",
    "1h",
    "4h",
    "1d",
    "1w",
    "1M",
}
_US_INDEX_SYMBOLS = {
    "ES",
    "/ES",
    "ES=F",
    "SP500",
    "SP500_FUTURE",
    "NQ",
    "/NQ",
    "NQ=F",
    "NASDAQ",
    "NASDAQ100",
    "NASDAQ_100",
}
_COMMODITY_SYMBOLS = {
    "GC",
    "/GC",
    "GC=F",
    "GOLD",
    "SI",
    "/SI",
    "SI=F",
    "SILVER",
    "NG",
    "/NG",
    "NG=F",
    "NATURALGAS",
    "BZ",
    "/BZ",
    "BZ=F",
    "BRENT",
    "PL",
    "/PL",
    "PL=F",
    "PLATINUM",
    "PA",
    "/PA",
    "PA=F",
    "PALLADIUM",
    "HG",
    "/HG",
    "HG=F",
    "COPPER",
}


@dataclass(frozen=True)
class HistoricalCsvSpec:
    path: Path
    market: str
    symbol: str
    interval: str


class HistoricalCsvRefreshService:
    def __init__(
        self,
        data_dir: str | Path = HISTORICAL_DATA_DIR,
        client_factory: Callable[[str], HistoricalMarketDataClient] | None = None,
        now: Callable[[], datetime] | None = None,
        retention_days: int = HISTORICAL_CSV_RETENTION_DAYS,
        page_limit: int = HISTORICAL_CSV_PAGE_LIMIT,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._client_factory = client_factory or historical_client_for_market
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._retention_days = max(0, int(retention_days))
        self._page_limit = max(1, int(page_limit))

    def refresh_all(self) -> dict[str, int]:
        summary = {"discovered": 0, "refreshed": 0, "pruned": 0, "failed": 0}
        for spec in self.discover_files():
            summary["discovered"] += 1
            try:
                if self.refresh_file(spec):
                    summary["refreshed"] += 1
                if self.prune_file(spec.path):
                    summary["pruned"] += 1
            except Exception:
                summary["failed"] += 1
                try:
                    if self.prune_file(spec.path):
                        summary["pruned"] += 1
                except Exception:
                    pass
        return summary

    def prune_all(self) -> dict[str, int]:
        summary = {"discovered": 0, "pruned": 0, "failed": 0}
        for spec in self.discover_files():
            summary["discovered"] += 1
            try:
                if self.prune_file(spec.path):
                    summary["pruned"] += 1
            except Exception:
                summary["failed"] += 1
        return summary

    def discover_files(self) -> list[HistoricalCsvSpec]:
        if not self._data_dir.is_dir():
            return []

        specs: list[HistoricalCsvSpec] = []
        for path in sorted(self._data_dir.rglob("*.csv")):
            try:
                relative = path.relative_to(self._data_dir)
            except ValueError:
                continue
            if not path.is_file() or "breadth" in relative.parts:
                continue
            parsed = _parse_historical_csv_filename(path)
            if parsed is None:
                continue
            symbol, interval = parsed
            specs.append(
                HistoricalCsvSpec(
                    path=path,
                    market=_infer_market(relative, symbol),
                    symbol=symbol,
                    interval=interval,
                )
            )
        return specs

    def refresh_file(self, spec: HistoricalCsvSpec) -> bool:
        end_time = self._current_millis()
        start_time = end_time - (self._retention_days * _MILLISECONDS_PER_DAY)
        existing = load_candles_from_csv(spec.path) if spec.path.is_file() else []
        fetched = self._client_factory(spec.market).get_historical_klines(
            spec.symbol,
            spec.interval,
            start_time,
            end_time,
            self._page_limit,
        )
        merged = [*existing, *fetched]
        if not merged:
            return False
        write_candles_to_csv(
            self._trim_to_clock_retention(merged, reference_millis=end_time),
            spec.path,
            retention_days=self._retention_days,
        )
        return True

    def prune_file(self, path: str | Path) -> bool:
        csv_path = Path(path)
        if not csv_path.is_file():
            return False
        current = load_candles_from_csv(csv_path)
        retained = self._trim_to_clock_retention(current)
        if len(retained) == len(current):
            return False
        write_candles_to_csv(retained, csv_path, retention_days=self._retention_days)
        return True

    def _trim_to_clock_retention(
        self,
        candles: Sequence[Candle],
        reference_millis: int | None = None,
    ) -> list[Candle]:
        retained = trim_candles_to_retention(candles, self._retention_days)
        if self._retention_days <= 0:
            return retained
        now_millis = reference_millis if reference_millis is not None else self._current_millis()
        cutoff = now_millis - (self._retention_days * _MILLISECONDS_PER_DAY)
        return [candle for candle in retained if candle.open_time >= cutoff]

    def _current_millis(self) -> int:
        return int(self._now().astimezone(timezone.utc).timestamp() * 1000)


def historical_client_for_market(market: str) -> HistoricalMarketDataClient:
    if market == _CRYPTO_SPOT_MARKET:
        return BinanceMarketDataClient()
    if market in {_CME_FUTURES_MARKET, _COMMODITIES_MARKET, _MAG7_STOCKS_MARKET}:
        return YahooFuturesMarketDataClient()
    if market == _RUSSIAN_BLUECHIPS_MARKET:
        return MoexSharesMarketDataClient()
    raise ValueError(f"unsupported market: {market}")


def _parse_historical_csv_filename(path: Path) -> tuple[str, str] | None:
    parts = path.stem.split("-")
    if len(parts) >= 3 and parts[-1].lower().endswith("d") and parts[-2] in _SUPPORTED_INTERVALS:
        return "-".join(parts[:-2]).upper(), parts[-2]
    if len(parts) >= 2 and parts[-1] in _SUPPORTED_INTERVALS:
        return "-".join(parts[:-1]).upper(), parts[-1]
    return None


def _infer_market(relative_path: Path, symbol: str) -> str:
    symbol_key = symbol.upper()
    if relative_path.parent.name == _MAG7_STOCKS_MARKET or symbol_key in MAG7_STOCK_SYMBOLS:
        return _MAG7_STOCKS_MARKET
    if relative_path.parent.name == _RUSSIAN_BLUECHIPS_MARKET or symbol_key in MOEX_BLUECHIP_SYMBOLS:
        return _RUSSIAN_BLUECHIPS_MARKET
    if symbol_key in _COMMODITY_SYMBOLS:
        return _COMMODITIES_MARKET
    if symbol_key in _US_INDEX_SYMBOLS:
        return _CME_FUTURES_MARKET
    return _CRYPTO_SPOT_MARKET
