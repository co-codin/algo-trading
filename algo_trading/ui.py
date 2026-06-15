from __future__ import annotations

import argparse
import csv
import io
import json
import time
import urllib.parse
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from algo_trading.data import (
    BinanceMarketDataClient,
    MarketDataClient,
    TransientMarketDataError,
    YahooFuturesMarketDataClient,
)
from algo_trading.models import (
    AllowedSide,
    Candle,
    StrategyConfig,
    StrategyName,
    StrategyPreset,
)
from algo_trading.paper import run_paper_session
from algo_trading.simulator import run_backtest
from algo_trading.storage import write_run_outputs
from algo_trading.strategy import (
    apply_strategy_preset,
    build_strategy_context,
    entry_signal_for_index,
    get_strategy,
    list_strategy_names,
)
from algo_trading.symbols import parse_symbol_list, ranked_usdt_symbols

WEB_ROOT = Path(__file__).with_name("web")
WEB_DIST_ROOT = WEB_ROOT / "dist"
ALL_STRATEGIES_VALUE = "all"
CRYPTO_SPOT_MARKET = "crypto_spot"
CME_FUTURES_MARKET = "cme_futures"
FUTURES_BENCHMARK_ALIASES = frozenset(
    {
        "ES",
        "/ES",
        "ES=F",
        "SP500",
        "SP500_FUTURE",
        "SP500-FUTURE",
        "NQ",
        "/NQ",
        "NQ=F",
        "NASDAQ",
        "NASDAQ100",
        "NASDAQ_100",
        "NASDAQ-100",
        "NASDAQ_FUTURE",
        "NASDAQ-FUTURE",
    }
)
STRATEGY_LAB_CSV_FIELDS = [
    "rank",
    "symbol",
    "strategy",
    "preset",
    "final_balance",
    "total_return_pct",
    "max_drawdown_pct",
    "trades",
    "win_rate",
    "profit_factor",
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown_duration",
    "average_trade_duration",
    "exposure_pct",
    "worst_trade",
    "walk_forward_windows",
    "walk_forward_avg_return_pct",
    "walk_forward_worst_return_pct",
    "walk_forward_best_return_pct",
    "walk_forward_profitable_pct",
]
FRONTEND_ROUTES = frozenset(
    {
        "",
        "/",
        "/index.html",
        "/live",
        "/chart",
        "/breadth",
        "/lab",
        "/profile",
        "/admin",
    }
)


def is_frontend_route(path: str) -> bool:
    return path in FRONTEND_ROUTES


def is_vite_asset_route(path: str) -> bool:
    normalized = Path(urllib.parse.unquote(path)).as_posix()
    return normalized.startswith("/assets/") and "/../" not in normalized


def top_symbols_payload(client: MarketDataClient, top: int = 10) -> dict[str, Any]:
    ranked = ranked_usdt_symbols(client.get_24h_tickers(), limit=top)
    return {
        "ok": True,
        "symbols": [
            {
                "symbol": item.symbol,
                "base_asset": item.base_asset,
                "quote_volume": item.quote_volume,
                "last_price": item.last_price,
            }
            for item in ranked
        ],
    }


def run_backtest_payload(
    payload: dict[str, Any],
    client: MarketDataClient | None = None,
    output_root: str | Path = "runs",
) -> dict[str, Any]:
    market_client = client or BinanceMarketDataClient()
    output_path = Path(output_root)
    symbols = _resolve_symbols(
        str(payload.get("symbols") or payload.get("symbol") or "BTCUSDT"),
        _int_value(payload, "top", 10),
        market_client,
    )
    limit = _int_value(payload, "limit", 300)
    retries = _int_value(payload, "market_data_retries", 2)
    retry_delay = _float_value(payload, "retry_delay", 0.5)

    runs: list[dict[str, Any]] = []
    for symbol in symbols:
        config = apply_strategy_preset(
            _strategy_config_from_payload(payload, symbol=symbol, default_interval="1h")
        )
        candles = _get_klines_with_retries(
            market_client,
            config.symbol,
            config.interval,
            limit,
            retries,
            retry_delay,
        )
        result = run_backtest(candles, config)
        run_dir = write_run_outputs("backtests", config, result, output_path)
        runs.append(_run_payload("backtest", run_dir, output_path, result.summary))

    return {"ok": True, "mode": "backtest", "runs": runs}


