import unittest

from algo_trading.indicators import (
    bollinger_width,
    commodity_channel_index,
    ema,
    keltner_channels,
    on_balance_volume,
    rolling_volume_mean,
    rsi,
    williams_r,
)
from algo_trading.models import Candle


def candle(time: int, close: float, volume: float = 100.0) -> Candle:
    return Candle(
        open_time=time,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=volume,
    )


def candles(prices: list[float], volumes: list[float] | None = None) -> list[Candle]:
    source_volumes = volumes or [100.0] * len(prices)
    return [
        candle(index, price, volume)
        for index, (price, volume) in enumerate(zip(prices, source_volumes))
    ]


class IndicatorTests(unittest.TestCase):
    def test_ema_uses_standard_smoothing(self):
        values = [10.0, 11.0, 12.0, 13.0]

        result = ema(values, period=3)

        self.assertEqual(result, [10.0, 10.5, 11.25, 12.125])

    def test_rsi_returns_neutral_until_enough_data(self):
        result = rsi([10.0, 11.0, 10.0], period=14)

        self.assertEqual(result, [50.0, 50.0, 50.0])

    def test_rsi_detects_strong_uptrend(self):
        values = [float(v) for v in range(1, 18)]

        result = rsi(values, period=14)

        self.assertEqual(result[:14], [50.0] * 14)
        self.assertEqual(result[-1], 100.0)

    def test_keltner_channels_use_ema_middle_and_atr_width(self):
        middle, upper, lower = keltner_channels(candles([10.0, 11.0, 12.0]), 3, 1.0)

        self.assertEqual(middle, [10.0, 10.5, 11.25])
        self.assertEqual(upper, [12.0, 12.5, 13.25])
        self.assertEqual(lower, [8.0, 8.5, 9.25])

    def test_commodity_channel_index_is_positive_above_typical_average(self):
        result = commodity_channel_index(candles([10.0, 10.0, 13.0]), period=3)

        self.assertEqual(result[:2], [0.0, 0.0])
        self.assertAlmostEqual(result[-1], 100.0)

    def test_williams_r_reports_close_position_in_recent_range(self):
        result = williams_r(candles([10.0, 11.0, 12.0]), period=3)

        self.assertEqual(result[:2], [-50.0, -33.33333333333333])
        self.assertEqual(result[-1], -25.0)

    def test_on_balance_volume_accumulates_directional_volume(self):
        result = on_balance_volume(candles([10.0, 11.0, 10.0, 12.0], [100, 120, 80, 150]))

        self.assertEqual(result, [0.0, 120.0, 40.0, 190.0])

    def test_rolling_volume_mean_averages_recent_candle_volume(self):
        result = rolling_volume_mean(candles([10.0, 11.0, 12.0], [100, 200, 500]), 2)

        self.assertEqual(result, [100.0, 150.0, 350.0])

    def test_bollinger_width_returns_relative_band_width(self):
        result = bollinger_width([12.0, 15.0], [8.0, 5.0], [10.0, 10.0])

        self.assertEqual(result, [0.4, 1.0])


if __name__ == "__main__":
    unittest.main()
