from __future__ import annotations

import csv
import io
import os
import re
from pathlib import Path
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Protocol

import httpx

BARCHART_HOME = "https://www.barchart.com/"
BARCHART_QUERY_URL = (
    "https://www.barchart.com/proxies/timeseries/historical/queryeod.ashx"
)
CBOE_DAILY_MARKET_STATISTICS_URL = (
    "https://www.cboe.com/markets/us/options/market-statistics/daily/"
)
CBOE_PUT_CALL_CSV_URLS = (
    "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/pcratioarchive.csv",
    "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/totalpcarchive.csv",
    "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/totalpc.csv",
)
CBOE_DAILY_HISTORY_START = date(2019, 10, 7)
BARCHART_COOKIE_TTL_SECONDS = 600
MARKET_BREADTH_CACHE_TTL_SECONDS = int(
    os.environ.get("MARKET_BREADTH_CACHE_TTL_SECONDS", "3600")
)
CBOE_PUT_CALL_BACKFILL_WORKERS = int(
    os.environ.get("CBOE_PUT_CALL_BACKFILL_WORKERS", "6")
)
MARKET_BREADTH_DATA_DIR = os.environ.get(
    "MARKET_BREADTH_DATA_DIR",
    "historical_data/breadth",
)
MARKET_BREADTH_RETENTION_DAYS = int(
    os.environ.get("MARKET_BREADTH_RETENTION_DAYS", "365")
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
    "label": "Cboe Total Put/Call Ratio",
    "period": "daily",
    "data": "daily",
    "source": "Cboe",
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


@dataclass(frozen=True)
class CboeDailyPutCallSnapshot:
    selected_date: date | None
    prev_trading_day: date | None
    bar: MarketBreadthBar | None


class BarchartCsvClient(Protocol):
    def fetch_csv(
        self,
        symbol: str,
        overrides: dict[str, str] | None = None,
    ) -> bytes:
        ...


class CboePutCallDataClient(Protocol):
    def fetch_historical_csvs(self) -> list[bytes]:
        ...

    def fetch_daily_page(self, trading_date: date | None = None) -> bytes:
        ...

    def fetch_daily_pages(self, trading_dates: list[date]) -> dict[date, bytes]:
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


class CboePutCallClient:
    def __init__(
        self,
        timeout: float = 12.0,
        historical_urls: tuple[str, ...] = CBOE_PUT_CALL_CSV_URLS,
        daily_url: str = CBOE_DAILY_MARKET_STATISTICS_URL,
        backfill_workers: int = CBOE_PUT_CALL_BACKFILL_WORKERS,
    ) -> None:
        self._timeout = timeout
        self._historical_urls = historical_urls
        self._daily_url = daily_url
        self._backfill_workers = max(1, int(backfill_workers))

    def fetch_historical_csvs(self) -> list[bytes]:
        with self._client() as client:
            bodies: list[bytes] = []
            for url in self._historical_urls:
                response = client.get(url)
                response.raise_for_status()
                bodies.append(response.content)
            return bodies

    def fetch_daily_page(self, trading_date: date | None = None) -> bytes:
        with self._client() as client:
            return self._fetch_daily_page_with_client(client, trading_date)

    def fetch_daily_pages(self, trading_dates: list[date]) -> dict[date, bytes]:
        unique_dates = list(dict.fromkeys(trading_dates))
        if not unique_dates:
            return {}
        if len(unique_dates) == 1:
            trading_date = unique_dates[0]
            return {trading_date: self.fetch_daily_page(trading_date)}

        workers = min(self._backfill_workers, len(unique_dates))
        results: dict[date, bytes] = {}
        with self._client() as client:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        self._fetch_daily_page_with_client,
                        client,
                        trading_date,
                    ): trading_date
                    for trading_date in unique_dates
                }
                for future in as_completed(futures):
                    trading_date = futures[future]
                    results[trading_date] = future.result()
        return results

    def _client(self) -> httpx.Client:
        return httpx.Client(
            follow_redirects=True,
            timeout=self._timeout,
            headers={
                "Accept": "text/html,text/csv,*/*;q=0.1",
                "User-Agent": BARCHART_USER_AGENT,
            },
        )

    def _fetch_daily_page_with_client(
        self,
        client: httpx.Client,
        trading_date: date | None,
    ) -> bytes:
        params = {"dt": trading_date.isoformat()} if trading_date else None
        response = client.get(self._daily_url, params=params)
        response.raise_for_status()
        return response.content


