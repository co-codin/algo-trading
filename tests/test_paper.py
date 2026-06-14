import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from algo_trading.cli import main
from algo_trading.models import Candle, StrategyConfig
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
