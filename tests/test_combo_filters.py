import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from algo_trading.combo_filters import (
    classify_session,
    classify_vol_regime,
    default_higher_tf_interval,
    relative_strength_bias,
    strategy_family,
    vote_weight,
)
from algo_trading.models import Candle, StrategyConfig, StrategyName


NY = ZoneInfo("America/New_York")


def candle(time: int, close: float, high: float | None = None, low: float | None = None) -> Candle:
    return Candle(
        open_time=time,
        open=close,
        high=close + 1.0 if high is None else high,
        low=close - 1.0 if low is None else low,
        close=close,
        volume=1.0,
    )


class ComboFilterTests(unittest.TestCase):
    def test_higher_tf_interval_is_four_times_base(self):
        cases = [
            ("1h", "4h"),
            ("15m", "1h"),
            ("5m", "20m"),
            ("30m", "2h"),
            ("4h", "1d"),
            ("1d", "1w"),
        ]
        for interval, expected in cases:
            with self.subTest(interval=interval):
                self.assertEqual(default_higher_tf_interval(interval), expected)

    def test_strategy_family_table(self):
        cases = [
            (StrategyName.EMA_RSI, "trend"),
            (StrategyName.DONCHIAN_BREAKOUT, "breakout"),
            (StrategyName.BOLLINGER_REVERSION, "mean_reversion"),
            (StrategyName.RSI_REVERSAL, "mean_reversion"),
            (StrategyName.RSI_MEAN_REVERSION, "mean_reversion"),
            (StrategyName.TIME_SERIES_MOMENTUM, "trend"),
            (StrategyName.VOLATILITY_BREAKOUT, "breakout"),
            (StrategyName.BREADTH_CONFIRMATION, "breadth"),
        ]
        for name, family in cases:
            with self.subTest(name=name.value):
                self.assertEqual(strategy_family(name), family)

    def test_vol_regime_classifies_percentile_buckets(self):
        cases = [
            ([1.0, 1.1, 1.0, 1.2, 1.0, 10.0], 4, "high"),
            ([10.0, 9.5, 10.5, 9.0, 10.0, 1.0], 4, "low"),
            ([4.0, 5.0, 6.0, 5.0, 5.5, 5.2], 6, "mid"),
            ([1.0, 2.0], 4, "unknown"),
        ]
        for values, lookback, expected in cases:
            with self.subTest(values=values, expected=expected):
                self.assertEqual(
                    classify_vol_regime(
                        values,
                        lookback=lookback,
                        low_pct=30.0,
                        high_pct=70.0,
                    ),
                    expected,
                )

    def test_vote_weight_table(self):
        config = StrategyConfig(
            combo_regime_filter=True,
            combo_regime_damp_weight=0.25,
            combo_mtf_mode="off",
            combo_session_filter=False,
            combo_rs_enabled=False,
            combo_vote_weight_threshold=0.5,
        )
        cases = [
            ("high", "trend", 1, 1.0),
            ("high", "breakout", 1, 1.0),
            ("high", "mean_reversion", 1, 0.25),
            ("high", "breadth", 1, 1.0),
            ("low", "trend", 1, 0.25),
            ("low", "breakout", -1, 0.25),
            ("low", "mean_reversion", 1, 1.0),
            ("mid", "mean_reversion", 1, 1.0),
            ("unknown", "trend", 1, 1.0),
        ]
        for regime, family, direction, expected in cases:
            with self.subTest(regime=regime, family=family):
                self.assertEqual(
                    vote_weight(
                        config,
                        family=family,
                        direction=direction,
                        regime=regime,
                        higher_tf_bias=None,
                        session=None,
                        rs_bias=None,
                    ),
                    expected,
                )

    def test_mtf_soft_and_hard_penalize_disagreement(self):
        cases = [
            ("off", 1, -1, 1.0),
            ("soft", 1, -1, 0.25),
            ("hard", 1, -1, 0.0),
            ("hard", 1, 1, 1.0),
            ("soft", -1, None, 1.0),
            ("hard", 1, 0, 1.0),
        ]
        for mode, direction, bias, expected in cases:
            with self.subTest(mode=mode, direction=direction, bias=bias):
                config = StrategyConfig(
                    combo_regime_filter=False,
                    combo_mtf_mode=mode,
                    combo_mtf_disagree_weight=0.25,
                    combo_session_filter=False,
                    combo_rs_enabled=False,
                )
                self.assertEqual(
                    vote_weight(
                        config,
                        family="trend",
                        direction=direction,
                        regime="mid",
                        higher_tf_bias=bias,
                        session=None,
                        rs_bias=None,
                    ),
                    expected,
                )

    def test_session_weights_use_new_york_cash_hours(self):
        us_cash = int(datetime(2026, 3, 3, 10, 0, tzinfo=NY).timestamp() * 1000)
        asia = int(datetime(2026, 3, 3, 21, 0, tzinfo=NY).timestamp() * 1000)
        europe = int(datetime(2026, 3, 3, 5, 0, tzinfo=NY).timestamp() * 1000)
        overnight = int(datetime(2026, 3, 3, 17, 0, tzinfo=NY).timestamp() * 1000)

        cases = [
            (us_cash, "us_cash"),
            (asia, "asia"),
            (europe, "europe"),
            (overnight, "overnight"),
            (4, None),
        ]
        for open_time, expected in cases:
            with self.subTest(open_time=open_time, expected=expected):
                self.assertEqual(classify_session(open_time), expected)

        config = StrategyConfig(
            combo_regime_filter=False,
            combo_mtf_mode="off",
            combo_session_filter=True,
            combo_session_asia_weight=0.5,
            combo_session_europe_weight=0.75,
            combo_session_overnight_weight=0.4,
            combo_rs_enabled=False,
        )
        self.assertEqual(
            vote_weight(
                config,
                family="trend",
                direction=1,
                regime="mid",
                higher_tf_bias=None,
                session="us_cash",
                rs_bias=None,
            ),
            1.0,
        )
        self.assertEqual(
            vote_weight(
                config,
                family="trend",
                direction=1,
                regime="mid",
                higher_tf_bias=None,
                session="asia",
                rs_bias=None,
            ),
            0.5,
        )

    def test_relative_strength_skips_missing_pair(self):
        symbol = [candle(index, 10 + index) for index in range(8)]
        self.assertIsNone(relative_strength_bias(symbol, [], lookback=4, index=7))
        pair = [candle(index, 10 + (index * 3)) for index in range(8)]
        self.assertEqual(relative_strength_bias(symbol, pair, lookback=4, index=7), -1)
        weaker_pair = [candle(index, 10 + (index * 0.2)) for index in range(8)]
        self.assertEqual(relative_strength_bias(symbol, weaker_pair, lookback=4, index=7), 1)

    def test_rs_soft_veto_downweights_disagreement(self):
        config = StrategyConfig(
            combo_regime_filter=False,
            combo_mtf_mode="off",
            combo_session_filter=False,
            combo_rs_enabled=True,
            combo_rs_disagree_weight=0.25,
        )
        self.assertEqual(
            vote_weight(
                config,
                family="trend",
                direction=1,
                regime="mid",
                higher_tf_bias=None,
                session=None,
                rs_bias=-1,
            ),
            0.25,
        )
        self.assertEqual(
            vote_weight(
                config,
                family="trend",
                direction=1,
                regime="mid",
                higher_tf_bias=None,
                session=None,
                rs_bias=None,
            ),
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