def run_paper_payload(
    payload: dict[str, Any],
    client: MarketDataClient | None = None,
    output_root: str | Path = "runs",
) -> dict[str, Any]:
    market_client = client or BinanceMarketDataClient()
    output_path = Path(output_root)
    symbols = parse_symbol_list(str(payload.get("symbol") or "BTCUSDT"))
    if len(symbols) != 1:
        raise ValueError("paper mode accepts one symbol")

    config = apply_strategy_preset(
        _strategy_config_from_payload(
            payload,
            symbol=symbols[0],
            default_interval="1m",
        )
    )
    run_dir = run_paper_session(
        market_client,
        config,
        output_path,
        poll_seconds=_float_value(payload, "poll_seconds", 30.0),
        iterations=_int_value(payload, "iterations", 3),
        limit=_int_value(payload, "limit", 300),
    )
    summary = _read_json(run_dir / "summary.json")
    return {
        "ok": True,
        "mode": "paper",
        "runs": [_run_payload("paper", run_dir, output_path, summary)],
    }


def live_chart_payload(
    payload: dict[str, Any],
    client: MarketDataClient | None = None,
    output_root: str | Path = "runs",
) -> dict[str, Any]:
    market = _market_from_payload(payload)
    market_client = client or market_data_client_from_payload(payload)
    symbol = _live_symbol_from_payload(payload, market)
    limit = _int_value(payload, "limit", 180)
    retries = _int_value(payload, "market_data_retries", 2)
    retry_delay = _float_value(payload, "retry_delay", 0.5)
    strategy_value = str(
        payload.get("strategy") or StrategyName.EMA_RSI.value
    ).strip().lower()
    configs = _live_strategy_configs_from_payload(
        payload,
        symbol=symbol,
        default_interval="1m",
    )
    config = configs[0]
    candles = _get_klines_with_retries(
        market_client,
        config.symbol,
        config.interval,
        limit,
        retries,
        retry_delay,
    )
    if not candles:
        raise ValueError("market-data client returned no candles")
    start_time = candles[0].open_time
    end_time = candles[-1].open_time
    signals = (
        _all_strategy_signal_markers(candles, configs)
        if strategy_value == ALL_STRATEGIES_VALUE
        else _strategy_signal_markers(candles, config)
    )
    return {
        "ok": True,
        "market": market,
        "data_source": _data_source_label(market),
        "symbol": config.symbol,
        "interval": config.interval,
        "strategy": strategy_value,
        "candles": [_candle_payload(candle) for candle in candles],
        "signals": signals,
        "paper_markers": paper_trade_markers(
            config.symbol,
            start_time,
            end_time,
            output_root,
        ),
    }


def combination_signals_payload(
    payload: dict[str, Any],
    client: MarketDataClient | None = None,
) -> dict[str, Any]:
    market = _market_from_payload(payload)
    market_client = client or market_data_client_from_payload(payload)
    symbol = _live_symbol_from_payload(payload, market)
    limit = _int_value(payload, "limit", 180)
    retries = _int_value(payload, "market_data_retries", 2)
    retry_delay = _float_value(payload, "retry_delay", 0.5)
    config = apply_strategy_preset(
        _strategy_config_from_payload(
            {**payload, "strategy": StrategyName.COMBINED_SIGNALS.value},
            symbol=symbol,
            default_interval="1h",
        )
    )
    candles = _get_klines_with_retries(
        market_client,
        config.symbol,
        config.interval,
        limit,
        retries,
        retry_delay,
    )
    result = run_backtest(candles, config)
    return {
        "ok": True,
        "mode": "combination-signals",
        "market": market,
        "data_source": _data_source_label(market),
        "symbol": config.symbol,
        "interval": config.interval,
        "config": _jsonable(asdict(config)),
        "summary": result.summary,
        "candles": [_candle_payload(candle) for candle in candles],
        "signals": _strategy_signal_markers(candles, config),
    }


def market_data_client_from_payload(payload: dict[str, Any]) -> MarketDataClient:
    market = _market_from_payload(payload)
    if market == CME_FUTURES_MARKET:
        return YahooFuturesMarketDataClient()
    if market == CRYPTO_SPOT_MARKET:
        return BinanceMarketDataClient()
    raise ValueError(f"unsupported market: {market}")


def strategies_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "strategies": [
            {
                "name": name,
                "description": get_strategy(name).description,
            }
            for name in list_strategy_names()
        ],
        "presets": [preset.value for preset in StrategyPreset],
    }


