from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from algo_trading.combo_ensemble import (
    combo_member_vote_weight,
    higher_timeframe_interval,
    session_name,
    volatility_regime_series,
)
from algo_trading.models import (
    AllowedSide,
    Candle,
    SignalType,
    StrategyConfig,
    StrategyName,
)
from algo_trading.strategy import (
    build_strategy_context,
    combo_ensemble_snapshot,
    entry_signal_for_index,
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


def candles(prices: list[float]) -> list[Candle]:
    return [candle(index, price) for index, price in enumerate(prices)]


def utc_ms(year: int, month: int, day: int, hour: int, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp() * 1000)


class ComboEnsembleTests(unittest.TestCase):
    def test_higher_timeframe_interval_scales_configured_interval(self):
        cases = [
            ("1h", 4, "4h"),
            ("15m", 4, "1h"),
            ("5m", 4, "20m"),
            ("1d", 4, "4d"),
            ("4h", 4, "16h"),
            ("1w", 2, "2w"),
        ]
        for interval, multiple, expected in cases:
            with self.subTest(interval=interval, multiple=multiple):
                self.assertEqual(higher_timeframe_interval(interval, multiple), expected)

    def test_volatility_regime_classifies_low_mid_high(self):
        cases = [
            ([1.0] * 50 + [10.0], "high"),
            ([10.0] * 50 + [1.0], "low"),
            ([5.0] * 51, "mid"),
            ([1.0, 2.0, 3.0], "mid"),
        ]
        for values, expected in cases:
            with self.subTest(expected=expected, values=values[-3:]):
                regimes = volatility_regime_series(
                    values,
                    lookback=50,
                    low_percentile=33.0,
                    high_percentile=67.0,
                )
                self.assertEqual(regimes[-1], expected)

    def test_session_name_uses_new_york_cash_hours(self):
        cases = [
            (utc_ms(2026, 6, 15, 14, 0), "us-cash"),
            (utc_ms(2026, 6, 15, 10, 0), "europe"),
            (utc_ms(2026, 6, 16, 0, 0), "asia"),
            (utc_ms(2026, 6, 15, 21, 0), "overnight"),
            (utc_ms(2026, 6, 14, 14, 0), "overnight"),
        ]
        for open_time, expected in cases:
            with self.subTest(expected=expected, open_time=open_time):
                self.assertEqual(session_name(open_time), expected)

    def test_regime_filter_ignores_mismatched_family_votes(self):
        cases = [
            ("high", StrategyName.BOLLINGER_REVERSION, SignalType.ENTER_LONG, 0.0),
            ("high", StrategyName.EMA_RSI, SignalType.ENTER_LONG, 1.0),
            ("low", StrategyName.EMA_RSI, SignalType.ENTER_LONG, 0.0),
            ("low", StrategyName.RSI_MEAN_REVERSION, SignalType.ENTER_LONG, 1.0),
            ("mid", StrategyName.EMA_RSI, SignalType.ENTER_LONG, 1.0),
            ("mid", StrategyName.BOLLINGER_REVERSION, SignalType.ENTER_LONG, 1.0),
        ]
        config = StrategyConfig()
        for regime, strategy_name, signal_type, expected in cases:
            with self.subTest(regime=regime, strategy=strategy_name):
                weight = combo_member_vote_weight(
                    strategy_name,
                    signal_type,
                    config,
                    regime=regime,
                    higher_tf_bias=0,
                    relative_strength_bias=0,
                    session="us-cash",
                )
                self.assertEqual(weight, expected)

    def test_mtf_disagreement_can_hard_drop_or_soft_penalize(self):
        cases = [
            ("hard", SignalType.ENTER_LONG, -1, 0.0),
            ("soft", SignalType.ENTER_LONG, -1, 0.5),
            ("hard", SignalType.ENTER_LONG, 1, 1.0),
            ("hard", SignalType.ENTER_LONG, 0, 1.0),
        ]
        for mode, signal_type, bias, expected in cases:
            with self.subTest(mode=mode, bias=bias):
                weight = combo_member_vote_weight(
                    StrategyName.EMA_RSI,
                    signal_type,
                    StrategyConfig(combo_mtf_mode=mode),
                    regime="mid",
                    higher_tf_bias=bias,
                    relative_strength_bias=0,
                    session="us-cash",
                )
                self.assertEqual(weight, expected)

    def test_relative_strength_soft_veto_skips_when_bias_missing(self):
        cases = [
            (-1, SignalType.ENTER_LONG, 0.5),
            (1, SignalType.ENTER_LONG, 1.0),
            (0, SignalType.ENTER_LONG, 1.0),
            (1, SignalType.ENTER_SHORT, 0.5),
        ]
        for bias, signal_type, expected in cases:
            with self.subTest(bias=bias, signal_type=signal_type):
                weight = combo_member_vote_weight(
                    StrategyName.EMA_RSI,
                    signal_type,
                    StrategyConfig(),
                    regime="mid",
                    higher_tf_bias=0,
                    relative_strength_bias=bias,
                    session="us-cash",
                )
                self.assertEqual(weight, expected)

    def test_session_filter_is_off_by_default(self):
        default_weight = combo_member_vote_weight(
            StrategyName.EMA_RSI,
            SignalType.ENTER_LONG,
            StrategyConfig(),
            regime="mid",
            higher_tf_bias=0,
            relative_strength_bias=0,
            session="asia",
        )
        filtered_weight = combo_member_vote_weight(
            StrategyName.EMA_RSI,
            SignalType.ENTER_LONG,
            StrategyConfig(combo_session_filter=True, combo_session_off_weight=0.0),
            regime="mid",
            higher_tf_bias=0,
            relative_strength_bias=0,
            session="asia",
        )

        self.assertEqual(default_weight, 1.0)
        self.assertEqual(filtered_weight, 0.0)

    def test_combo_low_regime_drops_trend_votes(self):
        config = StrategyConfig(
            strategy=StrategyName.COMBINED_SIGNALS,
            allowed_side=AllowedSide.LONG_ONLY,
            fast_ema=2,
            slow_ema=5,
            rsi_period=2,
            rsi_overbought=100.0,
            macd_signal=2,
            combo_strategies="ema-rsi,macd",
            combo_entry_confirmations=2,
            combo_lookback=2,
        )
        context = replace_regime(
            build_strategy_context(candles([10, 9, 8, 9, 11, 13, 15]), config),
            "low",
        )

        signal = entry_signal_for_index(config, context, 4)

        self.assertEqual(signal.type, SignalType.HOLD)
        self.assertEqual(signal.reason, "insufficient_combo_confirmations")

    def test_combo_mtf_disagreement_blocks_actionable_votes(self):
        config = StrategyConfig(
            strategy=StrategyName.COMBINED_SIGNALS,
            allowed_side=AllowedSide.LONG_ONLY,
            fast_ema=2,
            slow_ema=5,
            rsi_period=2,
            rsi_overbought=100.0,
            macd_signal=2,
            combo_strategies="ema-rsi,macd",
            combo_entry_confirmations=2,
            combo_lookback=2,
        )
        context = build_strategy_context(
            candles([10, 9, 8, 9, 11, 13, 15]),
            config,
            higher_tf_bias=-1,
        )

        signal = entry_signal_for_index(config, context, 4)
        snapshot = combo_ensemble_snapshot(config, context, 4)

        self.assertEqual(signal.type, SignalType.HOLD)
        self.assertEqual(snapshot.higher_tf_bias, -1)
        self.assertEqual(snapshot.long_votes, [])

    def test_combo_snapshot_exposes_regime_and_keeps_conf_denominator(self):
        config = StrategyConfig(
            strategy=StrategyName.COMBINED_SIGNALS,
            allowed_side=AllowedSide.LONG_ONLY,
            fast_ema=2,
            slow_ema=5,
            rsi_period=2,
            rsi_overbought=100.0,
            macd_signal=2,
            combo_strategies="ema-rsi,macd",
            combo_entry_confirmations=2,
            combo_lookback=2,
        )
        context = build_strategy_context(candles([10, 9, 8, 9, 11, 13, 15]), config)

        snapshot = combo_ensemble_snapshot(config, context, 4)

        self.assertEqual(snapshot.regime, "mid")
        self.assertEqual(snapshot.member_count, 2)
        self.assertEqual(snapshot.long_votes, ["ema-rsi", "macd"])

    def test_breadth_confirmation_uses_aligned_breadth_bars(self):
        config = StrategyConfig(strategy=StrategyName.BREADTH_CONFIRMATION)
        open_time = utc_ms(2026, 1, 2, 15, 0)
        context = build_strategy_context(
            [candle(open_time, 100.0)],
            config,
            breadth_bars_by_symbol={
                "$S5FD": [SimpleNamespace(date=date(2026, 1, 2), close=60.0)],
                "$S5TW": [SimpleNamespace(date=date(2026, 1, 2), close=58.0)],
            },
        )

        signal = entry_signal_for_index(config, context, 0)

        self.assertEqual(signal.type, SignalType.ENTER_LONG)
        self.assertEqual(signal.reason, "breadth_confirmation_long")


def replace_regime(context, regime: str):
    from dataclasses import replace

    return replace(context, volatility_regime=[regime] * len(context.candles))


if __name__ == "__main__":
    unittest.main()
