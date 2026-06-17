import csv
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
        self.historical_requests: list[tuple[str, str, int, int, int]] = []

    def get_24h_tickers(self) -> list[dict[str, object]]:
        return [
            {"symbol": "BTCUSDT", "quoteVolume": "500", "lastPrice": "65000"},
            {"symbol": "ETHUSDT", "quoteVolume": "250", "lastPrice": "1700"},
            {"symbol": "USDCUSDT", "quoteVolume": "999", "lastPrice": "1"},
        ]

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        self.kline_symbols.append(symbol)
        return [candle(index, price) for index, price in enumerate([10, 12, 13, 14])]

    def get_historical_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        limit: int,
    ) -> list[Candle]:
        self.historical_requests.append((symbol, interval, start_time, end_time, limit))
        return [candle(start_time, 10), candle(end_time - 1, 12)]


class FakeYahooClient:
    def __init__(self) -> None:
        self.historical_requests: list[tuple[str, str, int, int, int]] = []

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        return [candle(index, price) for index, price in enumerate([100, 101])]

    def get_historical_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        limit: int,
    ) -> list[Candle]:
        self.historical_requests.append((symbol, interval, start_time, end_time, limit))
        return [candle(start_time, 100), candle(end_time - 1, 101)]


class FakeMoexClient:
    def __init__(self) -> None:
        self.historical_requests: list[tuple[str, str, int, int, int]] = []

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        return [candle(index, price) for index, price in enumerate([300, 301])]

    def get_historical_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        limit: int,
    ) -> list[Candle]:
        self.historical_requests.append((symbol, interval, start_time, end_time, limit))
        return [candle(start_time, 300), candle(end_time - 1, 301)]


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

    def test_candles_command_writes_historical_candles_to_csv(self):
        fake_client = FakeBinanceClient()
        stdout = StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "BTCUSDT-1h.csv"
            with patch("algo_trading.cli.BinanceMarketDataClient", return_value=fake_client):
                with redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "candles",
                            "--symbol",
                            "BTCUSDT",
                            "--interval",
                            "1h",
                            "--limit",
                            "4",
                            "--output",
                            str(output),
                        ]
                    )

            self.assertEqual(exit_code, 0)
            self.assertEqual(fake_client.kline_symbols, ["BTCUSDT"])
            with output.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(
                rows[0],
                {
                    "open_time": "0",
                    "open": "10",
                    "high": "11.0",
                    "low": "9.0",
                    "close": "10",
                    "volume": "1.0",
                },
            )
            self.assertEqual(len(rows), 4)
            self.assertIn("wrote 4 BTCUSDT candles", stdout.getvalue())

    def test_candles_command_creates_output_parent_directories(self):
        fake_client = FakeBinanceClient()
        stdout = StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "history" / "spot" / "BTCUSDT-1h.csv"
            with patch("algo_trading.cli.BinanceMarketDataClient", return_value=fake_client):
                with redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "candles",
                            "--symbol",
                            "btcusdt",
                            "--interval",
                            "1h",
                            "--limit",
                            "2",
                            "--output",
                            str(output),
                        ]
                    )

            self.assertEqual(exit_code, 0)
            self.assertTrue(output.exists())
            self.assertEqual(fake_client.kline_symbols, ["BTCUSDT"])

    def test_candles_command_exports_last_n_days(self):
        fake_client = FakeBinanceClient()
        stdout = StringIO()
        now_seconds = 1_700_000_000.0
        expected_end = int(now_seconds * 1000)
        expected_start = expected_end - (365 * 24 * 60 * 60 * 1000)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "BTCUSDT-1h-365d.csv"
            with patch("algo_trading.cli.BinanceMarketDataClient", return_value=fake_client):
                with patch("algo_trading.cli.time.time", return_value=now_seconds):
                    with redirect_stdout(stdout):
                        exit_code = main(
                            [
                                "candles",
                                "--symbol",
                                "btcusdt",
                                "--interval",
                                "1h",
                                "--days",
                                "365",
                                "--limit",
                                "1000",
                                "--output",
                                str(output),
                            ]
                        )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                fake_client.historical_requests,
                [("BTCUSDT", "1h", expected_start, expected_end, 1000)],
            )
            with output.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertIn("wrote 2 BTCUSDT candles", stdout.getvalue())

    def test_candles_command_exports_yahoo_market_last_n_days(self):
        fake_client = FakeYahooClient()
        stdout = StringIO()
        now_seconds = 1_700_000_000.0
        expected_end = int(now_seconds * 1000)
        expected_start = expected_end - (365 * 24 * 60 * 60 * 1000)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "SP500-1d-365d.csv"
            with patch("algo_trading.cli.YahooFuturesMarketDataClient", return_value=fake_client):
                with patch("algo_trading.cli.time.time", return_value=now_seconds):
                    with redirect_stdout(stdout):
                        exit_code = main(
                            [
                                "candles",
                                "--market",
                                "cme_futures",
                                "--symbol",
                                "sp500",
                                "--interval",
                                "1d",
                                "--days",
                                "365",
                                "--limit",
                                "1000",
                                "--output",
                                str(output),
                            ]
                        )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                fake_client.historical_requests,
                [("SP500", "1d", expected_start, expected_end, 1000)],
            )
            self.assertTrue(output.exists())
            self.assertIn("wrote 2 SP500 candles", stdout.getvalue())

    def test_candles_command_exports_hong_kong_stock_market_last_n_days(self):
        fake_client = FakeYahooClient()
        stdout = StringIO()
        now_seconds = 1_700_000_000.0
        expected_end = int(now_seconds * 1000)
        expected_start = expected_end - (365 * 24 * 60 * 60 * 1000)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "9988.HK-1d-365d.csv"
            with patch("algo_trading.cli.YahooFuturesMarketDataClient", return_value=fake_client):
                with patch("algo_trading.cli.time.time", return_value=now_seconds):
                    with redirect_stdout(stdout):
                        exit_code = main(
                            [
                                "candles",
                                "--market",
                                "hong_kong_stocks",
                                "--symbol",
                                "9988.hk",
                                "--interval",
                                "1d",
                                "--days",
                                "365",
                                "--limit",
                                "1000",
                                "--output",
                                str(output),
                            ]
                        )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                fake_client.historical_requests,
                [("9988.HK", "1d", expected_start, expected_end, 1000)],
            )
            self.assertTrue(output.exists())
            self.assertIn("wrote 2 9988.HK candles", stdout.getvalue())

    def test_candles_command_exports_moex_market_last_n_days(self):
        fake_client = FakeMoexClient()
        stdout = StringIO()
        now_seconds = 1_700_000_000.0
        expected_end = int(now_seconds * 1000)
        expected_start = expected_end - (365 * 24 * 60 * 60 * 1000)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "SBER-1d-365d.csv"
            with patch("algo_trading.cli.MoexSharesMarketDataClient", return_value=fake_client):
                with patch("algo_trading.cli.time.time", return_value=now_seconds):
                    with redirect_stdout(stdout):
                        exit_code = main(
                            [
                                "candles",
                                "--market",
                                "russian_bluechips",
                                "--symbol",
                                "sber",
                                "--interval",
                                "1d",
                                "--days",
                                "365",
                                "--limit",
                                "1000",
                                "--output",
                                str(output),
                            ]
                        )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                fake_client.historical_requests,
                [("SBER", "1d", expected_start, expected_end, 1000)],
            )
            self.assertTrue(output.exists())
            self.assertIn("wrote 2 SBER candles", stdout.getvalue())

    def test_candles_command_exports_moex_futures_market_last_n_days(self):
        fake_client = FakeMoexClient()
        stdout = StringIO()
        now_seconds = 1_700_000_000.0
        expected_end = int(now_seconds * 1000)
        expected_start = expected_end - (365 * 24 * 60 * 60 * 1000)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "RIM6-1d-365d.csv"
            with patch("algo_trading.cli.MoexSharesMarketDataClient", return_value=fake_client):
                with patch("algo_trading.cli.time.time", return_value=now_seconds):
                    with redirect_stdout(stdout):
                        exit_code = main(
                            [
                                "candles",
                                "--market",
                                "russian_futures",
                                "--symbol",
                                "rim6",
                                "--interval",
                                "1d",
                                "--days",
                                "365",
                                "--limit",
                                "1000",
                                "--output",
                                str(output),
                            ]
                        )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                fake_client.historical_requests,
                [("RIM6", "1d", expected_start, expected_end, 1000)],
            )
            self.assertTrue(output.exists())
            self.assertIn("wrote 2 RIM6 candles", stdout.getvalue())

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

    def test_backtest_command_records_selected_strategy_and_effective_preset(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture = tmp_path / "candles.csv"
            fixture.write_text(
                "\n".join(
                    [
                        "open_time,open,high,low,close,volume",
                        "1,10,11,9,10,1",
                        "2,9,10,8,9,1",
                        "3,8,9,7,8,1",
                        "4,9,10,8,9,1",
                        "5,11,12,10,11,1",
                        "6,13,14,12,13,1",
                        "7,15,16,14,15,1",
                        "8,14,15,13,14,1",
                        "9,12,13,11,12,1",
                        "10,10,11,9,10,1",
                        "11,9,10,8,9,1",
                        "12,8,9,7,8,1",
                        "13,7,8,6,7,1",
                        "14,8,9,7,8,1",
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
                    "--strategy",
                    "macd",
                    "--preset",
                    "aggressive",
                    "--fee-rate",
                    "0",
                    "--slippage-rate",
                    "0",
                ]
            )

            self.assertEqual(exit_code, 0)
            configs = list(tmp_path.glob("backtests/*/config.json"))
            self.assertEqual(len(configs), 1)
            config = json.loads(configs[0].read_text())
            self.assertEqual(config["strategy"], "macd")
            self.assertEqual(config["preset"], "aggressive")
            self.assertEqual(config["fast_ema"], 6)
            self.assertEqual(config["slow_ema"], 13)
            self.assertEqual(config["macd_signal"], 5)

    def test_backtest_command_records_new_strategy_parameters(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture = tmp_path / "candles.csv"
            fixture.write_text(
                "\n".join(
                    [
                        "open_time,open,high,low,close,volume",
                        "1,10,11,9,10,100",
                        "2,10,11,9,10,100",
                        "3,10,11,9,10,100",
                        "4,14,15,13,14,400",
                        "5,15,16,14,15,400",
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
                    "--strategy",
                    "volume-breakout",
                    "--donchian-period",
                    "3",
                    "--volume-period",
                    "3",
                    "--volume-multiplier",
                    "1.25",
                    "--fee-rate",
                    "0",
                    "--slippage-rate",
                    "0",
                ]
            )

            self.assertEqual(exit_code, 0)
            configs = list(tmp_path.glob("backtests/*/config.json"))
            self.assertEqual(len(configs), 1)
            config = json.loads(configs[0].read_text())
            self.assertEqual(config["strategy"], "volume-breakout")
            self.assertEqual(config["volume_period"], 3)
            self.assertEqual(config["volume_multiplier"], 1.25)

    def test_backtest_command_records_combined_signal_parameters(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture = tmp_path / "candles.csv"
            fixture.write_text(
                "\n".join(
                    [
                        "open_time,open,high,low,close,volume",
                        "1,10,11,9,10,100",
                        "2,9,10,8,9,100",
                        "3,8,9,7,8,100",
                        "4,9,10,8,9,100",
                        "5,11,12,10,11,100",
                        "6,13,14,12,13,100",
                        "7,15,16,14,15,100",
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
                    "--strategy",
                    "combined-signals",
                    "--combo-strategies",
                    "ema-rsi,macd",
                    "--combo-entry-confirmations",
                    "2",
                    "--combo-exit-confirmations",
                    "2",
                    "--combo-lookback",
                    "2",
                    "--fast-ema",
                    "2",
                    "--slow-ema",
                    "5",
                    "--rsi-period",
                    "2",
                    "--rsi-overbought",
                    "100",
                    "--macd-signal",
                    "2",
                    "--fee-rate",
                    "0",
                    "--slippage-rate",
                    "0",
                    "--stop-loss-pct",
                    "1",
                    "--take-profit-pct",
                    "1",
                ]
            )

            self.assertEqual(exit_code, 0)
            configs = list(tmp_path.glob("backtests/*/config.json"))
            self.assertEqual(len(configs), 1)
            config = json.loads(configs[0].read_text())
            self.assertEqual(config["strategy"], "combined-signals")
            self.assertEqual(config["combo_strategies"], "ema-rsi,macd")
            self.assertEqual(config["combo_entry_confirmations"], 2)
            self.assertEqual(config["combo_exit_confirmations"], 2)
            self.assertEqual(config["combo_lookback"], 2)


if __name__ == "__main__":
    unittest.main()