def strategy_lab_payload(
    payload: dict[str, Any],
    client: MarketDataClient | None = None,
    benchmark_client: MarketDataClient | None = None,
) -> dict[str, Any]:
    market_client = client or BinanceMarketDataClient()
    symbols = _resolve_symbols(
        str(payload.get("symbols") or payload.get("symbol") or "BTCUSDT"),
        _int_value(payload, "top", 5),
        market_client,
    )
    strategies = _strategy_names_from_payload(payload)
    presets = _preset_names_from_payload(payload)
    limit = _int_value(payload, "limit", 300)
    retries = _int_value(payload, "market_data_retries", 2)
    retry_delay = _float_value(payload, "retry_delay", 0.5)
    walk_forward_windows = _int_value(payload, "walk_forward_windows", 0)
    walk_forward_min_candles = _int_value(payload, "walk_forward_min_candles", 30)
    rows: list[dict[str, Any]] = []
    candles_by_symbol: dict[str, list[Candle]] = {}

    for symbol in symbols:
        interval = str(payload.get("interval") or "1h")
        candles = _get_klines_with_retries(
            market_client,
            symbol,
            interval,
            limit,
            retries,
            retry_delay,
        )
        candles_by_symbol[symbol] = candles
        for strategy in strategies:
            for preset in presets:
                config_payload = {
                    **payload,
                    "strategy": strategy.value,
                    "preset": preset.value,
                }
                config = apply_strategy_preset(
                    _strategy_config_from_payload(
                        config_payload,
                        symbol=symbol,
                        default_interval=interval,
                    )
                )
                result = run_backtest(candles, config)
                summary = result.summary
                row = _strategy_lab_row(
                    symbol=symbol,
                    strategy=strategy.value,
                    preset=preset.value,
                    summary=summary,
                )
                if walk_forward_windows > 0:
                    _enrich_row_with_walk_forward(
                        row,
                        candles,
                        config,
                        walk_forward_windows,
                        walk_forward_min_candles,
                    )
                rows.append(row)

        rows.append(
            _benchmark_row(
                symbol,
                candles,
                starting_balance=_float_value(payload, "starting_balance", 10000.0),
            )
        )

    for symbol in _benchmark_symbols_from_payload(payload):
        if symbol in candles_by_symbol:
            continue
        interval = str(payload.get("interval") or "1h")
        if _is_futures_benchmark_symbol(symbol):
            source_client = benchmark_client or YahooFuturesMarketDataClient()
        else:
            source_client = market_client
        candles = _get_klines_with_retries(
            source_client,
            symbol,
            interval,
            limit,
            retries,
            retry_delay,
        )
        rows.append(
            _benchmark_row(
                symbol,
                candles,
                starting_balance=_float_value(payload, "starting_balance", 10000.0),
            )
        )

    rows.sort(
        key=lambda row: (
            float(row["total_return_pct"]),
            -float(row["max_drawdown_pct"]),
            int(row["trades"]),
        ),
        reverse=True,
    )
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return {"ok": True, "mode": "strategy-lab", "rows": rows}


def strategy_lab_csv(rows: list[dict[str, Any]]) -> str:
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=STRATEGY_LAB_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in STRATEGY_LAB_CSV_FIELDS})
    return handle.getvalue()


def _strategy_lab_row(
    symbol: str,
    strategy: str,
    preset: str,
    summary: dict[str, float | int | str],
) -> dict[str, Any]:
    return {
        "rank": 0,
        "symbol": symbol,
        "strategy": strategy,
        "preset": preset,
        "final_balance": summary["final_balance"],
        "total_return_pct": summary["total_return_pct"],
        "max_drawdown_pct": summary["max_drawdown_pct"],
        "trades": summary["trades"],
        "win_rate": summary["win_rate"],
        "profit_factor": summary["profit_factor"],
        "sharpe_ratio": summary.get("sharpe_ratio", 0.0),
        "sortino_ratio": summary.get("sortino_ratio", 0.0),
        "max_drawdown_duration": summary.get("max_drawdown_duration", 0),
        "average_trade_duration": summary.get("average_trade_duration", 0.0),
        "exposure_pct": summary.get("exposure_pct", 0.0),
        "worst_trade": summary.get("worst_trade", 0.0),
        "walk_forward_windows": 0,
        "walk_forward_avg_return_pct": 0.0,
        "walk_forward_worst_return_pct": 0.0,
        "walk_forward_best_return_pct": 0.0,
        "walk_forward_profitable_pct": 0.0,
    }


