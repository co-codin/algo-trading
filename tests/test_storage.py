import json
import tempfile
import unittest
from pathlib import Path

from algo_trading.models import (
    BacktestResult,
    EquityPoint,
    PositionSide,
    StrategyConfig,
    Trade,
)
from algo_trading.storage import write_run_outputs


class StorageTests(unittest.TestCase):
    def test_write_run_outputs_creates_expected_files(self):
        result = BacktestResult(
            trades=[
                Trade(
                    side=PositionSide.LONG,
                    entry_time=1,
                    exit_time=2,
                    entry_price=100.0,
                    exit_price=110.0,
                    quantity=1.0,
                    realized_pnl=10.0,
                    fees=0.1,
                    slippage=0.05,
                    entry_reason="ema_cross_above",
                    exit_reason="final_candle",
                )
            ],
            equity=[
                EquityPoint(
                    time=2,
                    equity=10010.0,
                    cash=10010.0,
                    position_side="",
                    position_quantity=0.0,
                )
            ],
            summary={"final_balance": 10010.0, "trades": 1},
        )

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = write_run_outputs(
                "backtests",
                StrategyConfig(symbol="BTCUSDT"),
                result,
                Path(tmp),
            )

            self.assertTrue((run_dir / "config.json").exists())
            self.assertTrue((run_dir / "trades.csv").exists())
            self.assertTrue((run_dir / "equity.csv").exists())
            self.assertTrue((run_dir / "summary.json").exists())
            config = json.loads((run_dir / "config.json").read_text())
            self.assertEqual(config["symbol"], "BTCUSDT")
            trades_text = (run_dir / "trades.csv").read_text()
            self.assertIn("side", trades_text)


if __name__ == "__main__":
    unittest.main()
