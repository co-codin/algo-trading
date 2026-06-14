import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from algo_trading.cli import main
from algo_trading.data import TransientMarketDataError
from algo_trading.models import Candle, StrategyConfig, StrategyName, StrategyPreset
from algo_trading.paper import run_paper_session


def candle(time: int, close: float) -> Candle:
    return Candle(
        open_time=time,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1.0,
    )


class FakeMarketDataClient:
    def __init__(self) -> None:
        self.calls = 0
        self.api_key = None

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        self.calls += 1
        return [
            candle(1, 10.0),
            candle(2, 12.0),
            candle(3, 13.0),
            candle(4, 14.0),
        ][-limit:]


class LongerMarketDataClient:
    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        prices = [10, 9, 8, 9, 10, 11, 10, 9, 8, 7]
        return [candle(index + 1, price) for index, price in enumerate(prices)][-limit:]


class ProgressiveMarketDataClient:
    def __init__(self) -> None:
        self.calls = 0

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        self.calls += 1
        if self.calls == 1:
            return [candle(1, 10.0), candle(2, 12.0), candle(3, 13.0)]
        return [candle(3, 13.0), candle(4, 14.0), candle(5, 15.0)]


class FlakyMarketDataClient:
    def __init__(self) -> None:
        self.calls = 0

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        self.calls += 1
        if self.calls == 1:
            raise TransientMarketDataError("temporary market data outage")
        return [candle(1, 10.0), candle(2, 12.0), candle(3, 13.0)]


class BrokenMarketDataClient:
    def __init__(self) -> None:
        self.calls = 0

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        self.calls += 1
        if self.calls == 1:
            return [candle(1, 10.0), candle(2, 12.0), candle(3, 13.0)]
        raise ValueError("invalid kline row")


class PaperTests(unittest.TestCase):
    def test_paper_session_writes_outputs_without_credentials(self):
        client = FakeMarketDataClient()

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = run_paper_session(
                client,
                StrategyConfig(fast_ema=1, slow_ema=2, rsi_period=2),
                Path(tmp),
                poll_seconds=0,
                iterations=2,
                limit=4,
            )

            self.assertEqual(client.calls, 2)
            self.assertIsNone(client.api_key)
            self.assertTrue((run_dir / "summary.json").exists())
            self.assertTrue((run_dir / "trades.csv").exists())

    def test_paper_session_records_effective_preset_config(self):
        client = LongerMarketDataClient()

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = run_paper_session(
                client,
                StrategyConfig(
                    strategy=StrategyName.RSI_REVERSAL,
                    preset=StrategyPreset.AGGRESSIVE,
                    fee_rate=0.0,
                    slippage_rate=0.0,
                ),
                Path(tmp),
                poll_seconds=0,
                iterations=1,
                limit=10,
            )

            config = json.loads((run_dir / "config.json").read_text())
            self.assertEqual(config["strategy"], "rsi-reversal")
            self.assertEqual(config["preset"], "aggressive")
            self.assertEqual(config["rsi_period"], 7)
            self.assertEqual(config["stop_loss_pct"], 0.04)

    def test_paper_session_accumulates_candles_across_polls(self):
        client = ProgressiveMarketDataClient()

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = run_paper_session(
                client,
                StrategyConfig(fast_ema=1, slow_ema=2, rsi_period=2),
                Path(tmp),
                poll_seconds=0,
                iterations=2,
                limit=3,
            )

            equity_text = (run_dir / "equity.csv").read_text()
            self.assertIn("1,", equity_text)
            self.assertIn("5,", equity_text)

    def test_paper_session_retries_failed_poll_without_inventing_prices(self):
        client = FlakyMarketDataClient()

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = run_paper_session(
                client,
                StrategyConfig(fast_ema=1, slow_ema=2, rsi_period=2),
                Path(tmp),
                poll_seconds=0,
                iterations=2,
                limit=3,
            )

            self.assertEqual(client.calls, 2)
            self.assertTrue((run_dir / "summary.json").exists())

    def test_paper_session_propagates_non_transient_poll_errors(self):
        client = BrokenMarketDataClient()

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "invalid kline row"):
                run_paper_session(
                    client,
                    StrategyConfig(fast_ema=1, slow_ema=2, rsi_period=2),
                    Path(tmp),
                    poll_seconds=0,
                    iterations=2,
                    limit=3,
                )

    def test_paper_cli_uses_read_only_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_client = FakeMarketDataClient()
            with patch("algo_trading.cli.BinanceMarketDataClient", return_value=fake_client):
                exit_code = main(
                    [
                        "paper",
                        "--output-root",
                        tmp,
                        "--iterations",
                        "1",
                        "--poll-seconds",
                        "0",
                        "--limit",
                        "4",
                        "--fast-ema",
                        "1",
                        "--slow-ema",
                        "2",
                        "--rsi-period",
                        "2",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(fake_client.calls, 1)
            self.assertEqual(len(list(Path(tmp).glob("paper/*/summary.json"))), 1)


if __name__ == "__main__":
    unittest.main()
