import unittest

from algo_trading.models import AllowedSide, PositionSide, SignalType, StrategyConfig
from algo_trading.strategy import exit_signal_for_position, signal_for_index


class StrategyTests(unittest.TestCase):
    def test_enter_long_on_fast_cross_above_slow(self):
        config = StrategyConfig(rsi_overbought=70.0)

        signal = signal_for_index(
            config,
            fast=[9.0, 11.0],
            slow=[10.0, 10.0],
            rsi_values=[50.0, 60.0],
            index=1,
        )

        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "ema_cross_above")

    def test_enter_short_on_fast_cross_below_slow(self):
        config = StrategyConfig(rsi_oversold=30.0)

        signal = signal_for_index(
            config,
            fast=[11.0, 9.0],
            slow=[10.0, 10.0],
            rsi_values=[50.0, 40.0],
            index=1,
        )

        self.assertEqual(signal.type, SignalType.ENTER_SHORT)
        self.assertEqual(signal.reason, "ema_cross_below")

    def test_long_only_blocks_short(self):
        config = StrategyConfig(allowed_side=AllowedSide.LONG_ONLY)

        signal = signal_for_index(
            config,
            fast=[11.0, 9.0],
            slow=[10.0, 10.0],
            rsi_values=[50.0, 40.0],
            index=1,
        )

        self.assertEqual(signal.type, SignalType.HOLD)

    def test_exit_long_on_fast_cross_below_slow(self):
        signal = exit_signal_for_position(
            PositionSide.LONG,
            fast=[11.0, 9.0],
            slow=[10.0, 10.0],
            index=1,
        )

        self.assertEqual(signal.type, SignalType.EXIT_LONG)

    def test_exit_short_on_fast_cross_above_slow(self):
        signal = exit_signal_for_position(
            PositionSide.SHORT,
            fast=[9.0, 11.0],
            slow=[10.0, 10.0],
            index=1,
        )

        self.assertEqual(signal.type, SignalType.EXIT_SHORT)


if __name__ == "__main__":
    unittest.main()
