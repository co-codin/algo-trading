from __future__ import annotations

import csv
import io
import os
from pathlib import Path
import threading
import time
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Protocol

import httpx

BARCHART_HOME = "https://www.barchart.com/"
BARCHART_QUERY_URL = (
    "https://www.barchart.com/proxies/timeseries/historical/queryeod.ashx"
)
BARCHART_COOKIE_TTL_SECONDS = 600
MARKET_BREADTH_CACHE_TTL_SECONDS = int(
    os.environ.get("MARKET_BREADTH_CACHE_TTL_SECONDS", "3600")
)
MARKET_BREADTH_DATA_DIR = os.environ.get(
    "MARKET_BREADTH_DATA_DIR",
    "historical_data/breadth",
)
BARCHART_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MARKET_BREADTH_CSV_FIELDS = ["symbol", "date", "open", "high", "low", "close", "volume"]
BARCHART_QUERY_DEFAULTS = {
    "data": "daily",
    "maxrecords": "640",
    "volume": "contract",
    "order": "asc",
    "dividends": "false",
    "backadjust": "false",
    "daystoexpiration": "1",
    "contractroll": "combined",
    "splits": "true",
    "padded": "false",
}
PUT_CALL_SYMBOL = "$CPC"

_PERIODS = [
    ("FD", "5-day"),
    ("TW", "20-day"),
    ("FI", "50-day"),
    ("OH", "100-day"),
    ("TH", "200-day"),
]
_INDEXES = [
    ("S&P 500", "$S5"),
    ("Nasdaq 100", "$ND"),
    ("NYSE", "$NC"),
]
MARKET_BREADTH_GROUPS: list[dict[str, Any]] = [
    {
        "name": name,
        "items": [
            {
                "symbol": f"{prefix}{suffix}",
                "label": f"{name} {period}",
                "period": period,
                "data": "daily",
            }
            for suffix, period in _PERIODS
        ],
    }
    for name, prefix in _INDEXES
]

MARKET_BREADTH_SYMBOLS: dict[str, dict[str, str]] = {
    item["symbol"]: {
        "label": item["label"],
        "period": item["period"],
        "data": item["data"],
    }
    for group in MARKET_BREADTH_GROUPS
    for item in group["items"]
}
MARKET_BREADTH_SYMBOLS[PUT_CALL_SYMBOL] = {
    "label": "CBOE Put/Call Ratio",
    "period": "weekly",
    "data": "weekly",
}
ALLOWED_MARKET_BREADTH_SYMBOLS = frozenset(MARKET_BREADTH_SYMBOLS)


@dataclass(frozen=True)
class MarketBreadthBar:
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class BarchartCsvClient(Protocol):
    def fetch_csv(
        self,
        symbol: str,
        overrides: dict[str, str] | None = None,
    ) -> bytes:
        ...


