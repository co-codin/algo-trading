import json
import tempfile
import unittest
from pathlib import Path

from algo_trading.cli import main


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


if __name__ == "__main__":
    unittest.main()
