import unittest

from algo_trading.data import _candle_from_kline


class DataTests(unittest.TestCase):
    def test_kline_parser_rejects_short_rows_with_clear_error(self):
        with self.assertRaisesRegex(ValueError, "invalid kline row"):
            _candle_from_kline([1, "10"])

    def test_kline_parser_rejects_non_sequence_rows(self):
        with self.assertRaisesRegex(ValueError, "invalid kline row"):
            _candle_from_kline(1)

    def test_kline_parser_rejects_mapping_rows(self):
        with self.assertRaisesRegex(ValueError, "invalid kline row"):
            _candle_from_kline({"open_time": 1, "open": "10"})

    def test_kline_parser_rejects_text_rows(self):
        with self.assertRaisesRegex(ValueError, "invalid kline row"):
            _candle_from_kline("123456")

    def test_kline_parser_rejects_invalid_numeric_fields(self):
        with self.assertRaisesRegex(ValueError, "invalid kline row"):
            _candle_from_kline([1, "bad", "11", "9", "10", "1"])


if __name__ == "__main__":
    unittest.main()
