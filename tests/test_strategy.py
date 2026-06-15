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


def candle(time: int, close: float, volume: float = 1.0) -> Candle:
    return Candle(
        open_time=time,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=volume,
    )


def candles(prices: list[float], volumes: list[float] | None = None) -> list[Candle]:
    source_volumes = volumes or [1.0] * len(prices)
    return [
        candle(index, price, volume)
        for index, (price, volume) in enumerate(zip(prices, source_volumes))
    ]


def first_entry_signal(
    config: StrategyConfig,
    prices: list[float],
    volumes: list[float] | None = None,
):
    context = build_strategy_context(candles(prices, volumes), config)
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
                "supertrend",
                "vwap-reversion",
                "stoch-rsi-reversal",
                "ema-ribbon",
                "momentum-scalping",
                "keltner-breakout",
                "ema-pullback",
                "atr-trailing-trend",
                "cci-reversal",
                "williams-r-reversal",
                "bollinger-squeeze-release",
                "obv-trend",
                "volume-breakout",
                "vwap-trend-continuation",
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

    def test_supertrend_enters_long_on_atr_trend_flip(self):
        config = StrategyConfig(
            strategy=StrategyName("supertrend"),
            allowed_side=AllowedSide.LONG_ONLY,
            atr_period=2,
            supertrend_multiplier=1.0,
        )

        signal = first_entry_signal(config, [12, 11, 10, 9, 10, 12, 14, 16])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "supertrend_flip_long")

    def test_vwap_reversion_enters_long_after_vwap_reclaim(self):
        config = StrategyConfig(
            strategy=StrategyName("vwap-reversion"),
            allowed_side=AllowedSide.LONG_ONLY,
            vwap_period=3,
            vwap_threshold_pct=0.0,
        )

        signal = first_entry_signal(config, [10, 10, 10, 7, 10, 11])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "vwap_reclaim_long")

    def test_stoch_rsi_reversal_enters_long_when_oscillator_recovers(self):
        config = StrategyConfig(
            strategy=StrategyName("stoch-rsi-reversal"),
            allowed_side=AllowedSide.LONG_ONLY,
            rsi_period=2,
            stoch_rsi_period=2,
            stoch_rsi_oversold=20.0,
            stoch_rsi_overbought=80.0,
        )

        signal = first_entry_signal(config, [10, 9, 8, 9, 10, 11])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "stoch_rsi_reversal_long")

    def test_ema_ribbon_enters_long_when_ribbon_turns_bullish(self):
        config = StrategyConfig(
            strategy=StrategyName("ema-ribbon"),
            allowed_side=AllowedSide.LONG_ONLY,
            ema_ribbon_fast=2,
            ema_ribbon_mid=3,
            ema_ribbon_slow=5,
        )

        signal = first_entry_signal(config, [10, 9, 8, 9, 11, 13, 15])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "ema_ribbon_bullish")

    def test_momentum_scalping_enters_long_on_confirmed_momentum(self):
        config = StrategyConfig(
            strategy=StrategyName("momentum-scalping"),
            allowed_side=AllowedSide.LONG_ONLY,
            fast_ema=2,
            slow_ema=5,
            macd_signal=2,
            rsi_period=2,
            momentum_period=2,
        )

        signal = first_entry_signal(config, [10, 9, 8, 9, 11, 13, 15])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "momentum_scalping_long")

    def test_keltner_breakout_enters_long_above_upper_band(self):
        config = StrategyConfig(
            strategy=StrategyName("keltner-breakout"),
            allowed_side=AllowedSide.LONG_ONLY,
            atr_period=3,
            keltner_multiplier=0.5,
        )

        signal = first_entry_signal(config, [10, 10, 10, 13])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "keltner_breakout_long")

    def test_ema_pullback_enters_long_when_price_reclaims_fast_ema_in_uptrend(self):
        config = StrategyConfig(
            strategy=StrategyName("ema-pullback"),
            allowed_side=AllowedSide.LONG_ONLY,
            fast_ema=2,
            slow_ema=4,
        )

        signal = first_entry_signal(config, [10, 11, 12, 11, 13])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "ema_pullback_long")

    def test_atr_trailing_trend_enters_long_on_trend_flip(self):
        config = StrategyConfig(
            strategy=StrategyName("atr-trailing-trend"),
            allowed_side=AllowedSide.LONG_ONLY,
            atr_period=2,
            supertrend_multiplier=1.0,
        )

        signal = first_entry_signal(config, [12, 11, 10, 9, 10, 12, 14, 16])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "atr_trailing_trend_long")

    def test_cci_reversal_enters_long_when_cci_leaves_oversold(self):
        config = StrategyConfig(
            strategy=StrategyName("cci-reversal"),
            allowed_side=AllowedSide.LONG_ONLY,
            cci_period=3,
            cci_oversold=-100.0,
            cci_overbought=100.0,
        )

        signal = first_entry_signal(config, [10, 10, 7, 10, 11])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "cci_reversal_long")

    def test_williams_r_reversal_enters_long_when_oscillator_leaves_oversold(self):
        config = StrategyConfig(
            strategy=StrategyName("williams-r-reversal"),
            allowed_side=AllowedSide.LONG_ONLY,
            williams_period=3,
            williams_oversold=-80.0,
            williams_overbought=-20.0,
        )

        signal = first_entry_signal(config, [10, 10, 7, 10, 11])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "williams_r_reversal_long")

    def test_bollinger_squeeze_release_enters_long_on_expansion_breakout(self):
        config = StrategyConfig(
            strategy=StrategyName("bollinger-squeeze-release"),
            allowed_side=AllowedSide.LONG_ONLY,
            bollinger_period=3,
            bollinger_stddev=1.0,
            squeeze_threshold_pct=0.05,
        )

        signal = first_entry_signal(config, [10, 10, 10, 12, 14])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "bollinger_squeeze_release_long")

    def test_obv_trend_enters_long_when_obv_confirms_price_trend(self):
        config = StrategyConfig(
            strategy=StrategyName("obv-trend"),
            allowed_side=AllowedSide.LONG_ONLY,
            slow_ema=3,
            volume_period=2,
        )

        signal = first_entry_signal(config, [10, 9, 10, 11, 12], [100, 100, 300, 300, 300])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "obv_trend_long")

    def test_volume_breakout_enters_long_when_price_and_volume_break_out(self):
        config = StrategyConfig(
            strategy=StrategyName("volume-breakout"),
            allowed_side=AllowedSide.LONG_ONLY,
            donchian_period=3,
            volume_period=3,
            volume_multiplier=1.5,
        )

        signal = first_entry_signal(config, [10, 10, 10, 14], [100, 100, 100, 400])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "volume_breakout_long")

    def test_vwap_trend_continuation_enters_long_after_vwap_reclaim_in_uptrend(self):
        config = StrategyConfig(
            strategy=StrategyName("vwap-trend-continuation"),
            allowed_side=AllowedSide.LONG_ONLY,
            fast_ema=2,
            slow_ema=4,
            vwap_period=3,
        )

        signal = first_entry_signal(config, [10, 11, 12, 11, 13])

        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "vwap_trend_continuation_long")

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
