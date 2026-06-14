import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from algo_trading.data import TransientMarketDataError
from algo_trading.models import Candle
from algo_trading.cli import main


def candle(time: int, close: float) -> Candle:
    return Candle(
        open_time=time,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1.0,
    )


class FakeBinanceClient:
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


class FlakyBinanceClient(FakeBinanceClient):
    def __init__(self) -> None:
        super().__init__()
        self.failed_once: set[str] = set()

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        self.kline_symbols.append(symbol)
        if symbol == "ETHUSDT" and symbol not in self.failed_once:
            self.failed_once.add(symbol)
            raise TransientMarketDataError("temporary market data outage")
        return [candle(index, price) for index, price in enumerate([10, 12, 13, 14])]


class CliTests(unittest.TestCase):
    def test_backtest_fixture_command_writes_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture = tmp_path / "candles.csv"
            fixture.write_text(
                "\n".join(
                    [
                        "open_time,open,high,low,close,volume",
                        "1,10,11,9,10,1",
                        "2,12,13,11,12,1",
                        "3,13,14,12,13,1",
                        "4,14,15,13,14,1",
                    ]
                )
            )

            exit_code = main(
                [
                    "backtest",
                    "--fixture",
                    str(fixture),
                    "--output-root",
                    str(tmp_path),
                    "--fast-ema",
                    "1",
                    "--slow-ema",
                    "2",
                    "--rsi-period",
                    "2",
                    "--fee-rate",
                    "0",
                    "--slippage-rate",
                    "0",
                ]
            )

            self.assertEqual(exit_code, 0)
            summaries = list(tmp_path.glob("backtests/*/summary.json"))
            self.assertEqual(len(summaries), 1)
            summary = json.loads(summaries[0].read_text())
            self.assertIn("final_balance", summary)

    def test_symbols_command_prints_ranked_symbols(self):
        fake_client = FakeBinanceClient()
        stdout = StringIO()

        with patch("algo_trading.cli.BinanceMarketDataClient", return_value=fake_client):
            with redirect_stdout(stdout):
                exit_code = main(["symbols", "--top", "2"])

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("BTCUSDT", output)
        self.assertIn("ETHUSDT", output)
        self.assertNotIn("USDCUSDT", output)

    def test_backtest_top_symbols_runs_each_ranked_symbol(self):
        fake_client = FakeBinanceClient()

        with tempfile.TemporaryDirectory() as tmp:
            with patch("algo_trading.cli.BinanceMarketDataClient", return_value=fake_client):
                exit_code = main(
                    [
                        "backtest",
                        "--symbols",
                        "top",
                        "--top",
                        "2",
                        "--output-root",
                        tmp,
                        "--fast-ema",
                        "1",
                        "--slow-ema",
                        "2",
                        "--rsi-period",
                        "2",
                        "--fee-rate",
                        "0",
                        "--slippage-rate",
                        "0",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(fake_client.kline_symbols, ["BTCUSDT", "ETHUSDT"])
            summaries = sorted(Path(tmp).glob("backtests/*/summary.json"))
            self.assertEqual(len(summaries), 2)
            symbols = [json.loads(path.read_text())["symbol"] for path in summaries]
            self.assertEqual(sorted(symbols), ["BTCUSDT", "ETHUSDT"])

    def test_backtest_retries_transient_market_data_failures(self):
        fake_client = FlakyBinanceClient()

        with tempfile.TemporaryDirectory() as tmp:
            with patch("algo_trading.cli.BinanceMarketDataClient", return_value=fake_client):
                exit_code = main(
                    [
                        "backtest",
                        "--symbols",
                        "BTCUSDT,ETHUSDT",
                        "--market-data-retries",
                        "1",
                        "--retry-delay",
                        "0",
                        "--output-root",
                        tmp,
                        "--fast-ema",
                        "1",
                        "--slow-ema",
                        "2",
                        "--rsi-period",
                        "2",
                        "--fee-rate",
                        "0",
                        "--slippage-rate",
                        "0",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(fake_client.kline_symbols, ["BTCUSDT", "ETHUSDT", "ETHUSDT"])
            summaries = sorted(Path(tmp).glob("backtests/*/summary.json"))
            self.assertEqual(len(summaries), 2)


if __name__ == "__main__":
    unittest.main()