def _benchmark_row(
    symbol: str,
    candles: list[Candle],
    starting_balance: float,
) -> dict[str, Any]:
    if not candles:
        raise ValueError("benchmark requires at least one candle")
    first_close = candles[0].close
    last_close = candles[-1].close
    final_balance = starting_balance * (last_close / first_close)
    summary: dict[str, float | int | str] = {
        "final_balance": round(final_balance, 8),
        "total_return_pct": round(((final_balance / starting_balance) - 1.0) * 100.0, 8),
        "max_drawdown_pct": round(_benchmark_max_drawdown(candles), 8),
        "trades": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "max_drawdown_duration": _benchmark_drawdown_duration(candles),
        "average_trade_duration": 0.0,
        "exposure_pct": 100.0,
        "worst_trade": 0.0,
    }
    return _strategy_lab_row(symbol, "buy-and-hold", "benchmark", summary)


def _benchmark_max_drawdown(candles: list[Candle]) -> float:
    peak = 0.0
    max_drawdown = 0.0
    for candle in candles:
        peak = max(peak, candle.close)
        if peak > 0.0:
            max_drawdown = max(max_drawdown, ((peak - candle.close) / peak) * 100.0)
    return max_drawdown


def _benchmark_drawdown_duration(candles: list[Candle]) -> int:
    peak = 0.0
    current_duration = 0
    longest_duration = 0
    for candle in candles:
        if candle.close >= peak:
            peak = candle.close
            current_duration = 0
        else:
            current_duration += 1
            longest_duration = max(longest_duration, current_duration)
    return longest_duration


def _benchmark_symbols_from_payload(payload: dict[str, Any]) -> list[str]:
    value = str(payload.get("benchmark_symbols") or "").strip()
    if not value:
        return []
    return [symbol.upper() for symbol in parse_symbol_list(value)]


def _is_futures_benchmark_symbol(symbol: str) -> bool:
    return symbol.upper() in FUTURES_BENCHMARK_ALIASES or symbol.upper().endswith("=F")


def _enrich_row_with_walk_forward(
    row: dict[str, Any],
    candles: list[Candle],
    config: StrategyConfig,
    window_count: int,
    min_candles: int,
) -> None:
    summaries = _walk_forward_summaries(candles, config, window_count, min_candles)
    returns = [float(summary["total_return_pct"]) for summary in summaries]
    if not returns:
        return
    row["walk_forward_windows"] = len(returns)
    row["walk_forward_avg_return_pct"] = round(sum(returns) / len(returns), 8)
    row["walk_forward_worst_return_pct"] = round(min(returns), 8)
    row["walk_forward_best_return_pct"] = round(max(returns), 8)
    profitable = sum(1 for value in returns if value > 0.0)
    row["walk_forward_profitable_pct"] = round((profitable / len(returns)) * 100.0, 8)


def _walk_forward_summaries(
    candles: list[Candle],
    config: StrategyConfig,
    window_count: int,
    min_candles: int,
) -> list[dict[str, float | int | str]]:
    summaries: list[dict[str, float | int | str]] = []
    for window in _windowed_candles(candles, window_count, min_candles):
        try:
            summaries.append(run_backtest(window, config).summary)
        except ValueError:
            continue
    return summaries


