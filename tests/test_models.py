import unittest

from algo_trading.models import (
    AllowedSide,
    Candle,
    PositionSide,
    SignalType,
    StrategyConfig,
    StrategyName,
    StrategyPreset,
)


class ModelTests(unittest.TestCase):
    def test_default_config_is_safe_and_both_sided(self):
        config = StrategyConfig()

        self.assertEqual(config.symbol, "BTCUSDT")
        self.assertEqual(config.allowed_side, AllowedSide.BOTH)
        self.assertEqual(config.starting_balance, 10000.0)
        self.assertEqual(config.fee_rate, 0.001)
        self.assertEqual(config.slippage_rate, 0.0005)
        self.assertEqual(config.strategy, StrategyName.EMA_RSI)
        self.assertEqual(config.preset, StrategyPreset.CUSTOM)
        self.assertEqual(config.macd_signal, 9)
        self.assertEqual(config.bollinger_period, 20)
        self.assertEqual(config.bollinger_stddev, 2.0)
        self.assertEqual(config.donchian_period, 20)
        self.assertEqual(config.rsi_midline, 50.0)

    def test_candle_rejects_invalid_prices(self):
        with self.assertRaises(ValueError):
            Candle(
                open_time=1,
                open=100.0,
                high=99.0,
                low=90.0,
                close=95.0,
                volume=1.0,
            )

    def test_enums_capture_long_short_signal_shape(self):
        self.assertEqual(PositionSide.LONG.value, "long")
        self.assertEqual(PositionSide.SHORT.value, "short")
        self.assertEqual(SignalType.ENTER_LONG.value, "enter_long")
        self.assertEqual(SignalType.ENTER_SHORT.value, "enter_short")


if __name__ == "__main__":
    unittest.main()
