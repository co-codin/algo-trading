from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from algo_trading.data import (
    BinanceMarketDataClient,
    MarketDataClient,
    TransientMarketDataError,
    load_candles_from_csv,
)
from algo_trading.models import (
    AllowedSide,
    Candle,
    StrategyConfig,
    StrategyName,
    StrategyPreset,
)
from algo_trading.simulator import run_backtest
from algo_trading.storage import write_run_outputs
from algo_trading.strategy import apply_strategy_preset, list_strategy_names
from algo_trading.symbols import parse_symbol_list, ranked_usdt_symbols


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "backtest":
            return _run_backtest_command(args)
        if args.command == "paper":
            return _run_paper_command(args)
        if args.command == "symbols":
            return _run_symbols_command(args)
        parser.print_help()
        return 2
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _run_backtest_command(args: argparse.Namespace) -> int:
    client = BinanceMarketDataClient()
    symbols = _resolve_backtest_symbols(args, client)
    fixture_candles = load_candles_from_csv(args.fixture) if args.fixture else None
    for symbol in symbols:
        config = apply_strategy_preset(_config_from_args(args, symbol=symbol))
        if fixture_candles is not None:
            candles = fixture_candles
        else:
            candles = _get_klines_with_retries(
                client,
                config.symbol,
                config.interval,
                args.limit,
                args.market_data_retries,
                args.retry_delay,
            )
        result = run_backtest(candles, config)
        run_dir = write_run_outputs("backtests", config, result, Path(args.output_root))
        print(f"wrote {config.symbol} backtest results to {run_dir}")
        print(f"{config.symbol} final_balance={result.summary['final_balance']}")
    return 0


def _run_symbols_command(args: argparse.Namespace) -> int:
    ranked = ranked_usdt_symbols(
        BinanceMarketDataClient().get_24h_tickers(),
        limit=args.top,
    )
    for index, item in enumerate(ranked, start=1):
        print(
            f"{index}\t{item.symbol}\tquoteVolume={item.quote_volume:.2f}\tlast={item.last_price:g}"
        )
    return 0


def _resolve_backtest_symbols(
    args: argparse.Namespace,
    client: MarketDataClient,
) -> list[str]:
    if not args.symbols:
        return [args.symbol.upper()]
    if args.symbols.strip().lower() == "top":
        return [
            item.symbol
            for item in ranked_usdt_symbols(client.get_24h_tickers(), args.top)
        ]
    return parse_symbol_list(args.symbols)


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
        except TransientMarketDataError as exc:
            if attempts >= retries:
                raise
            attempts += 1
            print(
                f"{symbol} market-data fetch failed: {exc}; retrying {attempts}/{retries}",
                file=sys.stderr,
            )
            if retry_delay > 0:
                time.sleep(retry_delay)


def _run_paper_command(args: argparse.Namespace) -> int:
    from algo_trading.paper import run_paper_session

    config = apply_strategy_preset(_config_from_args(args))
    run_dir = run_paper_session(
        BinanceMarketDataClient(),
        config,
        Path(args.output_root),
        poll_seconds=args.poll_seconds,
        iterations=args.iterations,
        limit=args.limit,
    )
    print(f"wrote paper results to {run_dir}")
    return 0


def _config_from_args(args: argparse.Namespace, symbol: str | None = None) -> StrategyConfig:
    return StrategyConfig(
        symbol=(symbol or args.symbol).upper(),
        interval=args.interval,
        starting_balance=args.starting_balance,
        fee_rate=args.fee_rate,
        slippage_rate=args.slippage_rate,
        position_fraction=args.position_fraction,
        allowed_side=AllowedSide(args.allowed_side),
        strategy=StrategyName(args.strategy),
        preset=StrategyPreset(args.preset),
        fast_ema=args.fast_ema,
        slow_ema=args.slow_ema,
        rsi_period=args.rsi_period,
        rsi_overbought=args.rsi_overbought,
        rsi_oversold=args.rsi_oversold,
        rsi_midline=args.rsi_midline,
        macd_signal=args.macd_signal,
        bollinger_period=args.bollinger_period,
        bollinger_stddev=args.bollinger_stddev,
        donchian_period=args.donchian_period,
        atr_period=args.atr_period,
        supertrend_multiplier=args.supertrend_multiplier,
        vwap_period=args.vwap_period,
        vwap_threshold_pct=args.vwap_threshold_pct,
        stoch_rsi_period=args.stoch_rsi_period,
        stoch_rsi_oversold=args.stoch_rsi_oversold,
        stoch_rsi_overbought=args.stoch_rsi_overbought,
        ema_ribbon_fast=args.ema_ribbon_fast,
        ema_ribbon_mid=args.ema_ribbon_mid,
        ema_ribbon_slow=args.ema_ribbon_slow,
        momentum_period=args.momentum_period,
        keltner_multiplier=args.keltner_multiplier,
        cci_period=args.cci_period,
        cci_oversold=args.cci_oversold,
        cci_overbought=args.cci_overbought,
        williams_period=args.williams_period,
        williams_oversold=args.williams_oversold,
        williams_overbought=args.williams_overbought,
        volume_period=args.volume_period,
        volume_multiplier=args.volume_multiplier,
        squeeze_threshold_pct=args.squeeze_threshold_pct,
        stop_loss_pct=args.stop_loss_pct,
        take_profit_pct=args.take_profit_pct,
        trailing_stop_pct=args.trailing_stop_pct,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="algo-trading",
        description="Read-only BTCUSDT backtesting and paper trading",
    )
    subparsers = parser.add_subparsers(dest="command")
    _add_backtest_parser(subparsers)
    _add_paper_parser(subparsers)
    _add_symbols_parser(subparsers)
    return parser


