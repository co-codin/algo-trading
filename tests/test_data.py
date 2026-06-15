import json
import unittest

from algo_trading.data import YahooFuturesMarketDataClient, _candle_from_kline


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


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

    def test_yahoo_futures_client_parses_sp500_future_chart_payload(self):
        requests = []

        def opener(request, timeout):
            requests.append(request)
            return FakeResponse(
                {
                    "chart": {
                        "result": [
                            {
                                "timestamp": [1_700_000_000, 1_700_000_300, 1_700_000_600],
                                "indicators": {
                                    "quote": [
                                        {
                                            "open": [5000.0, None, 5002.0],
                                            "high": [5005.0, None, 5008.0],
                                            "low": [4999.0, None, 5001.0],
                                            "close": [5003.0, None, 5006.0],
                                            "volume": [100, None, 125],
                                        }
                                    ]
                                },
                            }
                        ],
                        "error": None,
                    }
                }
            )

        client = YahooFuturesMarketDataClient(opener=opener)

        candles = client.get_klines("ES=F", "5m", 2)

        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].open_time, 1_700_000_000_000)
        self.assertEqual(candles[1].close, 5006.0)
        self.assertIn("ES%3DF", requests[0].full_url)
        self.assertIn("interval=5m", requests[0].full_url)
        self.assertIn("range=5d", requests[0].full_url)

    def test_yahoo_futures_client_maps_hourly_interval_to_yahoo_interval(self):
        requests = []

        def opener(request, timeout):
            requests.append(request)
            return FakeResponse(
                {
                    "chart": {
                        "result": [
                            {
                                "timestamp": [1_700_000_000],
                                "indicators": {
                                    "quote": [
                                        {
                                            "open": [5000.0],
                                            "high": [5005.0],
                                            "low": [4999.0],
                                            "close": [5003.0],
                                            "volume": [100],
                                        }
                                    ]
                                },
                            }
                        ],
                        "error": None,
                    }
                }
            )

        YahooFuturesMarketDataClient(opener=opener).get_klines("ES", "1h", 1)

        self.assertIn("interval=60m", requests[0].full_url)


if __name__ == "__main__":
    unittest.main()
