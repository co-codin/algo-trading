import os
import tempfile
import time
import unittest
from pathlib import Path

from algo_trading.market_breadth import (
    ALLOWED_MARKET_BREADTH_SYMBOLS,
    MARKET_BREADTH_GROUPS,
    PUT_CALL_SYMBOL,
    MarketBreadthService,
    market_breadth_payload,
    parse_barchart_csv,
)


CSV_BODY = b"""symbol,date,open,high,low,close,volume
$S5FD,2025-01-02,45,55,40,52,100
$S5FD,2025-01-03,52,58,51,56,110
$S5FD,2025-01-03,53,59,52,57,111
"""


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
            ttl_seconds=60,
            data_dir=None,
        )

        payload = market_breadth_payload(service, symbols=["$S5FD", "$CPC"])

        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["source"], "Barchart")
        self.assertIn("$S5FD", payload["series"])
        self.assertIn("$CPC", payload["series"])
        self.assertEqual(payload["series"]["$S5FD"]["candles"][-1]["time"], 1735862400)
        self.assertEqual(payload["series"]["$S5FD"]["candles"][-1]["close"], 57.0)
        self.assertEqual(payload["series"]["$CPC"]["data"], "weekly")
        self.assertEqual(
            fake_client.calls,
            [
                ("$S5FD", {"data": "daily"}),
                ("$CPC", {"data": "weekly"}),
            ],
        )

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