class MarketBreadthService:
    def __init__(
        self,
        client: BarchartCsvClient | None = None,
        put_call_client: CboePutCallDataClient | None = None,
        ttl_seconds: int = MARKET_BREADTH_CACHE_TTL_SECONDS,
        data_dir: str | Path | None = MARKET_BREADTH_DATA_DIR,
        refresh_seconds: int = MARKET_BREADTH_CACHE_TTL_SECONDS,
        retention_days: int = MARKET_BREADTH_RETENTION_DAYS,
    ) -> None:
        self._client = client or BarchartBreadthClient()
        self._put_call_client = put_call_client or CboePutCallClient()
        self._ttl_seconds = max(0, int(ttl_seconds))
        self._data_dir = Path(data_dir) if data_dir else None
        self._refresh_seconds = max(0, int(refresh_seconds))
        self._retention_days = max(0, int(retention_days))
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

    def refresh_default_symbols(self) -> dict[str, int]:
        summary = {"refreshed": 0, "failed": 0}
        for symbol in default_symbols():
            try:
                self.bars_for_symbol(symbol)
            except Exception:
                summary["failed"] += 1
            else:
                summary["refreshed"] += 1
        return summary

    def _fetch_and_store_bars(
        self,
        symbol: str,
        stored_bars: list[MarketBreadthBar],
    ) -> list[MarketBreadthBar]:
        if symbol == PUT_CALL_SYMBOL:
            return self._fetch_and_store_put_call_bars(stored_bars)

        settings = MARKET_BREADTH_SYMBOLS[symbol]
        try:
            body = self._client.fetch_csv(symbol, {"data": settings["data"]})
        except Exception:
            if stored_bars:
                return stored_bars
            raise
        parsed = parse_barchart_csv(body)
        fetched_bars = matching_symbol_bars(symbol, parsed)
        bars = trim_breadth_bars_to_retention(
            [*stored_bars, *fetched_bars],
            self._retention_days,
        )
        if not bars:
            bars = fetched_bars

        cache_path = self._csv_path(symbol)
        if cache_path and bars:
            write_breadth_bars_to_csv(
                cache_path,
                bars,
                retention_days=self._retention_days,
            )
        return bars

    def _fetch_and_store_put_call_bars(
        self,
        stored_bars: list[MarketBreadthBar],
    ) -> list[MarketBreadthBar]:
        official_bars: list[MarketBreadthBar] = []
        daily_bars: list[MarketBreadthBar] = []
        latest_snapshot: CboeDailyPutCallSnapshot | None = None

        try:
            historical_bodies = self._put_call_client.fetch_historical_csvs()
            official_bars = parse_cboe_put_call_csvs(historical_bodies)
        except Exception:
            if not stored_bars:
                raise

        try:
            latest_snapshot = parse_cboe_daily_put_call_page(
                self._put_call_client.fetch_daily_page()
            )
        except Exception:
            latest_snapshot = None

        if latest_snapshot is None:
            bars = merge_breadth_bars([*official_bars, *stored_bars])
            if not bars and stored_bars:
                return stored_bars
            cache_path = self._csv_path(PUT_CALL_SYMBOL)
            if cache_path and bars and not stored_bars:
                write_breadth_bars_to_csv(cache_path, bars, retention_days=0)
            return bars

        usable_stored_bars = (
            stored_bars
            if put_call_cache_looks_official(
                stored_bars,
                latest_snapshot.prev_trading_day,
            )
            else []
        )
        latest_trading_day = (
            latest_snapshot.prev_trading_day
            if latest_snapshot.prev_trading_day
            else None
        )
        if latest_trading_day:
            backfill_dates = put_call_backfill_dates(
                [*official_bars, *usable_stored_bars],
                latest_trading_day,
            )
            selected_date = latest_snapshot.selected_date if latest_snapshot else None
            if selected_date:
                backfill_dates = [
                    trading_date
                    for trading_date in backfill_dates
                    if trading_date != selected_date
                ]
            if backfill_dates:
                pages = self._put_call_client.fetch_daily_pages(backfill_dates)
                for trading_date, page in pages.items():
                    snapshot = parse_cboe_daily_put_call_page(page)
                    if snapshot.bar and snapshot.selected_date == trading_date:
                        daily_bars.append(snapshot.bar)

        if latest_snapshot and latest_snapshot.bar:
            daily_bars.append(latest_snapshot.bar)

        bars = merge_breadth_bars([*official_bars, *usable_stored_bars, *daily_bars])
        if not bars and stored_bars:
            return stored_bars

        cache_path = self._csv_path(PUT_CALL_SYMBOL)
        if cache_path and bars:
            write_breadth_bars_to_csv(cache_path, bars, retention_days=0)
        return bars

    def _read_cached_bars(self, symbol: str) -> list[MarketBreadthBar]:
        cache_path = self._csv_path(symbol)
        if not cache_path or not cache_path.is_file():
            return []
        bars = matching_symbol_bars(symbol, parse_barchart_csv(cache_path.read_bytes()))
        if symbol == PUT_CALL_SYMBOL:
            return merge_breadth_bars(bars)
        retained = trim_breadth_bars_to_retention(bars, self._retention_days)
        if len(retained) != len(bars):
            write_breadth_bars_to_csv(
                cache_path,
                retained,
                retention_days=self._retention_days,
            )
        return retained

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
        "source": "Barchart + Cboe",
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


