import json
import unittest
from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlparse

from algo_trading.algopack import (
    AlgoPackClient,
    AlgoPackRecord,
    AlgoPackService,
    algopack_record_time_millis,
)
from algo_trading.historical_store import InMemoryHistoricalDataStore


class AlgoPackTests(unittest.TestCase):
    def test_client_fetches_ticker_dataset_with_bearer_token(self):
        requests = []
        payload = {
            "data": {
                "columns": ["tradedate", "tradetime", "secid", "vol", "disb"],
                "data": [["2024-04-08", "10:05:00", "SBER", 100, 0.25]],
            },
        }

        def fake_opener(request, timeout):
            requests.append((request, timeout))
            return _FakeResponse(payload)

        client = AlgoPackClient(
            api_key="algopack-token",
            base_url="https://example.moex/iss",
            opener=fake_opener,
        )

        records = client.fetch_ticker(
            "russian_bluechips",
            "tradestats",
            "sber",
            start_date=date(2024, 4, 8),
            end_date=date(2024, 4, 9),
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].dataset, "tradestats")
        self.assertEqual(records[0].market, "russian_bluechips")
        self.assertEqual(records[0].ticker, "SBER")
        self.assertEqual(records[0].trade_date, date(2024, 4, 8))
        self.assertEqual(records[0].trade_time, "10:05:00")
        self.assertEqual(records[0].metrics, {"vol": 100, "disb": 0.25})
        request, timeout = requests[0]
        self.assertEqual(timeout, 20)
        self.assertEqual(request.headers["Authorization"], "Bearer algopack-token")
        parsed = urlparse(request.full_url)
        self.assertEqual(parsed.path, "/iss/datashop/algopack/eq/tradestats/SBER.json")
        self.assertEqual(
            parse_qs(parsed.query),
            {
                "from": ["2024-04-08"],
                "till": ["2024-04-09"],
                "start": ["0"],
                "limit": ["1000"],
            },
        )

    def test_service_uses_store_before_fetching_missing_records(self):
        store = InMemoryHistoricalDataStore()
        store.upsert_algopack_records(
            [
                AlgoPackRecord(
                    dataset="tradestats",
                    market="russian_bluechips",
                    ticker="SBER",
                    trade_date=date(2024, 4, 8),
                    trade_time="10:05:00",
                    metrics={"vol": 100},
                )
            ],
            source="unit-test",
        )
        client = _FakeAlgoPackClient()
        service = AlgoPackService(store=store, client=client)

        records = service.load_records(
            "russian_bluechips",
            "SBER",
            ["tradestats"],
            start_date=date(2024, 4, 8),
            end_date=date(2024, 4, 8),
        )

        self.assertEqual([record.metrics["vol"] for record in records], [100])
        self.assertEqual(client.calls, [])

    def test_service_skips_orderstats_for_futures(self):
        client = _FakeAlgoPackClient()
        service = AlgoPackService(store=InMemoryHistoricalDataStore(), client=client)

        records = service.load_records(
            "russian_indices_futures",
            "IMOEXF",
            ["tradestats", "orderstats", "obstats"],
            start_date=date(2024, 4, 8),
            end_date=date(2024, 4, 8),
        )

        self.assertEqual(records, [])
        self.assertEqual(
            [call[1] for call in client.calls],
            ["tradestats", "obstats"],
        )

    def test_algopack_record_time_millis_uses_moscow_time_bucket(self):
        record = AlgoPackRecord(
            dataset="tradestats",
            market="russian_bluechips",
            ticker="SBER",
            trade_date=date(2024, 4, 8),
            trade_time="10:05:00",
            metrics={},
        )

        self.assertEqual(
            algopack_record_time_millis(record),
            int(datetime(2024, 4, 8, 7, 5, tzinfo=timezone.utc).timestamp() * 1000),
        )


class _FakeAlgoPackClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, date | None, date | None]] = []

    def fetch_ticker(
        self,
        market: str,
        dataset: str,
        ticker: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[AlgoPackRecord]:
        self.calls.append((market, dataset, ticker, start_date, end_date))
        return []


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


if __name__ == "__main__":
    unittest.main()
