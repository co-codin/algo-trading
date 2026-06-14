import json
import tempfile
import unittest
from pathlib import Path

from algo_trading.models import Candle
from algo_trading.ui import (
    load_run_details,
    list_runs,
    live_chart_payload,
    paper_trade_markers,
    run_backtest_payload,
    top_symbols_payload,
)


def candle(time: int, close: float) -> Candle:
    return Candle(
        open_time=time,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1.0,
    )


class FakeClient:
    def __init__(self) -> None:
        self.kline_symbols: list[str] = []
        self.candles: list[Candle] | None = None

    def get_24h_tickers(self) -> list[dict[str, object]]:
        return [
            {"symbol": "BTCUSDT", "quoteVolume": "500", "lastPrice": "65000"},
            {"symbol": "ETHUSDT", "quoteVolume": "250", "lastPrice": "1700"},
            {"symbol": "USDCUSDT", "quoteVolume": "999", "lastPrice": "1"},
        ]

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        self.kline_symbols.append(symbol)
        if self.candles is not None:
            return self.candles[:limit]
        return [candle(index, price) for index, price in enumerate([10, 12, 13, 14])]


def trending_candles() -> list[Candle]:
    prices = [10, 9, 8, 9, 11, 13, 12, 10, 8, 7, 9, 11]
    return [candle(index, price) for index, price in enumerate(prices)]


class UiTests(unittest.TestCase):
    def test_top_symbols_payload_filters_and_ranks(self):
        payload = top_symbols_payload(FakeClient(), top=2)

        self.assertEqual(
            [item["symbol"] for item in payload["symbols"]],
            ["BTCUSDT", "ETHUSDT"],
        )

    def test_run_backtest_payload_writes_one_run_per_symbol(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as tmp:
            payload = run_backtest_payload(
                {
                    "symbols": "BTCUSDT,ETHUSDT",
                    "interval": "1h",
                    "limit": 4,
                    "fast_ema": 1,
                    "slow_ema": 2,
                    "rsi_period": 2,
                    "fee_rate": 0,
                    "slippage_rate": 0,
                },
                client=client,
                output_root=Path(tmp),
            )

            self.assertEqual(client.kline_symbols, ["BTCUSDT", "ETHUSDT"])
            self.assertEqual(
                [run["symbol"] for run in payload["runs"]],
                ["BTCUSDT", "ETHUSDT"],
            )
            self.assertEqual(len(list(Path(tmp).glob("backtests/*/summary.json"))), 2)

    def test_list_runs_reads_recent_summaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "backtests" / "20260614T010203Z"
            run_dir.mkdir(parents=True)
            (run_dir / "summary.json").write_text(
                json.dumps({"symbol": "BTCUSDT", "final_balance": 10100}),
                encoding="utf-8",
            )

            runs = list_runs(Path(tmp))

            self.assertEqual(runs[0]["mode"], "backtest")
            self.assertEqual(runs[0]["symbol"], "BTCUSDT")

    def test_load_run_details_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                load_run_details("../outside", output_root=Path(tmp))

    def test_live_chart_payload_returns_candles_and_strategy_signals(self):
        client = FakeClient()
        client.candles = trending_candles()

        payload = live_chart_payload(
            {
                "symbol": "BTCUSDT",
                "interval": "1h",
                "limit": 12,
                "fast_ema": 1,
                "slow_ema": 3,
                "rsi_period": 2,
                "rsi_overbought": 100,
                "rsi_oversold": 0,
            },
            client=client,
        )

        self.assertEqual(payload["symbol"], "BTCUSDT")
        self.assertEqual(len(payload["candles"]), 12)
        signal_types = {marker["type"] for marker in payload["signals"]}
        self.assertIn("long_signal", signal_types)
        self.assertIn("short_signal", signal_types)

    def test_paper_trade_markers_reads_entry_and_exit_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "paper" / "run-a"
            run_dir.mkdir(parents=True)
            (run_dir / "trades.csv").write_text(
                "\n".join(
                    [
                        "side,entry_time,exit_time,entry_price,exit_price,quantity,realized_pnl,fees,slippage,entry_reason,exit_reason",
                        "long,2,5,10,13,1,3,0,0,ema_cross_above,take_profit",
                        "short,7,9,12,9,1,3,0,0,ema_cross_below,ema_cross_above",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            markers = paper_trade_markers("BTCUSDT", 0, 10, Path(tmp))

            self.assertEqual(
                [marker["type"] for marker in markers],
                [
                    "paper_entry_long",
                    "paper_exit_long",
                    "paper_entry_short",
                    "paper_exit_short",
                ],
            )


if __name__ == "__main__":
    unittest.main()
