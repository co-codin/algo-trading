from __future__ import annotations

import argparse
import sys
from pathlib import Path

from algo_trading.data import BinanceMarketDataClient, load_candles_from_csv
from algo_trading.models import AllowedSide, StrategyConfig
from algo_trading.simulator import run_backtest
from algo_trading.storage import write_run_outputs


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "backtest":
            return _run_backtest_command(args)
        if args.command == "paper":
            return _run_paper_command(args)
        parser.print_help()
        return 2
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _run_backtest_command(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    if args.fixture:
        candles = load_candles_from_csv(args.fixture)
    else:
        candles = BinanceMarketDataClient().get_klines(
            config.symbol,
            config.interval,
            args.limit,
        )
    result = run_backtest(candles, config)
    run_dir = write_run_outputs("backtests", config, result, Path(args.output_root))
    print(f"wrote backtest results to {run_dir}")
    print(f"final_balance={result.summary['final_balance']}")
    return 0


def _run_paper_command(args: argparse.Namespace) -> int:
    from algo_trading.paper import run_paper_session

    config = _config_from_args(args)
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


def _config_from_args(args: argparse.Namespace) -> StrategyConfig:
    return StrategyConfig(
        symbol=args.symbol.upper(),
        interval=args.interval,
        starting_balance=args.starting_balance,
        fee_rate=args.fee_rate,
        slippage_rate=args.slippage_rate,
        position_fraction=args.position_fraction,
        allowed_side=AllowedSide(args.allowed_side),
        fast_ema=args.fast_ema,
        slow_ema=args.slow_ema,
        rsi_period=args.rsi_period,
        rsi_overbought=args.rsi_overbought,
        rsi_oversold=args.rsi_oversold,
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
    return parser


def _add_backtest_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("backtest", help="run a historical backtest")
    _add_common_options(parser)
    parser.add_argument("--fixture", default="", help="CSV candle fixture path")


def _add_paper_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("paper", help="run a bounded paper-trading loop")
    _add_common_options(parser)
    parser.set_defaults(interval="1m")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--poll-seconds", type=float, default=30.0)


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
    parser.add_argument("--fast-ema", type=int, default=12)
    parser.add_argument("--slow-ema", type=int, default=26)
    parser.add_argument("--rsi-period", type=int, default=14)
    parser.add_argument("--rsi-overbought", type=float, default=70.0)
    parser.add_argument("--rsi-oversold", type=float, default=30.0)
    parser.add_argument("--stop-loss-pct", type=float, default=0.03)
    parser.add_argument("--take-profit-pct", type=float, default=0.06)
    parser.add_argument("--trailing-stop-pct", type=float, default=0.0)


if __name__ == "__main__":
    raise SystemExit(main())
