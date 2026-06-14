import unittest

from algo_trading.models import Candle, PositionSide, StrategyConfig
from algo_trading.simulator import run_backtest


def candle(time: int, close: float) -> Candle:
    return Candle(
        open_time=time,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1.0,
    )


class SimulatorTests(unittest.TestCase):
    def test_backtest_rejects_candles_before_indicator_warmup(self):
        candles = [candle(index, price) for index, price in enumerate([10, 11, 12, 13])]

        with self.assertRaisesRegex(ValueError, "not enough candles"):
            run_backtest(candles, StrategyConfig())

    def test_backtest_rejects_invalid_risk_config(self):
        candles = [candle(index, float(index + 10)) for index in range(30)]
        config = StrategyConfig(stop_loss_pct=-0.01)

        with self.assertRaisesRegex(ValueError, "stop_loss_pct"):
            run_backtest(candles, config)

    def test_backtest_rejects_inverted_rsi_thresholds(self):
        candles = [candle(index, float(index + 10)) for index in range(30)]
        config = StrategyConfig(rsi_oversold=75.0, rsi_overbought=70.0)

        with self.assertRaisesRegex(ValueError, "rsi"):
            run_backtest(candles, config)

    def test_backtest_produces_trade_and_equity(self):
        candles = [
            candle(index, price)
            for index, price in enumerate([10, 12, 13, 14, 13, 12, 11, 10])
        ]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            position_fraction=0.5,
            fee_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(candles, config)

        self.assertGreaterEqual(len(result.equity), len(candles))
        self.assertIn("final_balance", result.summary)
        self.assertGreater(len(result.trades), 0)

    def test_long_trade_can_profit_when_price_rises(self):
        candles = [candle(index, price) for index, price in enumerate([10, 12, 13, 14])]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            fee_rate=0.0,
            slippage_rate=0.0,
            position_fraction=1.0,
        )

        result = run_backtest(candles, config)

        long_trades = [trade for trade in result.trades if trade.side is PositionSide.LONG]
        self.assertTrue(long_trades)
        self.assertTrue(any(trade.realized_pnl > 0 for trade in long_trades))

    def test_short_trade_can_profit_when_price_falls(self):
        candles = [candle(index, price) for index, price in enumerate([12, 10, 9, 8])]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            fee_rate=0.0,
            slippage_rate=0.0,
            position_fraction=1.0,
        )

        result = run_backtest(candles, config)

        short_trades = [trade for trade in result.trades if trade.side is PositionSide.SHORT]
        self.assertTrue(short_trades)
        self.assertTrue(any(trade.realized_pnl > 0 for trade in short_trades))

    def test_stop_loss_exit_reason_is_recorded(self):
        candles = [candle(index, price) for index, price in enumerate([10, 12, 11, 10])]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            stop_loss_pct=0.05,
            take_profit_pct=1.0,
            fee_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(candles, config)

        self.assertEqual(result.trades[0].exit_reason, "stop_loss")

    def test_take_profit_exit_reason_is_recorded(self):
        candles = [candle(index, price) for index, price in enumerate([10, 12, 13, 14])]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            stop_loss_pct=1.0,
            take_profit_pct=0.05,
            fee_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(candles, config)

        self.assertEqual(result.trades[0].exit_reason, "take_profit")

    def test_trailing_stop_exit_reason_is_recorded(self):
        candles = [candle(index, price) for index, price in enumerate([10, 12, 14, 13])]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            stop_loss_pct=1.0,
            take_profit_pct=1.0,
            trailing_stop_pct=0.05,
            fee_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(candles, config)

        self.assertEqual(result.trades[0].exit_reason, "trailing_stop")

    def test_fees_and_slippage_are_recorded(self):
        candles = [candle(index, price) for index, price in enumerate([10, 12, 13, 14])]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            fee_rate=0.001,
            slippage_rate=0.0005,
        )

        result = run_backtest(candles, config)

        self.assertGreater(result.trades[0].fees, 0)
        self.assertGreater(result.trades[0].slippage, 0)
        self.assertGreater(result.summary["fee_total"], 0)
        self.assertGreater(result.summary["slippage_estimate"], 0)

    def test_profit_factor_is_explicit_when_there_are_no_losses(self):
        candles = [candle(index, price) for index, price in enumerate([10, 12, 13, 14])]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            fee_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(candles, config)

        self.assertEqual(result.summary["profit_factor"], "infinite")


if __name__ == "__main__":
    unittest.main()