def parse_cboe_put_call_csvs(bodies: list[bytes]) -> list[MarketBreadthBar]:
    bars: list[MarketBreadthBar] = []
    for body in bodies:
        bars.extend(parse_cboe_put_call_csv(body))
    return merge_breadth_bars(bars)


def parse_cboe_put_call_csv(body: bytes) -> list[MarketBreadthBar]:
    rows: dict[tuple[str, date], MarketBreadthBar] = {}
    reader = csv.reader(io.StringIO(body.decode("utf-8-sig", errors="replace")))
    headers: list[str] | None = None
    header_indexes: dict[str, int] = {}
    for row in reader:
        if not row:
            continue
        normalized_headers = [normalize_cboe_header(value) for value in row]
        if headers is None:
            if normalized_headers[0] not in {"date", "trade_date"}:
                continue
            headers = normalized_headers
            header_indexes = cboe_put_call_header_indexes(headers)
            continue
        try:
            parsed_date = parse_cboe_date(row[header_indexes["date"]])
            ratio = parse_cboe_number(row[header_indexes["ratio"]])
        except (IndexError, KeyError, ValueError):
            continue

        volume = 0.0
        total_index = header_indexes.get("total")
        call_index = header_indexes.get("call")
        put_index = header_indexes.get("put")
        try:
            if total_index is not None:
                volume = parse_cboe_number(row[total_index])
            elif call_index is not None and put_index is not None:
                volume = parse_cboe_number(row[call_index]) + parse_cboe_number(
                    row[put_index]
                )
        except (IndexError, ValueError):
            volume = 0.0

        rows[(PUT_CALL_SYMBOL, parsed_date)] = MarketBreadthBar(
            symbol=PUT_CALL_SYMBOL,
            date=parsed_date,
            open=ratio,
            high=ratio,
            low=ratio,
            close=ratio,
            volume=volume,
        )
    return sorted(rows.values(), key=lambda bar: bar.date)


def parse_cboe_daily_put_call_page(body: bytes) -> CboeDailyPutCallSnapshot:
    text = body.decode("utf-8", errors="replace").replace('\\"', '"')
    selected_date = parse_optional_cboe_iso_date(find_cboe_json_value(text, "selectedDate"))
    prev_trading_day = parse_optional_cboe_iso_date(
        find_cboe_json_value(text, "prevTradingDay")
    )
    ratio_match = re.search(
        r'"name":"TOTAL PUT/CALL RATIO","value":"(?P<ratio>[0-9.]+)"',
        text,
    )
    if not selected_date or not ratio_match:
        return CboeDailyPutCallSnapshot(
            selected_date=selected_date,
            prev_trading_day=prev_trading_day,
            bar=None,
        )

    ratio = parse_cboe_number(ratio_match.group("ratio"))
    volume = 0.0
    volume_match = re.search(
        r'"SUM OF ALL PRODUCTS":\[\{"name":"VOLUME","call":(?P<call>[0-9.]+),'
        r'"put":(?P<put>[0-9.]+),"total":(?P<total>[0-9.]+)\}',
        text,
    )
    if volume_match:
        volume = parse_cboe_number(volume_match.group("total"))

    return CboeDailyPutCallSnapshot(
        selected_date=selected_date,
        prev_trading_day=prev_trading_day,
        bar=MarketBreadthBar(
            symbol=PUT_CALL_SYMBOL,
            date=selected_date,
            open=ratio,
            high=ratio,
            low=ratio,
            close=ratio,
            volume=volume,
        ),
    )