def _windowed_candles(
    candles: list[Candle],
    window_count: int,
    min_candles: int,
) -> list[list[Candle]]:
    if window_count <= 0 or min_candles <= 0:
        return []
    window_size = max(min_candles, len(candles) // window_count)
    windows: list[list[Candle]] = []
    for index in range(window_count):
        start = index * window_size
        end = len(candles) if index == window_count - 1 else start + window_size
        window = candles[start:end]
        if len(window) >= min_candles:
            windows.append(window)
    return windows


def paper_trade_markers(
    symbol: str,
    start_time: int,
    end_time: int,
    output_root: str | Path = "runs",
) -> list[dict[str, Any]]:
    root = Path(output_root)
    paper_root = root / "paper"
    if not paper_root.exists():
        return []

    markers: list[dict[str, Any]] = []
    for run_dir in paper_root.iterdir():
        if not run_dir.is_dir():
            continue
        config_path = run_dir / "config.json"
        if config_path.exists():
            try:
                config = _read_json(config_path)
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            if str(config.get("symbol", "")).upper() != symbol.upper():
                continue

        for row in _read_csv_rows(run_dir / "trades.csv", 10_000):
            try:
                side = str(row["side"]).lower()
                entry_time = int(row["entry_time"])
                exit_time = int(row["exit_time"])
                entry_price = float(row["entry_price"])
                exit_price = float(row["exit_price"])
                entry_reason = str(row.get("entry_reason", ""))
                exit_reason = str(row.get("exit_reason", ""))
            except (KeyError, TypeError, ValueError):
                continue
            if side not in {"long", "short"}:
                continue
            if start_time <= entry_time <= end_time:
                markers.append(
                    {
                        "time": entry_time,
                        "price": entry_price,
                        "type": f"paper_entry_{side}",
                        "reason": entry_reason,
                    }
                )
            if start_time <= exit_time <= end_time:
                markers.append(
                    {
                        "time": exit_time,
                        "price": exit_price,
                        "type": f"paper_exit_{side}",
                        "reason": exit_reason,
                    }
                )
    return sorted(markers, key=lambda item: (int(item["time"]), str(item["type"])))


def list_runs(output_root: str | Path = "runs", limit: int = 20) -> list[dict[str, Any]]:
    root = Path(output_root)
    runs: list[dict[str, Any]] = []
    for directory_name, mode in (("backtests", "backtest"), ("paper", "paper")):
        base = root / directory_name
        if not base.exists():
            continue
        for run_dir in base.iterdir():
            summary_path = run_dir / "summary.json"
            if not run_dir.is_dir() or not summary_path.exists():
                continue
            try:
                summary = _read_json(summary_path)
            except (OSError, json.JSONDecodeError):
                continue
            runs.append(_run_payload(mode, run_dir, root, summary))
    return sorted(runs, key=lambda item: str(item["timestamp"]), reverse=True)[:limit]


def load_run_details(
    run_path: str,
    output_root: str | Path = "runs",
    trade_limit: int = 50,
    equity_limit: int = 200,
) -> dict[str, Any]:
    root = Path(output_root).resolve()
    relative = Path(run_path)
    if relative.is_absolute():
        raise ValueError("run path must be relative")
    run_dir = (root / relative).resolve()
    try:
        run_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("run path escapes output root") from exc
    if not run_dir.is_dir():
        raise ValueError("run not found")

    return {
        "ok": True,
        "path": relative.as_posix(),
        "summary": _read_json(run_dir / "summary.json"),
        "config": _read_json(run_dir / "config.json"),
        "trades": _read_csv_rows(run_dir / "trades.csv", trade_limit),
        "equity": _read_csv_rows(run_dir / "equity.csv", equity_limit),
    }


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    output_root: str | Path = "runs",
) -> None:
    display_host = "127.0.0.1" if host in ("", "0.0.0.0") else host
    print(f"Serving algo-trading UI at http://{display_host}:{port}")
    import uvicorn

    from algo_trading.web_app import create_app

    uvicorn.run(
        create_app(output_root=output_root),
        host=host,
        port=port,
        log_level="info",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="algo-trading-ui")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--output-root", default="runs")
    args = parser.parse_args(argv)
    serve(host=args.host, port=args.port, output_root=args.output_root)
    return 0


def _resolve_symbols(
    value: str,
    top: int,
    client: MarketDataClient,
) -> list[str]:
    text = value.strip()
    lower = text.lower()
    if lower == "top" or lower.startswith("top "):
        parts = lower.split()
        limit = int(parts[1]) if len(parts) > 1 else top
        return [item.symbol for item in ranked_usdt_symbols(client.get_24h_tickers(), limit)]
    return parse_symbol_list(text)


def _market_from_payload(payload: dict[str, Any]) -> str:
    market = str(payload.get("market") or CRYPTO_SPOT_MARKET).strip().lower()
    aliases = {
        "spot": CRYPTO_SPOT_MARKET,
        "crypto": CRYPTO_SPOT_MARKET,
        "crypto_spot": CRYPTO_SPOT_MARKET,
        "binance": CRYPTO_SPOT_MARKET,
        "futures": CME_FUTURES_MARKET,
        "cme": CME_FUTURES_MARKET,
        "cme_futures": CME_FUTURES_MARKET,
        "us_index_futures": CME_FUTURES_MARKET,
    }
    try:
        return aliases[market]
    except KeyError as exc:
        raise ValueError(f"unsupported market: {market}") from exc


