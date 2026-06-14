import json
import tempfile
import unittest
from pathlib import Path

from algo_trading.models import Candle
from algo_trading.ui import (
    load_run_details,
    list_runs,
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

    def get_24h_tickers(self) -> list[dict[str, object]]:
        return [
            {"symbol": "BTCUSDT", "quoteVolume": "500", "lastPrice": "65000"},
            {"symbol": "ETHUSDT", "quoteVolume": "250", "lastPrice": "1700"},
            {"symbol": "USDCUSDT", "quoteVolume": "999", "lastPrice": "1"},
        ]

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        self.kline_symbols.append(symbol)
        return [candle(index, price) for index, price in enumerate([10, 12, 13, 14])]


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


if __name__ == "__main__":
    unittest.main()
