import unittest

from algo_trading.data import _candle_from_kline


class DataTests(unittest.TestCase):
    def test_kline_parser_rejects_short_rows_with_clear_error(self):
        with self.assertRaisesRegex(ValueError, "kline row"):
            _candle_from_kline([1, "10"])


if __name__ == "__main__":
    unittest.main()
