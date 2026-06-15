from __future__ import annotations

import csv
import io
import os
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
BARCHART_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
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
    ) -> None:
        self._client = client or BarchartBreadthClient()
        self._ttl_seconds = max(0, int(ttl_seconds))
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

        settings = MARKET_BREADTH_SYMBOLS[symbol]
        body = self._client.fetch_csv(symbol, {"data": settings["data"]})
        parsed = parse_barchart_csv(body)
        bars = [bar for bar in parsed if bar.symbol == symbol]
        if not bars:
            bars = parsed
        bars = sorted(bars, key=lambda bar: bar.date)

        with self._lock:
            self._cache[symbol] = (now + self._ttl_seconds, bars)
        return list(bars)


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