def _add_backtest_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("backtest", help="run a historical backtest")
    _add_common_options(parser)
    parser.add_argument(
        "--symbols",
        default="",
        help="comma-separated symbols, or 'top' to use ranked USDT pairs",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="number of top symbols when --symbols=top",
    )
    parser.add_argument(
        "--market-data-retries",
        type=int,
        default=2,
        help="transient market-data retries per symbol",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=0.5,
        help="seconds to wait between transient market-data retries",
    )
    parser.add_argument("--fixture", default="", help="CSV candle fixture path")


def _add_paper_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("paper", help="run a bounded paper-trading loop")
    _add_common_options(parser)
    parser.set_defaults(interval="1m")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--poll-seconds", type=float, default=30.0)


def _add_symbols_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("symbols", help="list top read-only Binance USDT symbols")
    parser.add_argument("--top", type=int, default=10, help="number of symbols to print")


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--output-root", default="runs")
    parser.add_argument("--starting-balance", type=float, default=10000.0)
    parser.add_argument("--fee-rate", type=float, default=0.001)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--position-fraction", type=float, default=1.0)
    parser.add_argument(
        "--allowed-side",
        choices=[side.value for side in AllowedSide],
        default=AllowedSide.BOTH.value,
    )
    parser.add_argument(
        "--strategy",
        choices=list_strategy_names(),
        default=StrategyName.EMA_RSI.value,
    )
    parser.add_argument(
        "--preset",
        choices=[preset.value for preset in StrategyPreset],
        default=StrategyPreset.CUSTOM.value,
    )
    parser.add_argument("--fast-ema", type=int, default=12)
    parser.add_argument("--slow-ema", type=int, default=26)
    parser.add_argument("--rsi-period", type=int, default=14)
    parser.add_argument("--rsi-overbought", type=float, default=70.0)
    parser.add_argument("--rsi-oversold", type=float, default=30.0)
    parser.add_argument("--rsi-midline", type=float, default=50.0)
    parser.add_argument("--macd-signal", type=int, default=9)
    parser.add_argument("--bollinger-period", type=int, default=20)
    parser.add_argument("--bollinger-stddev", type=float, default=2.0)
    parser.add_argument("--donchian-period", type=int, default=20)
    parser.add_argument("--atr-period", type=int, default=14)
    parser.add_argument("--supertrend-multiplier", type=float, default=3.0)
    parser.add_argument("--vwap-period", type=int, default=20)
    parser.add_argument("--vwap-threshold-pct", type=float, default=0.01)
    parser.add_argument("--stoch-rsi-period", type=int, default=14)
    parser.add_argument("--stoch-rsi-oversold", type=float, default=20.0)
    parser.add_argument("--stoch-rsi-overbought", type=float, default=80.0)
    parser.add_argument("--ema-ribbon-fast", type=int, default=8)
    parser.add_argument("--ema-ribbon-mid", type=int, default=21)
    parser.add_argument("--ema-ribbon-slow", type=int, default=55)
    parser.add_argument("--momentum-period", type=int, default=10)
    parser.add_argument("--keltner-multiplier", type=float, default=2.0)
    parser.add_argument("--cci-period", type=int, default=20)
    parser.add_argument("--cci-oversold", type=float, default=-100.0)
    parser.add_argument("--cci-overbought", type=float, default=100.0)
    parser.add_argument("--williams-period", type=int, default=14)
    parser.add_argument("--williams-oversold", type=float, default=-80.0)
    parser.add_argument("--williams-overbought", type=float, default=-20.0)
    parser.add_argument("--volume-period", type=int, default=20)
    parser.add_argument("--volume-multiplier", type=float, default=1.5)
    parser.add_argument("--squeeze-threshold-pct", type=float, default=0.05)
    parser.add_argument("--stop-loss-pct", type=float, default=0.03)
    parser.add_argument("--take-profit-pct", type=float, default=0.06)
    parser.add_argument("--trailing-stop-pct", type=float, default=0.0)


if __name__ == "__main__":
    raise SystemExit(main())
