from __future__ import annotations

import time
from pathlib import Path

from algo_trading.data import MarketDataClient
from algo_trading.models import Candle, StrategyConfig
from algo_trading.simulator import run_backtest
from algo_trading.storage import write_run_outputs


def run_paper_session(
    client: MarketDataClient,
    config: StrategyConfig,
    output_root: str | Path = "runs",
    poll_seconds: float = 30.0,
    iterations: int = 3,
    limit: int = 300,
) -> Path:
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    if poll_seconds < 0:
        raise ValueError("poll_seconds cannot be negative")
    if limit <= 0:
        raise ValueError("limit must be positive")

    latest_candles: list[Candle] = []
    for iteration in range(iterations):
        candles = client.get_klines(config.symbol, config.interval, limit)
        if not candles:
            raise ValueError("market-data client returned no candles")
        latest_candles = candles
        if poll_seconds > 0 and iteration < iterations - 1:
            time.sleep(poll_seconds)

    result = run_backtest(latest_candles, config)
    return write_run_outputs("paper", config, result, output_root)
