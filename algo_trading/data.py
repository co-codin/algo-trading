from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from collections.abc import Sequence as RuntimeSequence
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence
from urllib.error import HTTPError, URLError

from algo_trading.models import Candle


class MarketDataClient(Protocol):
    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        raise NotImplementedError

    def get_24h_tickers(self) -> list[dict[str, object]]:
        raise NotImplementedError


class HistoricalMarketDataClient(MarketDataClient, Protocol):
    def get_historical_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        limit: int,
    ) -> list[Candle]:
        raise NotImplementedError


class TransientMarketDataError(RuntimeError):
    """Raised when a read-only market-data request can be retried later."""


_BINANCE_MAX_KLINE_LIMIT = 1000


class BinanceMarketDataClient:
    def __init__(
        self,
        base_url: str = "https://api.binance.com",
        opener: Callable[..., Any] = urllib.request.urlopen,
        timeout: int = 15,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.opener = opener
        self.timeout = timeout

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        return self._request_klines(symbol, interval, limit)

    def get_historical_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        limit: int = _BINANCE_MAX_KLINE_LIMIT,
    ) -> list[Candle]:
        if end_time <= start_time:
            raise ValueError("end time must be after start time")
        interval_ms = _binance_interval_ms(interval)
        candles: list[Candle] = []
        seen_open_times: set[int] = set()
        cursor = start_time

        while cursor < end_time:
            page = self._request_klines(
                symbol,
                interval,
                limit,
                start_time=cursor,
                end_time=end_time,
            )
            if not page:
                break

            for candle in page:
                if (
                    start_time <= candle.open_time < end_time
                    and candle.open_time not in seen_open_times
                ):
                    candles.append(candle)
                    seen_open_times.add(candle.open_time)

            last_open_time = max(candle.open_time for candle in page)
            next_cursor = last_open_time + interval_ms
            if next_cursor <= cursor:
                raise ValueError("Binance returned a non-advancing kline page")
            cursor = next_cursor

            if len(page) < limit:
                break

        return candles

    def get_24h_tickers(self) -> list[dict[str, object]]:
        payload = self._request_json("/api/v3/ticker/24hr", {}, timeout=20)
        if not isinstance(payload, list):
            raise ValueError("unexpected Binance ticker response")
        if not all(isinstance(item, dict) for item in payload):
            raise ValueError("unexpected Binance ticker response")
        return payload

    def _request_klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[Candle]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if limit > _BINANCE_MAX_KLINE_LIMIT:
            raise ValueError(f"limit cannot exceed {_BINANCE_MAX_KLINE_LIMIT}")
        query: dict[str, str] = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": str(limit),
        }
        if start_time is not None:
            query["startTime"] = str(start_time)
        if end_time is not None:
            query["endTime"] = str(end_time)
        payload = self._request_json("/api/v3/klines", query)
        if not isinstance(payload, list):
            raise ValueError("unexpected Binance kline response")
        return [_candle_from_kline(row) for row in payload]

    def _request_json(
        self,
        path: str,
        query: dict[str, str],
        timeout: int | None = None,
    ) -> Any:
        encoded_query = urllib.parse.urlencode(query)
        url = f"{self.base_url}{path}"
        if encoded_query:
            url = f"{url}?{encoded_query}"
        try:
            with self.opener(url, timeout=timeout or self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                raise TransientMarketDataError(
                    f"transient Binance HTTP {exc.code}"
                ) from exc
            raise ValueError(f"Binance HTTP {exc.code}") from exc
        except (TimeoutError, URLError) as exc:
            raise TransientMarketDataError("transient Binance market-data failure") from exc
        return payload


class YahooFuturesMarketDataClient:
    def __init__(
        self,
        base_url: str = "https://query2.finance.yahoo.com",
        opener: Callable[..., Any] = urllib.request.urlopen,
        timeout: int = 20,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.opener = opener
        self.timeout = timeout

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        yahoo_symbol = _yahoo_futures_symbol(symbol)
        yahoo_interval, yahoo_range, aggregate_minutes = _yahoo_interval(interval)
        candles = self._request_chart(
            yahoo_symbol,
            {
                "interval": yahoo_interval,
                "range": yahoo_range,
                "events": "history",
            },
        )
        if aggregate_minutes is not None:
            candles = _aggregate_candles(candles, aggregate_minutes)
        return candles[-limit:]

    def get_historical_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        limit: int = 1000,
    ) -> list[Candle]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if end_time <= start_time:
            raise ValueError("end time must be after start time")
        yahoo_symbol = _yahoo_futures_symbol(symbol)
        yahoo_interval, _yahoo_range, aggregate_minutes = _yahoo_interval(interval)
        candles = self._request_chart(
            yahoo_symbol,
            {
                "interval": yahoo_interval,
                "period1": str(start_time // 1000),
                "period2": str(end_time // 1000),
                "events": "history",
            },
        )
        if aggregate_minutes is not None:
            candles = _aggregate_candles(candles, aggregate_minutes)
        return [
            candle
            for candle in candles
            if start_time <= candle.open_time < end_time
        ]

    def get_24h_tickers(self) -> list[dict[str, object]]:
        candles = self.get_klines("ES=F", "1d", 1)
        if not candles:
            return []
        latest = candles[-1]
        return [
            {
                "symbol": "ES=F",
                "quoteVolume": latest.volume,
                "lastPrice": latest.close,
            }
        ]

    def _request_chart(self, yahoo_symbol: str, query: dict[str, str]) -> list[Candle]:
        encoded_query = urllib.parse.urlencode(query)
        encoded_symbol = urllib.parse.quote(yahoo_symbol, safe="")
        url = f"{self.base_url}/v8/finance/chart/{encoded_symbol}?{encoded_query}"
        request = urllib.request.Request(url, headers=_YAHOO_HEADERS)
        try:
            with self.opener(request, timeout=self.timeout) as response:
                response_text = response.read().decode("utf-8")
        except HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                raise TransientMarketDataError(
                    f"transient Yahoo Finance HTTP {exc.code}"
                ) from exc
            raise ValueError(f"Yahoo Finance HTTP {exc.code}") from exc
        except (TimeoutError, URLError) as exc:
            raise TransientMarketDataError(
                "transient Yahoo Finance market-data failure"
            ) from exc
        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError as exc:
            if "Too Many Requests" in response_text:
                raise TransientMarketDataError(
                    "transient Yahoo Finance rate limit"
                ) from exc
            raise ValueError("unexpected Yahoo Finance chart response") from exc
        return _candles_from_yahoo_chart(payload)


def load_candles_from_csv(path: str | Path) -> list[Candle]:
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            Candle(
                open_time=int(row["open_time"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            for row in reader
        ]


def write_candles_to_csv(candles: Sequence[Candle], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["open_time", "open", "high", "low", "close", "volume"]
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for candle in candles:
            writer.writerow(
                {
                    "open_time": candle.open_time,
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
            )
    return output_path


def _candle_from_kline(row: Sequence[Any]) -> Candle:
    if not isinstance(row, RuntimeSequence) or isinstance(row, (str, bytes)):
        raise ValueError("invalid kline row")
    if len(row) < 6:
        raise ValueError("invalid kline row")
    try:
        return Candle(
            open_time=int(row[0]),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid kline row") from exc


def _binance_interval_ms(interval: str) -> int:
    value = interval.strip()
    if len(value) < 2:
        raise ValueError(f"unsupported Binance interval: {interval}")
    if value.endswith("M"):
        raise ValueError("monthly Binance intervals are not fixed-width")
    try:
        amount = int(value[:-1])
    except ValueError as exc:
        raise ValueError(f"unsupported Binance interval: {interval}") from exc
    if amount <= 0:
        raise ValueError(f"unsupported Binance interval: {interval}")
    unit = value[-1].lower()
    multipliers = {
        "m": 60 * 1000,
        "h": 60 * 60 * 1000,
        "d": 24 * 60 * 60 * 1000,
        "w": 7 * 24 * 60 * 60 * 1000,
    }
    try:
        return amount * multipliers[unit]
    except KeyError as exc:
        raise ValueError(f"unsupported Binance interval: {interval}") from exc


_YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def _yahoo_futures_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    aliases = {
        "ES": "ES=F",
        "/ES": "ES=F",
        "ES=F": "ES=F",
        "SP500": "ES=F",
        "SP500_FUTURE": "ES=F",
        "SP500-FUTURE": "ES=F",
        "NQ": "NQ=F",
        "/NQ": "NQ=F",
        "NQ=F": "NQ=F",
        "NASDAQ": "NQ=F",
        "NASDAQ100": "NQ=F",
        "NASDAQ_100": "NQ=F",
        "NASDAQ-100": "NQ=F",
        "NASDAQ_FUTURE": "NQ=F",
        "NASDAQ-FUTURE": "NQ=F",
    }
    try:
        return aliases[value]
    except KeyError as exc:
        raise ValueError(f"unsupported futures symbol: {symbol}") from exc


def _yahoo_interval(interval: str) -> tuple[str, str, int | None]:
    intervals = {
        "1m": ("1m", "1d", None),
        "3m": ("1m", "1d", 3),
        "5m": ("5m", "5d", None),
        "15m": ("15m", "5d", None),
        "30m": ("30m", "1mo", None),
        "1h": ("60m", "1mo", None),
        "4h": ("60m", "3mo", 240),
        "1d": ("1d", "1y", None),
    }
    try:
        return intervals[interval.strip().lower()]
    except KeyError as exc:
        raise ValueError(f"unsupported futures interval: {interval}") from exc


def _candles_from_yahoo_chart(payload: Any) -> list[Candle]:
    if not isinstance(payload, dict):
        raise ValueError("unexpected Yahoo Finance chart response")
    try:
        chart = payload["chart"]
        error = chart.get("error")
        if error:
            raise ValueError(f"Yahoo Finance chart error: {error}")
        result = chart["result"][0]
        timestamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
        opens = quote["open"]
        highs = quote["high"]
        lows = quote["low"]
        closes = quote["close"]
        volumes = quote.get("volume", [])
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("unexpected Yahoo Finance chart response") from exc

    candles: list[Candle] = []
    for index, timestamp in enumerate(timestamps):
        try:
            open_value = opens[index]
            high_value = highs[index]
            low_value = lows[index]
            close_value = closes[index]
        except IndexError as exc:
            raise ValueError("unexpected Yahoo Finance chart response") from exc
        if any(
            value is None for value in (timestamp, open_value, high_value, low_value, close_value)
        ):
            continue
        volume_value = volumes[index] if index < len(volumes) else 0
        open_float = float(open_value)
        high_float = float(high_value)
        low_float = float(low_value)
        close_float = float(close_value)
        if high_float < max(open_float, close_float) or low_float > min(
            open_float,
            close_float,
        ):
            continue
        candles.append(
            Candle(
                open_time=int(timestamp) * 1000,
                open=open_float,
                high=high_float,
                low=low_float,
                close=close_float,
                volume=0.0 if volume_value is None else float(volume_value),
            )
        )
    if not candles:
        raise ValueError("Yahoo Finance chart response returned no usable candles")
    return candles


def _aggregate_candles(candles: list[Candle], minutes: int) -> list[Candle]:
    bucket_ms = minutes * 60 * 1000
    buckets: dict[int, list[Candle]] = {}
    for candle in candles:
        bucket_open = (candle.open_time // bucket_ms) * bucket_ms
        buckets.setdefault(bucket_open, []).append(candle)
    aggregated: list[Candle] = []
    for bucket_open in sorted(buckets):
        bucket = sorted(buckets[bucket_open], key=lambda candle: candle.open_time)
        aggregated.append(
            Candle(
                open_time=bucket_open,
                open=bucket[0].open,
                high=max(candle.high for candle in bucket),
                low=min(candle.low for candle in bucket),
                close=bucket[-1].close,
                volume=sum(candle.volume for candle in bucket),
            )
        )
    return aggregated
