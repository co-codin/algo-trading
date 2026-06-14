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


if __name__ == "__main__":
    unittest.main()
