import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from algo_trading.futoi import (
    FutoiClient,
    FutoiCsvHistory,
    FutoiRecord,
    FutoiRefreshService,
    MissingFutoiApiKey,
)
from algo_trading.data import TransientMarketDataError
from algo_trading.historical_store import InMemoryHistoricalDataStore


class FutoiTests(unittest.TestCase):
    def test_client_fetches_daily_pages_with_bearer_token(self):
        requests = []
        payloads = [
            {
                "futoi": {
                    "columns": [
                        "sess_id",
                        "seqnum",
                        "tradedate",
                        "tradetime",
                        "ticker",
                        "clgroup",
                        "pos",
                        "pos_long",
                        "pos_short",
                        "pos_long_num",
                        "pos_short_num",
                        "systime",
                        "trade_session_date",
                    ],
                    "data": [
                        [
                            7027,
                            1,
                            "2024-04-08",
                            "18:45:00",
                            "IMOEXF",
                            "YUR",
                            -19,
                            213,
                            232,
                            18,
                            24,
                            "2024-04-08 18:45:01",
                            "2024-04-09",
                        ]
                    ],
                }
            },
            {"futoi": {"columns": ["ticker"], "data": []}},
        ]

        def fake_opener(request, timeout):
            requests.append((request, timeout))
            return _FakeResponse(payloads[len(requests) - 1])

        client = FutoiClient(
            api_key="futoi-token",
            base_url="https://example.moex/iss",
            opener=fake_opener,
        )

        records = client.fetch_daily(date(2024, 4, 8), page_limit=1000)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].trade_date, date(2024, 4, 8))
        self.assertEqual(records[0].trade_time, "18:45:00")
        self.assertEqual(records[0].ticker, "IMOEXF")
        self.assertEqual(records[0].client_group, "YUR")
        self.assertEqual(records[0].position, -19.0)
        self.assertEqual(records[0].position_long_count, 18)
        self.assertEqual(records[0].system_time, datetime(2024, 4, 8, 18, 45, 1, tzinfo=timezone.utc))
        self.assertEqual(len(requests), 2)
        first_request, first_timeout = requests[0]
        self.assertEqual(first_timeout, 20)
        self.assertEqual(first_request.headers["Authorization"], "Bearer futoi-token")
        parsed = urlparse(first_request.full_url)
        self.assertEqual(parsed.path, "/iss/analyticalproducts/futoi/securities.json")
        self.assertEqual(
            parse_qs(parsed.query),
            {"date": ["2024-04-08"], "start": ["0"], "limit": ["1000"]},
        )

    def test_refresh_service_upserts_daily_records(self):
        class FakeFutoiClient:
            def fetch_daily(self, trading_date):
                self.trading_date = trading_date
                return [
                    FutoiRecord(
                        trade_date=trading_date,
                        trade_time="18:45:00",
                        ticker="IMOEXF",
                        client_group="FIZ",
                        position=10.0,
                        position_long=12.0,
                        position_short=2.0,
                        position_long_count=3,
                        position_short_count=1,
                    )
                ]

        store = InMemoryHistoricalDataStore()
        client = FakeFutoiClient()
        service = FutoiRefreshService(store=store, client=client, csv_history=None)

        summary = service.refresh_daily(date(2024, 4, 8))

        self.assertEqual(summary, {"requested": 1, "refreshed": 1, "records": 1, "failed": 0, "skipped": 0})
        self.assertEqual(client.trading_date, date(2024, 4, 8))
        self.assertEqual(
            [record.ticker for record in store.load_futoi_records(trading_date=date(2024, 4, 8))],
            ["IMOEXF"],
        )

    def test_refresh_service_writes_deduped_csv_history(self):
        class FakeFutoiClient:
            def __init__(self) -> None:
                self.position = 10.0

            def fetch_daily(self, trading_date):
                return [
                    FutoiRecord(
                        trade_date=trading_date,
                        trade_time="18:45:00",
                        ticker="IMOEXF",
                        client_group="FIZ",
                        position=self.position,
                        position_long=12.0,
                        position_short=2.0,
                        position_long_count=3,
                        position_short_count=1,
                    )
                ]

        with tempfile.TemporaryDirectory() as tempdir:
            csv_history = FutoiCsvHistory(Path(tempdir) / "futoi.csv")
            client = FakeFutoiClient()
            service = FutoiRefreshService(
                store=InMemoryHistoricalDataStore(),
                client=client,
                csv_history=csv_history,
            )
            service.refresh_daily(date(2024, 4, 8))
            client.position = 11.0
            service.refresh_daily(date(2024, 4, 8))

            saved = csv_history.load_records(trading_date=date(2024, 4, 8), ticker="IMOEXF")

        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].position, 11.0)

    def test_prune_history_removes_futoi_records_older_than_retention(self):
        current_time = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
        old_record = _record_for_date(date(2024, 6, 16), position=1.0)
        cutoff_record = _record_for_date(date(2024, 6, 17), position=2.0)

        with tempfile.TemporaryDirectory() as tempdir:
            store = InMemoryHistoricalDataStore()
            store.upsert_futoi_records([old_record, cutoff_record], source="unit-test")
            csv_history = FutoiCsvHistory(Path(tempdir) / "futoi.csv")
            csv_history.upsert_records([old_record, cutoff_record])
            service = FutoiRefreshService(
                store=store,
                client=object(),
                csv_history=csv_history,
                now=lambda: current_time,
                retention_days=730,
            )

            summary = service.prune_history()

            self.assertEqual(
                summary,
                {"retention_days": 730, "store_deleted": 1, "csv_deleted": 1, "failed": 0},
            )
            self.assertEqual(
                [record.trade_date for record in store.load_futoi_records()],
                [date(2024, 6, 17)],
            )
            self.assertEqual(
                [record.trade_date for record in csv_history.load_records()],
                [date(2024, 6, 17)],
            )

    def test_refresh_service_skips_when_api_key_is_missing(self):
        class FakeFutoiClient:
            def fetch_daily(self, trading_date):
                raise MissingFutoiApiKey("MOEX FUTOI API key is required")

        service = FutoiRefreshService(
            store=InMemoryHistoricalDataStore(),
            client=FakeFutoiClient(),
            csv_history=None,
        )

        summary = service.refresh_daily(date(2024, 4, 8))

        self.assertEqual(summary, {"requested": 1, "refreshed": 0, "records": 0, "failed": 0, "skipped": 1})

    def test_refresh_service_reports_transient_fetch_failures(self):
        class FakeFutoiClient:
            def fetch_daily(self, trading_date):
                raise TransientMarketDataError("transient MOEX FUTOI market-data failure")

        service = FutoiRefreshService(
            store=InMemoryHistoricalDataStore(),
            client=FakeFutoiClient(),
            csv_history=None,
        )

        summary = service.refresh_daily(date(2024, 4, 8))

        self.assertEqual(summary, {"requested": 1, "refreshed": 0, "records": 0, "failed": 1, "skipped": 0})


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _record_for_date(trade_date: date, position: float) -> FutoiRecord:
    return FutoiRecord(
        trade_date=trade_date,
        trade_time="18:45:00",
        ticker="IMOEXF",
        client_group="FIZ",
        position=position,
        position_long=position,
        position_short=0.0,
        position_long_count=1,
        position_short_count=0,
    )


if __name__ == "__main__":
    unittest.main()
