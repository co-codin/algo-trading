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


class TransientMarketDataError(RuntimeError):
    """Raised when a read-only market-data request can be retried later."""


class BinanceMarketDataClient:
    def __init__(self, base_url: str = "https://api.binance.com") -> None:
        self.base_url = base_url.rstrip("/")

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        query = urllib.parse.urlencode(
            {
                "symbol": symbol.upper(),
                "interval": interval,
                "limit": str(limit),
            }
        )
        url = f"{self.base_url}/api/v3/klines?{query}"
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                raise TransientMarketDataError(
                    f"transient Binance HTTP {exc.code}"
                ) from exc
            raise ValueError(f"Binance HTTP {exc.code}") from exc
        except (TimeoutError, URLError) as exc:
            raise TransientMarketDataError("transient Binance market-data failure") from exc
        if not isinstance(payload, list):
            raise ValueError("unexpected Binance kline response")
        return [_candle_from_kline(row) for row in payload]

    def get_24h_tickers(self) -> list[dict[str, object]]:
        url = f"{self.base_url}/api/v3/ticker/24hr"
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                raise TransientMarketDataError(
                    f"transient Binance HTTP {exc.code}"
                ) from exc
            raise ValueError(f"Binance HTTP {exc.code}") from exc
        except (TimeoutError, URLError) as exc:
            raise TransientMarketDataError("transient Binance market-data failure") from exc
        if not isinstance(payload, list):
            raise ValueError("unexpected Binance ticker response")
        if not all(isinstance(item, dict) for item in payload):
            raise ValueError("unexpected Binance ticker response")
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
        query = urllib.parse.urlencode(
            {
                "interval": yahoo_interval,
                "range": yahoo_range,
                "events": "history",
            }
        )
        encoded_symbol = urllib.parse.quote(yahoo_symbol, safe="")
        url = f"{self.base_url}/v8/finance/chart/{encoded_symbol}?{query}"
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
        candles = _candles_from_yahoo_chart(payload)
        if aggregate_minutes is not None:
            candles = _aggregate_candles(candles, aggregate_minutes)
        return candles[-limit:]

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
        candles.append(
            Candle(
                open_time=int(timestamp) * 1000,
                open=float(open_value),
                high=float(high_value),
                low=float(low_value),
                close=float(close_value),
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
