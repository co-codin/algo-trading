import unittest

from algo_trading.indicators import ema, rsi


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


if __name__ == "__main__":
    unittest.main()
