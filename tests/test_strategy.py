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
from algo_trading.strategy import (
    apply_strategy_preset,
    build_strategy_context,
    entry_signal_for_index,
    exit_signal_for_position,
    get_strategy,
    list_strategy_names,
)


def candle(time: int, close: float) -> Candle:
    return Candle(
        open_time=time,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1.0,
    )


def candles(prices: list[float]) -> list[Candle]:
    return [candle(index, price) for index, price in enumerate(prices)]


def first_entry_signal(config: StrategyConfig, prices: list[float]):
    context = build_strategy_context(candles(prices), config)
    for index in range(len(prices)):
        signal = entry_signal_for_index(config, context, index)
        if signal.type is not SignalType.HOLD:
            return signal
    return None


class StrategyTests(unittest.TestCase):
    def test_registry_lists_all_strategies(self):
        self.assertEqual(
            list_strategy_names(),
            [
                "ema-rsi",
                "macd",
                "bollinger-reversion",
                "donchian-breakout",
                "rsi-reversal",
            ],
        )

    def test_registry_rejects_unknown_strategy(self):
        with self.assertRaisesRegex(ValueError, "strategy"):
            get_strategy("not-a-strategy")

    def test_conservative_preset_is_deterministic(self):
        config = apply_strategy_preset(
            StrategyConfig(
                strategy=StrategyName.MACD,
                preset=StrategyPreset.CONSERVATIVE,
            )
        )

        self.assertEqual(config.position_fraction, 0.5)
        self.assertEqual(config.stop_loss_pct, 0.02)
        self.assertEqual(config.take_profit_pct, 0.04)
        self.assertEqual(config.trailing_stop_pct, 0.015)
        self.assertEqual(config.fast_ema, 18)
        self.assertEqual(config.slow_ema, 39)
        self.assertEqual(config.macd_signal, 12)

    def test_ema_rsi_strategy_enters_long_on_cross_above(self):
        config = StrategyConfig(
            strategy=StrategyName.EMA_RSI,
            allowed_side=AllowedSide.LONG_ONLY,
            fast_ema=1,
            slow_ema=3,
            rsi_period=2,
            rsi_overbought=100.0,
            rsi_oversold=0.0,
        )

        signal = first_entry_signal(config, [10, 9, 8, 9, 11, 13])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "ema_cross_above")

    def test_macd_strategy_enters_long_on_macd_cross_above(self):
        config = StrategyConfig(
            strategy=StrategyName.MACD,
            allowed_side=AllowedSide.LONG_ONLY,
            fast_ema=2,
            slow_ema=5,
            macd_signal=2,
        )

        signal = first_entry_signal(config, [10, 9, 8, 9, 11, 13, 15])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "macd_cross_above")

    def test_bollinger_reversion_enters_long_after_lower_band_reclaim(self):
        config = StrategyConfig(
            strategy=StrategyName.BOLLINGER_REVERSION,
            bollinger_period=3,
            bollinger_stddev=1.0,
        )

        signal = first_entry_signal(config, [10, 10, 10, 7, 10, 11])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "bollinger_lower_reclaim")

    def test_donchian_breakout_enters_long_above_previous_channel(self):
        config = StrategyConfig(
            strategy=StrategyName.DONCHIAN_BREAKOUT,
            donchian_period=3,
        )

        signal = first_entry_signal(config, [10, 10, 10, 14, 15])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "donchian_breakout_high")

    def test_rsi_reversal_enters_long_when_rsi_leaves_oversold(self):
        config = StrategyConfig(
            strategy=StrategyName.RSI_REVERSAL,
            rsi_period=2,
            rsi_oversold=30.0,
            rsi_overbought=70.0,
        )

        signal = first_entry_signal(config, [10, 9, 8, 9, 10, 11])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "rsi_reversal_long")

    def test_allowed_side_blocks_disallowed_entries(self):
        config = StrategyConfig(
            strategy=StrategyName.MACD,
            allowed_side=AllowedSide.LONG_ONLY,
            fast_ema=2,
            slow_ema=5,
            macd_signal=2,
        )

        signal = first_entry_signal(config, [15, 14, 13, 12, 10, 8, 6])

        self.assertIsNone(signal)

    def test_strategy_exit_signal_for_position_uses_selected_strategy(self):
        config = StrategyConfig(
            strategy=StrategyName.MACD,
            fast_ema=2,
            slow_ema=5,
            macd_signal=2,
        )
        context = build_strategy_context(candles([15, 14, 13, 14, 16, 15, 12, 10]), config)

        exit_signal = None
        for index in range(1, 8):
            signal = exit_signal_for_position(PositionSide.LONG, config, context, index)
            if signal.type is SignalType.EXIT_LONG:
                exit_signal = signal
                break

        self.assertIsNotNone(exit_signal)
        self.assertEqual(exit_signal.reason, "macd_cross_below")


if __name__ == "__main__":
    unittest.main()