class BarchartBreadthClient:
    def __init__(self, timeout: float = 12.0) -> None:
        self._timeout = timeout
        self._client: httpx.Client | None = None
        self._xsrf_token = ""
        self._primed_at = 0.0
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
            self._client = None
            self._xsrf_token = ""
            self._primed_at = 0.0

    def fetch_csv(
        self,
        symbol: str,
        overrides: dict[str, str] | None = None,
    ) -> bytes:
        symbol = normalize_breadth_symbol(symbol)
        with self._lock:
            response = self._fetch_locked(symbol, overrides)
            if response.status_code in {401, 403}:
                self._prime_locked(force=True)
                response = self._fetch_locked(symbol, overrides)
        if response.status_code >= 400:
            raise RuntimeError(f"Barchart returned HTTP {response.status_code} for {symbol}")
        return response.content

    def _client_inner(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                follow_redirects=True,
                timeout=self._timeout,
                headers={"User-Agent": BARCHART_USER_AGENT},
            )
        return self._client

    def _prime_locked(self, force: bool = False) -> None:
        if (
            not force
            and self._xsrf_token
            and time.monotonic() - self._primed_at < BARCHART_COOKIE_TTL_SECONDS
        ):
            return
        client = self._client_inner()
        response = client.get(
            BARCHART_HOME,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": BARCHART_HOME,
            },
        )
        response.raise_for_status()
        raw_token = client.cookies.get("XSRF-TOKEN") or response.cookies.get("XSRF-TOKEN")
        if not raw_token:
            raise RuntimeError("Barchart did not return an XSRF token")
        self._xsrf_token = urllib.parse.unquote(raw_token)
        self._primed_at = time.monotonic()

    def _fetch_locked(
        self,
        symbol: str,
        overrides: dict[str, str] | None,
    ) -> httpx.Response:
        self._prime_locked()
        params = {
            "symbol": symbol,
            **BARCHART_QUERY_DEFAULTS,
            **(overrides or {}),
        }
        return self._client_inner().get(
            BARCHART_QUERY_URL,
            params=params,
            headers={
                "Accept": "text/csv,*/*;q=0.1",
                "Referer": f"https://www.barchart.com/stocks/quotes/{urllib.parse.quote(symbol, safe='')}",
                "X-XSRF-TOKEN": self._xsrf_token,
                "X-Requested-With": "XMLHttpRequest",
            },
        )


class MarketBreadthService:
    def __init__(
        self,
        client: BarchartCsvClient | None = None,
        ttl_seconds: int = MARKET_BREADTH_CACHE_TTL_SECONDS,
        data_dir: str | Path | None = MARKET_BREADTH_DATA_DIR,
        refresh_seconds: int = MARKET_BREADTH_CACHE_TTL_SECONDS,
    ) -> None:
        self._client = client or BarchartBreadthClient()
        self._ttl_seconds = max(0, int(ttl_seconds))
        self._data_dir = Path(data_dir) if data_dir else None
        self._refresh_seconds = max(0, int(refresh_seconds))
        self._cache: dict[str, tuple[float, list[MarketBreadthBar]]] = {}
        self._lock = threading.Lock()

    def payload(self, symbols: list[str] | None = None) -> dict[str, Any]:
        return market_breadth_payload(self, symbols=symbols)

    def bars_for_symbol(self, symbol: str) -> list[MarketBreadthBar]:
        symbol = normalize_breadth_symbol(symbol)
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(symbol)
            if cached and cached[0] > now:
                return list(cached[1])

        stored_bars = self._read_cached_bars(symbol)
        cache_path = self._csv_path(symbol)
        if stored_bars and cache_path and self._csv_is_fresh(cache_path):
            bars = stored_bars
        else:
            bars = self._fetch_and_store_bars(symbol, stored_bars)

        with self._lock:
            self._cache[symbol] = (now + self._ttl_seconds, bars)
        return list(bars)

    def _fetch_and_store_bars(
        self,
        symbol: str,
        stored_bars: list[MarketBreadthBar],
    ) -> list[MarketBreadthBar]:
        settings = MARKET_BREADTH_SYMBOLS[symbol]
        try:
            body = self._client.fetch_csv(symbol, {"data": settings["data"]})
        except Exception:
            if stored_bars:
                return stored_bars
            raise
        parsed = parse_barchart_csv(body)
        fetched_bars = matching_symbol_bars(symbol, parsed)
        bars = merge_breadth_bars([*stored_bars, *fetched_bars])
        if not bars:
            bars = fetched_bars

        cache_path = self._csv_path(symbol)
        if cache_path and bars:
            write_breadth_bars_to_csv(cache_path, bars)
        return bars

    def _read_cached_bars(self, symbol: str) -> list[MarketBreadthBar]:
        cache_path = self._csv_path(symbol)
        if not cache_path or not cache_path.is_file():
            return []
        return matching_symbol_bars(symbol, parse_barchart_csv(cache_path.read_bytes()))

    def _csv_is_fresh(self, path: Path) -> bool:
        if self._refresh_seconds <= 0:
            return False
        return time.time() - path.stat().st_mtime < self._refresh_seconds

    def _csv_path(self, symbol: str) -> Path | None:
        if self._data_dir is None:
            return None
        return self._data_dir / f"{symbol_filename(symbol)}.csv"