def cboe_put_call_header_indexes(headers: list[str]) -> dict[str, int]:
    indexes: dict[str, int] = {}
    for index, header in enumerate(headers):
        if header in {"date", "trade_date"}:
            indexes["date"] = index
        elif header in {"call", "calls"}:
            indexes["call"] = index
        elif header in {"put", "puts"}:
            indexes["put"] = index
        elif header == "total":
            indexes["total"] = index
        elif header == "p/c ratio" or header == "total volume p/c ratio":
            indexes["ratio"] = index
    return indexes


def normalize_cboe_header(value: str) -> str:
    return " ".join(value.strip().strip('"').lower().split())


def parse_cboe_date(value: str) -> date:
    normalized = value.strip().strip('"')
    for date_format in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, date_format).date()
        except ValueError:
            continue
    raise ValueError(f"unsupported Cboe date: {value}")


def parse_cboe_number(value: str) -> float:
    normalized = value.strip().strip('"').replace(",", "")
    if not normalized:
        raise ValueError("missing Cboe number")
    return float(normalized)


def find_cboe_json_value(text: str, key: str) -> str | None:
    match = re.search(rf'"{re.escape(key)}":"(?P<value>[^"]+)"', text)
    return match.group("value") if match else None


def parse_optional_cboe_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def write_breadth_bars_to_csv(
    path: Path,
    bars: list[MarketBreadthBar],
    retention_days: int = MARKET_BREADTH_RETENTION_DAYS,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=MARKET_BREADTH_CSV_FIELDS,
            lineterminator="\n",
        )
        writer.writeheader()
        for bar in trim_breadth_bars_to_retention(bars, retention_days):
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


def trim_breadth_bars_to_retention(
    bars: list[MarketBreadthBar],
    retention_days: int = MARKET_BREADTH_RETENTION_DAYS,
) -> list[MarketBreadthBar]:
    ordered = merge_breadth_bars(bars)
    if retention_days <= 0 or not ordered:
        return ordered
    latest_date = max(bar.date for bar in ordered)
    cutoff = latest_date - timedelta(days=retention_days)
    return [bar for bar in ordered if bar.date >= cutoff]


def put_call_cache_looks_official(
    bars: list[MarketBreadthBar],
    latest_trading_day: date | None,
) -> bool:
    if not latest_trading_day:
        return False
    post_2019_dates = {
        bar.date
        for bar in bars
        if bar.symbol == PUT_CALL_SYMBOL and bar.date >= CBOE_DAILY_HISTORY_START
    }
    if not post_2019_dates:
        return False
    first_date = min(post_2019_dates)
    if first_date > CBOE_DAILY_HISTORY_START + timedelta(days=7):
        return False
    last_date = min(max(post_2019_dates), latest_trading_day)
    expected_dates = business_dates(CBOE_DAILY_HISTORY_START, last_date)
    if not expected_dates:
        return False
    actual_dates = {trading_date for trading_date in post_2019_dates if trading_date <= last_date}
    return len(actual_dates) / len(expected_dates) >= 0.8


def put_call_backfill_dates(
    bars: list[MarketBreadthBar],
    latest_trading_day: date,
) -> list[date]:
    latest_cached_date = max((bar.date for bar in bars), default=None)
    if latest_cached_date:
        start_date = max(latest_cached_date + timedelta(days=1), CBOE_DAILY_HISTORY_START)
    else:
        start_date = CBOE_DAILY_HISTORY_START
    return business_dates(start_date, latest_trading_day)


def business_dates(start_date: date, end_date: date) -> list[date]:
    if start_date > end_date:
        return []
    days: list[date] = []
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() < 5:
            days.append(current_date)
        current_date += timedelta(days=1)
    return days


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
        "source": settings.get("source", "Barchart"),
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
