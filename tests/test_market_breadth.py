import os
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

from algo_trading.market_breadth import (
    ALLOWED_MARKET_BREADTH_SYMBOLS,
    MARKET_BREADTH_GROUPS,
    PUT_CALL_SYMBOL,
    MarketBreadthService,
    market_breadth_payload,
    parse_barchart_csv,
    parse_cboe_put_call_csvs,
)


CSV_BODY = b"""symbol,date,open,high,low,close,volume
$S5FD,2025-01-02,45,55,40,52,100
$S5FD,2025-01-03,52,58,51,56,110
$S5FD,2025-01-03,53,59,52,57,111
"""

CBOE_RATIO_ARCHIVE = b""""DATE","TOTAL VOLUME P/C RATIO","INDEX P/C RATIO","EQUITY P/C RATIO"
9/27/1995,0.79,,,
12/31/2003,1.25,2.96,0.95
"""
CBOE_TOTAL_ARCHIVE = b"""Trade_date,Call,Put,Total,P/C Ratio
10/17/2003,1152086,733258,1885344,0.64
11/1/2006,100,90,190,0.90
"""
CBOE_TOTAL_RECENT = b"""DATE,CALLS,PUTS,TOTAL,P/C Ratio
11/1/2006,1401036,1271445,2672481,0.91
10/04/2019,2175006,2289715,4464721,1.05
"""


def cboe_daily_page(
    selected_date: str,
    ratio: str,
    *,
    call: int = 100,
    put: int = 90,
    total: int = 190,
    prev_trading_day: str | None = None,
) -> bytes:
    prev_trading_day = prev_trading_day or selected_date
    return f'''
        <script>
        self.__next_f.push([1, "24:[\\"$\\",\\"$L32\\",null,{{\\"data\\":{{
          \\"optionsData\\":{{
            \\"ratios\\":[{{\\"name\\":\\"TOTAL PUT/CALL RATIO\\",\\"value\\":\\"{ratio}\\"}}],
            \\"SUM OF ALL PRODUCTS\\":[{{\\"name\\":\\"VOLUME\\",\\"call\\":{call},\\"put\\":{put},\\"total\\":{total}}}]
          }},
          \\"selectedDate\\":\\"{selected_date}\\",
          \\"minDate\\":\\"2019-10-07\\",
          \\"prevTradingDay\\":\\"{prev_trading_day}\\"
        }}}}]"]);
        </script>
    '''.encode()


class FakeBreadthClient:
    def __init__(self, bodies: dict[str, bytes]) -> None:
        self.bodies = bodies
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def fetch_csv(
        self,
        symbol: str,
        overrides: dict[str, str] | None = None,
    ) -> bytes:
        self.calls.append((symbol, overrides))
        return self.bodies[symbol]


class FailingBreadthClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def fetch_csv(
        self,
        symbol: str,
        overrides: dict[str, str] | None = None,
    ) -> bytes:
        self.calls.append((symbol, overrides))
        raise RuntimeError("Barchart unavailable")


class FakePutCallClient:
    def __init__(
        self,
        historical_bodies: list[bytes] | None = None,
        daily_pages: dict[object, bytes] | None = None,
    ) -> None:
        self.historical_bodies = historical_bodies or [
            CBOE_RATIO_ARCHIVE,
            CBOE_TOTAL_ARCHIVE,
            CBOE_TOTAL_RECENT,
        ]
        self.daily_pages = daily_pages or {}
        self.historical_calls = 0
        self.daily_calls: list[object] = []
        self.backfill_dates: list[object] = []

    def fetch_historical_csvs(self) -> list[bytes]:
        self.historical_calls += 1
        return self.historical_bodies

    def fetch_daily_page(self, trading_date=None) -> bytes:
        self.daily_calls.append(trading_date)
        return self.daily_pages[trading_date]

    def fetch_daily_pages(self, trading_dates):
        self.backfill_dates.extend(trading_dates)
        return {
            trading_date: self.daily_pages[trading_date]
            for trading_date in trading_dates
            if trading_date in self.daily_pages
        }


