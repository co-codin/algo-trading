import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from algo_trading.futoi import (
    FutoiClient,
    FutoiCsvHistory,
    FutoiInstrument,
    FutoiRecord,
    FutoiRefreshService,
    MissingFutoiApiKey,
    futoi_instruments_from_records,
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

        records = client.fetch_daily(date(2024, 4, 8), page_limit=1)

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
            {"date": ["2024-04-08"], "start": ["0"], "limit": ["1"]},
        )

    def test_client_fetches_ticker_detail_from_detail_endpoint(self):
        requests = []
        payloads = [
            {
                "futoi": {
                    "columns": [
                        "tradedate",
                        "tradetime",
                        "ticker",
                        "clgroup",
                        "pos",
                        "pos_long",
                        "pos_short",
                        "pos_long_num",
                        "pos_short_num",
                    ],
                    "data": [
                        [
                            "2024-04-08",
                            "18:45:00",
                            "IMOEXF",
                            "FIZ",
                            19,
                            232,
                            -213,
                            24,
                            18,
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

        records = client.fetch_ticker(
            "imoexf",
            start_date=date(2024, 4, 1),
            end_date=date(2024, 4, 8),
            page_limit=1000,
        )

        self.assertEqual([record.ticker for record in records], ["IMOEXF"])
        parsed = urlparse(requests[0][0].full_url)
        self.assertEqual(parsed.path, "/iss/analyticalproducts/futoi/securities/IMOEXF.json")
        self.assertEqual(
            parse_qs(parsed.query),
            {
                "from": ["2024-04-01"],
                "till": ["2024-04-08"],
                "start": ["0"],
                "limit": ["1000"],
            },
        )

    def test_client_fetches_latest_from_one_current_feed_page(self):
        requests = []
        payload = _futoi_payload("2024-04-08", "IMOEXF", "YUR", -19)

        def fake_opener(request, timeout):
            requests.append(request)
            return _FakeResponse(payload)

        client = FutoiClient(
            api_key="futoi-token",
            base_url="https://example.moex/iss",
            opener=fake_opener,
        )

        records = client.fetch_latest(page_limit=1000)

        self.assertEqual([record.ticker for record in records], ["IMOEXF"])
        self.assertEqual(len(requests), 1)
        parsed = urlparse(requests[0].full_url)
        self.assertEqual(parsed.path, "/iss/analyticalproducts/futoi/securities.json")
        self.assertEqual(parse_qs(parsed.query), {"start": ["0"], "limit": ["1000"]})

    def test_client_stops_when_detail_page_repeats(self):
        requests = []
        payload = _futoi_payload("2024-04-08", "IMOEXF", "YUR", -19)

        def fake_opener(request, timeout):
            requests.append(request)
            return _FakeResponse(payload)

        client = FutoiClient(
            api_key="futoi-token",
            base_url="https://example.moex/iss",
            opener=fake_opener,
        )

        records = client.fetch_ticker("IMOEXF", page_limit=1)

        self.assertEqual([record.ticker for record in records], ["IMOEXF"])
        self.assertEqual(len(requests), 2)

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

    def test_refresh_service_renews_futoi_instruments_from_latest_feed(self):
        class FakeFutoiClient:
            def fetch_latest(self):
                return [
                    FutoiRecord(
                        trade_date=date(2024, 4, 8),
                        trade_time="18:45:00",
                        ticker="IMOEXF",
                        client_group="YUR",
                        position=-19.0,
                        position_long=213.0,
                        position_short=-232.0,
                        position_long_count=18,
                        position_short_count=24,
                    ),
                    FutoiRecord(
                        trade_date=date(2024, 4, 8),
                        trade_time="18:45:00",
                        ticker="IMOEXF",
                        client_group="FIZ",
                        position=19.0,
                        position_long=232.0,
                        position_short=-213.0,
                        position_long_count=24,
                        position_short_count=18,
                    ),
                    FutoiRecord(
                        trade_date=date(2024, 4, 8),
                        trade_time="18:45:00",
                        ticker="SBERF",
                        client_group="FIZ",
                        position=7.0,
                        position_long=10.0,
                        position_short=-3.0,
                        position_long_count=2,
                        position_short_count=1,
                    ),
                ]

        store = InMemoryHistoricalDataStore()
        service = FutoiRefreshService(store=store, client=FakeFutoiClient(), csv_history=None)

        summary = service.refresh_instruments()

        self.assertEqual(summary["records"], 3)
        self.assertEqual(summary["instruments"], 2)
        instruments = store.list_futoi_instruments()
        self.assertEqual([instrument.ticker for instrument in instruments], ["IMOEXF", "SBERF"])
        self.assertEqual(instruments[0].client_groups, ("FIZ", "YUR"))
        self.assertEqual(instruments[0].gross_position, 38.0)
        self.assertEqual(instruments[0].long_position, 445.0)
        self.assertEqual(instruments[0].short_position, 445.0)
        self.assertEqual(
            [record.ticker for record in store.load_futoi_records(trading_date=date(2024, 4, 8))],
            ["IMOEXF", "IMOEXF", "SBERF"],
        )

    def test_refresh_all_updates_daily_history_and_latest_instruments(self):
        class FakeFutoiClient:
            def __init__(self) -> None:
                self.daily_dates: list[date] = []
                self.latest_calls = 0

            def fetch_daily(self, trading_date):
                self.daily_dates.append(trading_date)
                return [_record_for_date(trading_date, position=10.0)]

            def fetch_latest(self):
                self.latest_calls += 1
                return [_record_for_date(date(2024, 4, 9), position=25.0)]

        store = InMemoryHistoricalDataStore()
        client = FakeFutoiClient()
        service = FutoiRefreshService(store=store, client=client, csv_history=None)

        summary = service.refresh_all(trading_date=date(2024, 4, 8))

        self.assertEqual(client.daily_dates, [date(2024, 4, 8)])
        self.assertEqual(client.latest_calls, 1)
        self.assertEqual(summary["requested"], 2)
        self.assertEqual(summary["records"], 2)
        self.assertEqual(summary["instruments"], 1)
        self.assertEqual(
            [record.trade_date for record in store.load_futoi_records(ticker="IMOEXF")],
            [date(2024, 4, 8), date(2024, 4, 9)],
        )
        self.assertEqual(store.list_futoi_instruments()[0].last_trade_date, date(2024, 4, 9))

    def test_instrument_summary_uses_only_latest_snapshot_for_ticker(self):
        instruments = futoi_instruments_from_records(
            [
                _record_for_date(date(2024, 4, 8), position=10.0),
                _record_for_date(date(2024, 4, 9), position=20.0),
            ]
        )

        self.assertEqual(len(instruments), 1)
        self.assertEqual(instruments[0].last_trade_date, date(2024, 4, 9))
        self.assertEqual(instruments[0].net_position, 20.0)
        self.assertEqual(instruments[0].gross_position, 20.0)
        self.assertEqual(instruments[0].row_count, 1)

    def test_load_ticker_history_backfills_one_year_to_store(self):
        class FakeFutoiClient:
            def __init__(self) -> None:
                self.calls: list[tuple[str, date | None, date | None]] = []

            def fetch_ticker(self, ticker, *, start_date=None, end_date=None):
                self.calls.append((ticker, start_date, end_date))
                return [
                    _record_for_date(date(2023, 6, 17), position=5.0),
                    _record_for_date(date(2023, 6, 18), position=10.0),
                    _record_for_date(date(2024, 6, 17), position=20.0),
                ]

        store = InMemoryHistoricalDataStore()
        store.upsert_futoi_records(
            [_record_for_date(date(2024, 6, 17), position=20.0)],
            source="unit-test",
        )
        client = FakeFutoiClient()
        service = FutoiRefreshService(store=store, client=client, csv_history=None)

        records = service.load_ticker_history(
            "imoexf",
            end_date=date(2024, 6, 17),
            days=365,
        )

        self.assertEqual(
            client.calls,
            [("IMOEXF", date(2023, 6, 18), date(2024, 6, 17))],
        )
        self.assertEqual(
            [record.trade_date for record in records],
            [date(2023, 6, 18), date(2024, 6, 17)],
        )
        self.assertEqual(
            [record.trade_date for record in store.load_futoi_records(ticker="IMOEXF")],
            [date(2023, 6, 17), date(2023, 6, 18), date(2024, 6, 17)],
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

    def test_csv_history_writes_lf_line_endings_for_repo_artifacts(self):
        with tempfile.TemporaryDirectory() as tempdir:
            csv_history = FutoiCsvHistory(Path(tempdir) / "futoi.csv")

            csv_history.upsert_records([_record_for_date(date(2024, 4, 8), position=10.0)])

            contents = csv_history.path.read_bytes()

        self.assertIn(b"\n", contents)
        self.assertNotIn(b"\r\n", contents)

    def test_prune_history_removes_futoi_records_older_than_retention(self):
        current_time = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
        old_record = _record_for_date(date(2024, 6, 16), position=1.0)
        cutoff_record = _record_for_date(date(2024, 6, 17), position=2.0)

        with tempfile.TemporaryDirectory() as tempdir:
            store = InMemoryHistoricalDataStore()
            store.upsert_futoi_records([old_record, cutoff_record], source="unit-test")
            store.upsert_futoi_instruments(
                [
                    FutoiInstrument(ticker="IMOEXF", last_trade_date=date(2024, 6, 16), row_count=1),
                    FutoiInstrument(ticker="SBERF", last_trade_date=date(2024, 6, 17), row_count=1),
                ],
                source="unit-test",
            )
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
            self.assertEqual(
                [instrument.ticker for instrument in store.list_futoi_instruments()],
                ["IMOEXF"],
            )
            self.assertEqual(store.list_futoi_instruments()[0].last_trade_date, date(2024, 6, 17))

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


def _futoi_payload(
    trade_date: str,
    ticker: str,
    client_group: str,
    position: float,
):
    return {
        "futoi": {
            "columns": [
                "tradedate",
                "tradetime",
                "ticker",
                "clgroup",
                "pos",
                "pos_long",
                "pos_short",
                "pos_long_num",
                "pos_short_num",
            ],
            "data": [
                [
                    trade_date,
                    "18:45:00",
                    ticker,
                    client_group,
                    position,
                    abs(position) + 1,
                    -abs(position),
                    2,
                    1,
                ]
            ],
        }
    }


if __name__ == "__main__":
    unittest.main()