def _live_symbol_from_payload(payload: dict[str, Any], market: str) -> str:
    default_symbol = "ES=F" if market == CME_FUTURES_MARKET else "BTCUSDT"
    return str(payload.get("symbol") or default_symbol).upper()


def _data_source_label(market: str) -> str:
    if market == CME_FUTURES_MARKET:
        return "Yahoo Finance delayed CME futures"
    return "Binance Spot public REST"


def _live_client_for_handler(
    payload: dict[str, Any],
    client_factory: Callable[[], MarketDataClient],
) -> MarketDataClient:
    if client_factory is BinanceMarketDataClient:
        return market_data_client_from_payload(payload)
    return client_factory()


def _query_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    return {key: values[-1] for key, values in query.items() if values}


def _strategy_config_from_payload(
    payload: dict[str, Any],
    symbol: str,
    default_interval: str,
) -> StrategyConfig:
    return StrategyConfig(
        symbol=symbol.upper(),
        interval=str(payload.get("interval") or default_interval),
        starting_balance=_float_value(payload, "starting_balance", 10000.0),
        fee_rate=_float_value(payload, "fee_rate", 0.001),
        slippage_rate=_float_value(payload, "slippage_rate", 0.0005),
        position_fraction=_float_value(payload, "position_fraction", 1.0),
        allowed_side=AllowedSide(str(payload.get("allowed_side") or "both")),
        strategy=StrategyName(str(payload.get("strategy") or StrategyName.EMA_RSI.value)),
        preset=StrategyPreset(str(payload.get("preset") or StrategyPreset.CUSTOM.value)),
        fast_ema=_int_value(payload, "fast_ema", 12),
        slow_ema=_int_value(payload, "slow_ema", 26),
        rsi_period=_int_value(payload, "rsi_period", 14),
        rsi_overbought=_float_value(payload, "rsi_overbought", 70.0),
        rsi_oversold=_float_value(payload, "rsi_oversold", 30.0),
        rsi_midline=_float_value(payload, "rsi_midline", 50.0),
        macd_signal=_int_value(payload, "macd_signal", 9),
        bollinger_period=_int_value(payload, "bollinger_period", 20),
        bollinger_stddev=_float_value(payload, "bollinger_stddev", 2.0),
        donchian_period=_int_value(payload, "donchian_period", 20),
        atr_period=_int_value(payload, "atr_period", 14),
        supertrend_multiplier=_float_value(payload, "supertrend_multiplier", 3.0),
        vwap_period=_int_value(payload, "vwap_period", 20),
        vwap_threshold_pct=_float_value(payload, "vwap_threshold_pct", 0.01),
        stoch_rsi_period=_int_value(payload, "stoch_rsi_period", 14),
        stoch_rsi_oversold=_float_value(payload, "stoch_rsi_oversold", 20.0),
        stoch_rsi_overbought=_float_value(payload, "stoch_rsi_overbought", 80.0),
        ema_ribbon_fast=_int_value(payload, "ema_ribbon_fast", 8),
        ema_ribbon_mid=_int_value(payload, "ema_ribbon_mid", 21),
        ema_ribbon_slow=_int_value(payload, "ema_ribbon_slow", 55),
        momentum_period=_int_value(payload, "momentum_period", 10),
        keltner_multiplier=_float_value(payload, "keltner_multiplier", 2.0),
        cci_period=_int_value(payload, "cci_period", 20),
        cci_oversold=_float_value(payload, "cci_oversold", -100.0),
        cci_overbought=_float_value(payload, "cci_overbought", 100.0),
        williams_period=_int_value(payload, "williams_period", 14),
        williams_oversold=_float_value(payload, "williams_oversold", -80.0),
        williams_overbought=_float_value(payload, "williams_overbought", -20.0),
        volume_period=_int_value(payload, "volume_period", 20),
        volume_multiplier=_float_value(payload, "volume_multiplier", 1.5),
        squeeze_threshold_pct=_float_value(payload, "squeeze_threshold_pct", 0.05),
        combo_strategies=str(payload.get("combo_strategies") or "all"),
        combo_entry_confirmations=_int_value(payload, "combo_entry_confirmations", 2),
        combo_exit_confirmations=_int_value(payload, "combo_exit_confirmations", 2),
        combo_lookback=_int_value(payload, "combo_lookback", 3),
        stop_loss_pct=_float_value(payload, "stop_loss_pct", 0.03),
        take_profit_pct=_float_value(payload, "take_profit_pct", 0.06),
        trailing_stop_pct=_float_value(payload, "trailing_stop_pct", 0.0),
    )