def market_breadth_payload(
    service: MarketBreadthService | None = None,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    breadth_service = service or MarketBreadthService()
    selected_symbols = normalize_breadth_symbols(symbols) if symbols else default_symbols()
    series = {
        symbol: series_payload(symbol, breadth_service.bars_for_symbol(symbol))
        for symbol in selected_symbols
    }
    return {
        "ok": True,
        "source": "Barchart",
        "groups": MARKET_BREADTH_GROUPS,
        "series": series,
        "put_call_symbol": PUT_CALL_SYMBOL,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def parse_barchart_csv(body: bytes) -> list[MarketBreadthBar]:
    rows: dict[tuple[str, date], MarketBreadthBar] = {}
    reader = csv.reader(io.StringIO(body.decode("utf-8", errors="replace")))
    for row in reader:
        if len(row) < 6:
            continue
        symbol = row[0].strip().strip('"')
        try:
            parsed_date = date.fromisoformat(row[1].strip().strip('"'))
            open_price = float(row[2])
            high_price = float(row[3])
            low_price = float(row[4])
            close_price = float(row[5])
            volume = float(row[6]) if len(row) > 6 and row[6] else 0.0
        except ValueError:
            continue
        rows[(symbol, parsed_date)] = MarketBreadthBar(
            symbol=symbol,
            date=parsed_date,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
        )
    return sorted(rows.values(), key=lambda bar: (bar.date, bar.symbol))


def write_breadth_bars_to_csv(path: Path, bars: list[MarketBreadthBar]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MARKET_BREADTH_CSV_FIELDS)
        writer.writeheader()
        for bar in merge_breadth_bars(bars):
            writer.writerow(
                {
                    "symbol": bar.symbol,
                    "date": bar.date.isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
            )
    return path


def matching_symbol_bars(
    symbol: str,
    bars: list[MarketBreadthBar],
) -> list[MarketBreadthBar]:
    filtered = [bar for bar in bars if bar.symbol == symbol]
    return merge_breadth_bars(filtered or bars)


def merge_breadth_bars(bars: list[MarketBreadthBar]) -> list[MarketBreadthBar]:
    rows = {(bar.symbol, bar.date): bar for bar in bars}
    return sorted(rows.values(), key=lambda bar: (bar.date, bar.symbol))


def symbol_filename(symbol: str) -> str:
    return symbol.strip().lstrip("$").replace("/", "_").replace("=", "_")


def series_payload(symbol: str, bars: list[MarketBreadthBar]) -> dict[str, Any]:
    settings = MARKET_BREADTH_SYMBOLS[symbol]
    return {
        "symbol": symbol,
        "label": settings["label"],
        "period": settings["period"],
        "data": settings["data"],
        "candles": [bar_payload(bar) for bar in bars],
    }


def bar_payload(bar: MarketBreadthBar) -> dict[str, Any]:
    timestamp = int(
        datetime(
            bar.date.year,
            bar.date.month,
            bar.date.day,
            tzinfo=timezone.utc,
        ).timestamp()
    )
    return {
        "time": timestamp,
        "date": bar.date.isoformat(),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }


def default_symbols() -> list[str]:
    symbols = [
        item["symbol"]
        for group in MARKET_BREADTH_GROUPS
        for item in group["items"]
    ]
    return [*symbols, PUT_CALL_SYMBOL]


def normalize_breadth_symbols(symbols: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_symbol in symbols:
        symbol = normalize_breadth_symbol(raw_symbol)
        if symbol not in normalized:
            normalized.append(symbol)
    return normalized


def normalize_breadth_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized not in ALLOWED_MARKET_BREADTH_SYMBOLS:
        raise ValueError(f"unsupported market breadth symbol: {symbol}")
    return normalized