class FailingDailyPutCallClient(FakePutCallClient):
    def fetch_daily_page(self, trading_date=None) -> bytes:
        self.daily_calls.append(trading_date)
        raise RuntimeError("Cboe daily page unavailable")

    def fetch_daily_pages(self, trading_dates):
        self.backfill_dates.extend(trading_dates)
        raise RuntimeError("Cboe daily page unavailable")


class MarketBreadthTests(unittest.TestCase):
    def test_catalog_includes_barchart_reference_matrix_and_put_call(self):
        self.assertIn("$S5FD", ALLOWED_MARKET_BREADTH_SYMBOLS)
        self.assertIn("$NDFD", ALLOWED_MARKET_BREADTH_SYMBOLS)
        self.assertIn("$NCFD", ALLOWED_MARKET_BREADTH_SYMBOLS)
        self.assertEqual(PUT_CALL_SYMBOL, "$CPC")

        group_names = [group["name"] for group in MARKET_BREADTH_GROUPS]
        self.assertEqual(group_names, ["S&P 500", "Nasdaq 100", "NYSE"])
        first_symbols = [
            group["items"][0]["symbol"] for group in MARKET_BREADTH_GROUPS
        ]
        self.assertEqual(first_symbols, ["$S5FD", "$NDFD", "$NCFD"])
        self.assertTrue(
            all(len(group["items"]) == 5 for group in MARKET_BREADTH_GROUPS)
        )

    def test_parse_barchart_csv_keeps_latest_duplicate_date(self):
        bars = parse_barchart_csv(CSV_BODY)

        self.assertEqual([bar.date.isoformat() for bar in bars], ["2025-01-02", "2025-01-03"])
        self.assertEqual(bars[-1].close, 57.0)
        self.assertEqual(bars[-1].volume, 111.0)

    def test_parse_cboe_put_call_csvs_merges_all_official_history(self):
        bars = parse_cboe_put_call_csvs(
            [CBOE_RATIO_ARCHIVE, CBOE_TOTAL_ARCHIVE, CBOE_TOTAL_RECENT]
        )

        self.assertEqual(
            [bar.date.isoformat() for bar in bars],
            ["1995-09-27", "2003-10-17", "2003-12-31", "2006-11-01", "2019-10-04"],
        )
        self.assertTrue(all(bar.symbol == PUT_CALL_SYMBOL for bar in bars))
        self.assertEqual(bars[0].close, 0.79)
        self.assertEqual(bars[0].volume, 0.0)
        self.assertEqual(bars[1].volume, 1885344.0)
        self.assertEqual(bars[3].close, 0.91)
        self.assertEqual(bars[3].volume, 2672481.0)

    def test_payload_fetches_selected_symbols_and_converts_dates_to_chart_time(self):
        fake_client = FakeBreadthClient(
            {
                "$S5FD": CSV_BODY,
                "$CPC": b"""symbol,date,open,high,low,close,volume
$CPC,2025-01-03,0.8,0.9,0.7,0.85,0
""",
            }
        )
        service = MarketBreadthService(
            client=fake_client,
            put_call_client=FakePutCallClient(
                daily_pages={
                    None: cboe_daily_page(
                        "2019-10-07",
                        "1.05",
                        prev_trading_day="2019-10-07",
                    )
                },
            ),
            ttl_seconds=60,
            data_dir=None,
        )

        payload = market_breadth_payload(service, symbols=["$S5FD", "$CPC"])

        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["source"], "Barchart + Cboe")
        self.assertIn("$S5FD", payload["series"])
        self.assertIn("$CPC", payload["series"])
        self.assertEqual(payload["series"]["$S5FD"]["candles"][-1]["time"], 1735862400)
        self.assertEqual(payload["series"]["$S5FD"]["candles"][-1]["close"], 57.0)
        self.assertEqual(payload["series"]["$CPC"]["data"], "daily")
        self.assertEqual(payload["series"]["$CPC"]["source"], "Cboe")
        self.assertEqual(payload["series"]["$CPC"]["candles"][0]["date"], "1995-09-27")
        self.assertEqual(
            fake_client.calls,
            [
                ("$S5FD", {"data": "daily"}),
            ],
        )

    def test_put_call_uses_cboe_client_and_keeps_all_history_in_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            put_call_client = FakePutCallClient(
                daily_pages={
                    None: cboe_daily_page(
                        "2019-10-08",
                        "1.01",
                        call=120,
                        put=121,
                        total=241,
                        prev_trading_day="2019-10-08",
                    ),
                    date(2019, 10, 7): cboe_daily_page(
                        "2019-10-07",
                        "1.05",
                        call=110,
                        put=116,
                        total=226,
                        prev_trading_day="2019-10-08",
                    ),
                }
            )
            fake_client = FakeBreadthClient({})
            service = MarketBreadthService(
                client=fake_client,
                put_call_client=put_call_client,
                ttl_seconds=0,
                data_dir=data_dir,
                refresh_seconds=0,
                retention_days=365,
            )

            payload = market_breadth_payload(service, symbols=[PUT_CALL_SYMBOL])

            candles = payload["series"][PUT_CALL_SYMBOL]["candles"]
            cache_text = (data_dir / "CPC.csv").read_text(encoding="utf-8")
            self.assertEqual(fake_client.calls, [])
            self.assertEqual(put_call_client.historical_calls, 1)
            self.assertIn(date(2019, 10, 7), put_call_client.backfill_dates)
            self.assertEqual(candles[0]["date"], "1995-09-27")
            self.assertEqual(candles[-1]["date"], "2019-10-08")
            self.assertEqual(candles[-1]["close"], 1.01)
            self.assertIn("$CPC,1995-09-27,0.79,0.79,0.79,0.79,0.0", cache_text)
            self.assertIn("$CPC,2019-10-08,1.01,1.01,1.01,1.01,241.0", cache_text)

    def test_put_call_daily_failure_does_not_drop_post_2019_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            cache_file = data_dir / "CPC.csv"
            cache_file.write_text(
                "symbol,date,open,high,low,close,volume\n"
                "$CPC,1995-09-27,0.79,0.79,0.79,0.79,0.0\n"
                "$CPC,2026-06-15,0.89,0.89,0.89,0.89,15025339.0\n",
                encoding="utf-8",
            )
            stale_time = time.time() - 7200
            os.utime(cache_file, (stale_time, stale_time))
            service = MarketBreadthService(
                put_call_client=FailingDailyPutCallClient(),
                ttl_seconds=0,
                data_dir=data_dir,
                refresh_seconds=3600,
                retention_days=365,
            )

            bars = service.bars_for_symbol(PUT_CALL_SYMBOL)

            self.assertIn("2026-06-15", [bar.date.isoformat() for bar in bars])
            self.assertIn("2026-06-15", cache_file.read_text(encoding="utf-8"))

    def test_service_rejects_unknown_symbols(self):
        service = MarketBreadthService(
            client=FakeBreadthClient({}),
            ttl_seconds=60,
            data_dir=None,
        )

        with self.assertRaises(ValueError):
            market_breadth_payload(service, symbols=["$UNKNOWN"])

    def test_service_persists_breadth_bars_to_csv_and_reuses_fresh_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            fake_client = FakeBreadthClient({"$S5FD": CSV_BODY})
            service = MarketBreadthService(
                client=fake_client,
                ttl_seconds=0,
                data_dir=data_dir,
                refresh_seconds=3600,
            )

            first_bars = service.bars_for_symbol("$S5FD")

            cache_file = data_dir / "S5FD.csv"
            self.assertEqual([bar.close for bar in first_bars], [52.0, 57.0])
            self.assertTrue(cache_file.exists())
            self.assertEqual(
                cache_file.read_text(encoding="utf-8").splitlines()[0],
                "symbol,date,open,high,low,close,volume",
            )

            second_client = FakeBreadthClient({})
            second_service = MarketBreadthService(
                client=second_client,
                ttl_seconds=0,
                data_dir=data_dir,
                refresh_seconds=3600,
            )

            second_bars = second_service.bars_for_symbol("$S5FD")

            self.assertEqual([bar.close for bar in second_bars], [52.0, 57.0])
            self.assertEqual(second_client.calls, [])

    def test_service_refreshes_stale_csv_hourly_and_merges_new_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            cache_file = data_dir / "S5FD.csv"
            cache_file.write_text(
                "symbol,date,open,high,low,close,volume\n"
                "$S5FD,2025-01-02,45,55,40,52,100\n"
                "$S5FD,2025-01-03,52,58,51,56,110\n",
                encoding="utf-8",
            )
            stale_time = time.time() - 7200
            os.utime(cache_file, (stale_time, stale_time))
            fake_client = FakeBreadthClient(
                {
                    "$S5FD": b"""symbol,date,open,high,low,close,volume
$S5FD,2025-01-03,53,59,52,57,111
$S5FD,2025-01-04,57,62,56,60,120
"""
                }
            )
            service = MarketBreadthService(
                client=fake_client,
                ttl_seconds=0,
                data_dir=data_dir,
                refresh_seconds=3600,
            )

            bars = service.bars_for_symbol("$S5FD")

            self.assertEqual(
                fake_client.calls,
                [("$S5FD", {"data": "daily"})],
            )
            self.assertEqual(
                [bar.date.isoformat() for bar in bars],
                ["2025-01-02", "2025-01-03", "2025-01-04"],
            )
            self.assertEqual([bar.close for bar in bars], [52.0, 57.0, 60.0])
            saved_lines = cache_file.read_text(encoding="utf-8").splitlines()
            self.assertIn("$S5FD,2025-01-04,57.0,62.0,56.0,60.0,120.0", saved_lines)

    def test_service_retains_only_latest_one_year_when_rewriting_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            cache_file = data_dir / "S5FD.csv"
            cache_file.write_text(
                "symbol,date,open,high,low,close,volume\n"
                "$S5FD,2025-06-15,40,45,39,41,90\n"
                "$S5FD,2025-06-16,45,55,40,52,100\n",
                encoding="utf-8",
            )
            stale_time = time.time() - 7200
            os.utime(cache_file, (stale_time, stale_time))
            fake_client = FakeBreadthClient(
                {
                    "$S5FD": b"""symbol,date,open,high,low,close,volume
$S5FD,2026-06-16,57,62,56,60,120
"""
                }
            )
            service = MarketBreadthService(
                client=fake_client,
                ttl_seconds=0,
                data_dir=data_dir,
                refresh_seconds=3600,
            )

            bars = service.bars_for_symbol("$S5FD")

            self.assertEqual(
                [bar.date.isoformat() for bar in bars],
                ["2025-06-16", "2026-06-16"],
            )
            saved_text = cache_file.read_text(encoding="utf-8")
            self.assertNotIn("2025-06-15", saved_text)
            self.assertIn("2026-06-16", saved_text)

    def test_service_serves_saved_csv_when_hourly_refresh_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            cache_file = data_dir / "S5FD.csv"
            cache_file.write_text(
                "symbol,date,open,high,low,close,volume\n"
                "$S5FD,2025-01-02,45,55,40,52,100\n",
                encoding="utf-8",
            )
            stale_time = time.time() - 7200
            os.utime(cache_file, (stale_time, stale_time))
            failing_client = FailingBreadthClient()
            service = MarketBreadthService(
                client=failing_client,
                ttl_seconds=0,
                data_dir=data_dir,
                refresh_seconds=3600,
            )

            bars = service.bars_for_symbol("$S5FD")

            self.assertEqual(
                failing_client.calls,
                [("$S5FD", {"data": "daily"})],
            )
            self.assertEqual([bar.date.isoformat() for bar in bars], ["2025-01-02"])
            self.assertEqual(bars[0].close, 52.0)


if __name__ == "__main__":
    unittest.main()