def _live_strategy_configs_from_payload(
    payload: dict[str, Any],
    symbol: str,
    default_interval: str,
) -> list[StrategyConfig]:
    strategy_value = str(
        payload.get("strategy") or StrategyName.EMA_RSI.value
    ).strip().lower()
    strategies = (
        [StrategyName(name) for name in list_strategy_names()]
        if strategy_value == ALL_STRATEGIES_VALUE
        else [StrategyName(strategy_value)]
    )
    return [
        apply_strategy_preset(
            _strategy_config_from_payload(
                {**payload, "strategy": strategy.value},
                symbol=symbol,
                default_interval=default_interval,
            )
        )
        for strategy in strategies
    ]


def _get_klines_with_retries(
    client: MarketDataClient,
    symbol: str,
    interval: str,
    limit: int,
    retries: int,
    retry_delay: float,
) -> list[Candle]:
    if retries < 0:
        raise ValueError("market-data retries cannot be negative")
    if retry_delay < 0:
        raise ValueError("retry delay cannot be negative")

    attempts = 0
    while True:
        try:
            return client.get_klines(symbol, interval, limit)
        except TransientMarketDataError:
            if attempts >= retries:
                raise
            attempts += 1
            if retry_delay > 0:
                time.sleep(retry_delay)


def _strategy_names_from_payload(payload: dict[str, Any]) -> list[StrategyName]:
    value = str(payload.get("strategies") or payload.get("strategy") or "").strip()
    if not value or value.lower() == "all":
        return [StrategyName(name) for name in list_strategy_names()]
    return [StrategyName(item.strip()) for item in value.split(",") if item.strip()]


def _preset_names_from_payload(payload: dict[str, Any]) -> list[StrategyPreset]:
    value = str(payload.get("presets") or payload.get("preset") or "custom").strip()
    if value.lower() == "all":
        return list(StrategyPreset)
    return [StrategyPreset(item.strip()) for item in value.split(",") if item.strip()]


def _strategy_signal_markers(
    candles: list[Candle],
    config: StrategyConfig,
    include_strategy_name: bool = False,
) -> list[dict[str, Any]]:
    context = build_strategy_context(candles, config)
    markers: list[dict[str, Any]] = []
    for index, candle in enumerate(candles):
        signal = entry_signal_for_index(config, context, index)
        reason = (
            f"{config.strategy.value}: {signal.reason}"
            if include_strategy_name
            else signal.reason
        )
        if signal.type.value == "enter_long":
            markers.append(
                {
                    "time": candle.open_time,
                    "price": candle.close,
                    "type": "long_signal",
                    "reason": reason,
                }
            )
        elif signal.type.value == "enter_short":
            markers.append(
                {
                    "time": candle.open_time,
                    "price": candle.close,
                    "type": "short_signal",
                    "reason": reason,
                }
            )
    return markers


def _all_strategy_signal_markers(
    candles: list[Candle],
    configs: list[StrategyConfig],
) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for config in configs:
        markers.extend(
            _strategy_signal_markers(candles, config, include_strategy_name=True)
        )
    return sorted(
        markers,
        key=lambda item: (int(item["time"]), str(item["reason"]), str(item["type"])),
    )


def _candle_payload(candle: Candle) -> dict[str, float | int]:
    return {
        "time": candle.open_time,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _jsonable(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_jsonable(inner) for inner in value]
    return value


def _run_payload(
    mode: str,
    run_dir: Path,
    output_root: Path,
    summary: dict[str, Any],
) -> dict[str, Any]:
    relative = run_dir.relative_to(output_root).as_posix()
    return {
        "mode": mode,
        "path": relative,
        "timestamp": run_dir.name,
        "symbol": summary.get("symbol", ""),
        "final_balance": summary.get("final_balance"),
        "summary": summary,
    }


def _int_value(payload: dict[str, Any], key: str, default: int) -> int:
    value = payload.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _float_value(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a number") from exc


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _read_csv_rows(path: Path, limit: int) -> list[dict[str, str]]:
    if limit <= 0 or not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return rows[:limit]


if __name__ == "__main__":
    raise SystemExit(main())
