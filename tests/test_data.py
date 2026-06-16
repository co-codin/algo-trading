import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from algo_trading.data import (
    BinanceMarketDataClient,
    MoexSharesMarketDataClient,
    YahooFuturesMarketDataClient,
    _candle_from_kline,
    load_candles_from_csv,
    write_candles_to_csv,
)
from algo_trading.models import Candle


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class DataTests(unittest.TestCase):
    def test_write_candles_to_csv_retains_only_latest_one_year(self):
        day_ms = 24 * 60 * 60 * 1000
        latest = int(datetime(2026, 6, 16, tzinfo=timezone.utc).timestamp() * 1000)
        candles = [
            _candle(latest - (366 * day_ms), 10.0),
            _candle(latest - (365 * day_ms), 11.0),
            _candle(latest, 12.0),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "BTCUSDT-1d-365d.csv"

            write_candles_to_csv(candles, path)
            saved = load_candles_from_csv(path)

        self.assertEqual(
            [candle.open_time for candle in saved],
            [latest - (365 * day_ms), latest],
        )

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

    def test_yahoo_futures_client_maps_nasdaq_alias_to_yahoo_symbol(self):
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
                                            "open": [15000.0],
                                            "high": [15005.0],
                                            "low": [14999.0],
                                            "close": [15003.0],
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

        YahooFuturesMarketDataClient(opener=opener).get_klines("nasdaq", "1d", 1)

        self.assertIn("NQ%3DF", requests[0].full_url)

    def test_yahoo_futures_client_maps_commodity_aliases(self):
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
                                            "open": [100.0],
                                            "high": [101.0],
                                            "low": [99.0],
                                            "close": [100.5],
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

        client = YahooFuturesMarketDataClient(opener=opener)
        for symbol in ("gold", "silver", "naturalgas", "brent", "platinum", "palladium", "copper"):
            client.get_klines(symbol, "1d", 1)

        requested_urls = [request.full_url for request in requests]
        for encoded_symbol in ("GC%3DF", "SI%3DF", "NG%3DF", "BZ%3DF", "PL%3DF", "PA%3DF", "HG%3DF"):
            self.assertTrue(
                any(encoded_symbol in url for url in requested_urls),
                msg=f"missing {encoded_symbol}",
            )

    def test_yahoo_historical_klines_uses_period_window(self):
        requests = []
        start_time = 1_700_000_000_000
        end_time = start_time + (2 * 24 * 60 * 60 * 1000)

        def opener(request, timeout):
            requests.append(request)
            return FakeResponse(
                {
                    "chart": {
                        "result": [
                            {
                                "timestamp": [1_700_000_000, 1_700_086_400],
                                "indicators": {
                                    "quote": [
                                        {
                                            "open": [5000.0, 5002.0],
                                            "high": [5005.0, 5008.0],
                                            "low": [4999.0, 5001.0],
                                            "close": [5003.0, 5006.0],
                                            "volume": [100, 125],
                                        }
                                    ]
                                },
                            }
                        ],
                        "error": None,
                    }
                }
            )

        candles = YahooFuturesMarketDataClient(opener=opener).get_historical_klines(
            "sp500",
            "1d",
            start_time,
            end_time,
            limit=1000,
        )

        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].open_time, start_time)
        query = parse_qs(urlparse(requests[0].full_url).query)
        self.assertIn("ES%3DF", requests[0].full_url)
        self.assertEqual(query["interval"], ["1d"])
        self.assertEqual(query["period1"], [str(start_time // 1000)])
        self.assertEqual(query["period2"], [str(end_time // 1000)])

    def test_yahoo_client_skips_malformed_daily_quote_rows(self):
        def opener(request, timeout):
            return FakeResponse(
                {
                    "chart": {
                        "result": [
                            {
                                "timestamp": [1_700_000_000, 1_700_086_400],
                                "indicators": {
                                    "quote": [
                                        {
                                            "open": [7480.0, 5000.0],
                                            "high": [7619.0, 5005.0],
                                            "low": [7542.0, 4999.0],
                                            "close": [7617.5, 5003.0],
                                            "volume": [453504, 100],
                                        }
                                    ]
                                },
                            }
                        ],
                        "error": None,
                    }
                }
            )

        candles = YahooFuturesMarketDataClient(opener=opener).get_klines("SP500", "1d", 10)

        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0].open_time, 1_700_086_400_000)
        self.assertEqual(candles[0].close, 5003.0)

    def test_binance_historical_klines_paginates_by_time_window(self):
        hour_ms = 60 * 60 * 1000
        requests: list[str] = []
        pages = {
            "0": [_binance_kline(0), _binance_kline(hour_ms)],
            str(2 * hour_ms): [
                _binance_kline(2 * hour_ms),
                _binance_kline(3 * hour_ms),
            ],
        }

        def opener(url: str, timeout: int):
            requests.append(url)
            query = parse_qs(urlparse(url).query)
            return FakeResponse(pages[query["startTime"][0]])

        client = BinanceMarketDataClient(opener=opener)

        candles = client.get_historical_klines(
            "btcusdt",
            "1h",
            start_time=0,
            end_time=4 * hour_ms,
            limit=2,
        )

        self.assertEqual(
            [candle.open_time for candle in candles],
            [0, hour_ms, 2 * hour_ms, 3 * hour_ms],
        )
        self.assertEqual(len(requests), 2)
        first_query = parse_qs(urlparse(requests[0]).query)
        second_query = parse_qs(urlparse(requests[1]).query)
        self.assertEqual(first_query["symbol"], ["BTCUSDT"])
        self.assertEqual(first_query["interval"], ["1h"])
        self.assertEqual(first_query["limit"], ["2"])
        self.assertEqual(first_query["startTime"], ["0"])
        self.assertEqual(first_query["endTime"], [str(4 * hour_ms)])
        self.assertEqual(second_query["startTime"], [str(2 * hour_ms)])

    def test_moex_shares_client_parses_bluechip_iss_candles(self):
        requests = []

        def opener(url: str, timeout: int):
            requests.append(url)
            return FakeResponse(
                {
                    "candles": {
                        "columns": [
                            "begin",
                            "end",
                            "open",
                            "close",
                            "high",
                            "low",
                            "value",
                            "volume",
                        ],
                        "data": [
                            [
                                "2026-06-15 10:00:00",
                                "2026-06-15 10:04:59",
                                300.0,
                                301.0,
                                302.0,
                                299.0,
                                1000000.0,
                                1000,
                            ],
                            [
                                "2026-06-15 10:05:00",
                                "2026-06-15 10:09:59",
                                301.0,
                                303.0,
                                304.0,
                                300.0,
                                2000000.0,
                                1500,
                            ],
                        ],
                    }
                }
            )

        candles = MoexSharesMarketDataClient(opener=opener).get_klines("sber", "5m", 2)

        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].open, 300.0)
        self.assertEqual(candles[1].close, 303.0)
        self.assertEqual(candles[1].volume, 1500.0)
        request_url = requests[0]
        self.assertIn("/engines/stock/markets/shares/boards/TQBR/securities/SBER/candles.json", request_url)
        self.assertIn("interval=1", request_url)

    def test_moex_shares_client_requests_latest_live_page(self):
        requests = []

        def opener(url: str, timeout: int):
            requests.append(url)
            return FakeResponse(
                {
                    "candles": {
                        "columns": ["begin", "open", "high", "low", "close", "volume"],
                        "data": [
                            ["2026-06-16 12:03:00", 303, 304, 302, 303.5, 100],
                            ["2026-06-16 12:02:00", 302, 303, 301, 302.5, 90],
                            ["2026-06-16 12:01:00", 301, 302, 300, 301.5, 80],
                        ],
                    }
                }
            )

        candles = MoexSharesMarketDataClient(opener=opener).get_klines("SBER", "1m", 2)

        query = parse_qs(urlparse(requests[0]).query)
        self.assertEqual(query["iss.reverse"], ["true"])
        self.assertEqual(
            [datetime.fromtimestamp(candle.open_time / 1000, tz=timezone.utc) for candle in candles],
            [
                datetime(2026, 6, 16, 12, 2, tzinfo=timezone.utc),
                datetime(2026, 6, 16, 12, 3, tzinfo=timezone.utc),
            ],
        )

    def test_moex_client_routes_imoex_to_index_board(self):
        requests = []

        def opener(url: str, timeout: int):
            requests.append(url)
            return FakeResponse(
                {
                    "candles": {
                        "columns": ["open", "close", "high", "low", "value", "volume", "begin", "end"],
                        "data": [["2540.0", "2541.0", "2542.0", "2539.0", "100000", "0", "2026-06-16 12:00:00", "2026-06-16 12:04:59"]],
                    }
                }
            )

        candles = MoexSharesMarketDataClient(opener=opener).get_klines("IMOEX", "5m", 1)

        self.assertEqual(len(candles), 1)
        self.assertIn("/engines/stock/markets/index/boards/SNDX/securities/IMOEX/candles.json", requests[0])
        self.assertIn("iss.reverse=true", requests[0])

    def test_moex_shares_client_rejects_unsupported_symbols(self):
        with self.assertRaisesRegex(ValueError, "unsupported MOEX bluechip symbol"):
            MoexSharesMarketDataClient().get_klines("PENNY", "5m", 1)

    def test_moex_shares_client_sends_optional_bearer_token(self):
        requests = []

        def opener(request, timeout):
            requests.append(request)
            return FakeResponse(
                {
                    "candles": {
                        "columns": ["begin", "open", "high", "low", "close", "volume"],
                        "data": [["2026-06-15 10:00:00", 300, 302, 299, 301, 1000]],
                    }
                }
            )

        MoexSharesMarketDataClient(opener=opener, api_key="fake-token").get_klines(
            "SBER",
            "1d",
            1,
        )

        self.assertEqual(requests[0].get_header("Authorization"), "Bearer fake-token")
        self.assertTrue(requests[0].full_url.startswith("https://apim.moex.com/iss/"))

    def test_moex_shares_client_fetches_historical_window(self):
        requests = []

        def opener(request, timeout):
            requests.append(request)
            return FakeResponse(
                {
                    "candles": {
                        "columns": ["begin", "open", "high", "low", "close", "volume"],
                        "data": [
                            ["2025-06-16 00:00:00", 300, 302, 299, 301, 1000],
                            ["2026-06-15 00:00:00", 301, 303, 300, 302, 1500],
                        ],
                    }
                }
            )

        start_time = int(datetime(2025, 6, 16, tzinfo=timezone.utc).timestamp() * 1000)
        end_time = int(datetime(2026, 6, 16, tzinfo=timezone.utc).timestamp() * 1000)

        candles = MoexSharesMarketDataClient(opener=opener).get_historical_klines(
            "TATN",
            "1d",
            start_time,
            end_time,
            1000,
        )

        request_url = requests[0]
        query = parse_qs(urlparse(request_url).query)
        self.assertIn("/securities/TATN/candles.json", request_url)
        self.assertEqual(query["from"], ["2025-06-16"])
        self.assertEqual(query["till"], ["2026-06-16"])
        self.assertEqual(query["interval"], ["24"])
        self.assertEqual(len(candles), 2)

def _binance_kline(open_time: int) -> list[object]:
    return [
        open_time,
        "10",
        "11",
        "9",
        "10",
        "1",
        open_time + 1,
        "0",
        0,
        "0",
        "0",
        "0",
    ]


def _candle(open_time: int, close: float) -> Candle:
    return Candle(
        open_time=open_time,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1.0,
    )


if __name__ == "__main__":
    unittest.main()
