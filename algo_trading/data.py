from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol, Sequence

from algo_trading.models import Candle


class MarketDataClient(Protocol):
    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        raise NotImplementedError


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
        with urllib.request.urlopen(url, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, list):
            raise ValueError("unexpected Binance kline response")
        return [_candle_from_kline(row) for row in payload]


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
    if len(row) < 6:
        raise ValueError("kline row must contain at least 6 fields")
    return Candle(
        open_time=int(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
    )
