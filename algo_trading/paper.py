from __future__ import annotations

import time
from pathlib import Path
from sys import stderr

from algo_trading.data import MarketDataClient, TransientMarketDataError
from algo_trading.models import Candle, StrategyConfig
from algo_trading.simulator import run_backtest
from algo_trading.storage import write_run_outputs
from algo_trading.strategy import apply_strategy_preset


def run_paper_session(
    client: MarketDataClient,
    config: StrategyConfig,
    output_root: str | Path = "runs",
    poll_seconds: float = 30.0,
    iterations: int = 3,
    limit: int = 300,
) -> Path:
    config = apply_strategy_preset(config)
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    if poll_seconds < 0:
        raise ValueError("poll_seconds cannot be negative")
    if limit <= 0:
        raise ValueError("limit must be positive")

    candles_by_time: dict[int, Candle] = {}
    for iteration in range(iterations):
        try:
            candles = client.get_klines(config.symbol, config.interval, limit)
        except TransientMarketDataError as exc:
            print(f"paper poll failed: {exc}", file=stderr)
            candles = []
        if not candles:
            print("paper poll returned no candles; preserving current state", file=stderr)
        for candle in candles:
            candles_by_time[candle.open_time] = candle
        if poll_seconds > 0 and iteration < iterations - 1:
            time.sleep(poll_seconds)

    if not candles_by_time:
        raise ValueError("market-data client returned no usable candles")
    collected_candles = [
        candles_by_time[open_time] for open_time in sorted(candles_by_time)
    ]
    result = run_backtest(collected_candles, config)
    return write_run_outputs("paper", config, result, output_root)
