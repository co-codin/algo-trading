import unittest
from unittest.mock import patch

from algo_trading import jobs


class BackgroundJobTests(unittest.TestCase):
    def test_refresh_historical_csvs_returns_service_summary(self):
        class FakeHistoricalCsvService:
            def refresh_all(self):
                return {"discovered": 2, "refreshed": 2, "pruned": 1, "failed": 0}

        with patch(
            "algo_trading.jobs.HistoricalCsvRefreshService",
            return_value=FakeHistoricalCsvService(),
        ):
            result = jobs.refresh_historical_csvs()

        self.assertEqual(result["refreshed"], 2)
        self.assertEqual(result["pruned"], 1)

    def test_prune_historical_csvs_returns_service_summary(self):
        class FakeHistoricalCsvService:
            def prune_all(self):
                return {"discovered": 3, "pruned": 2, "failed": 0}

        with patch(
            "algo_trading.jobs.HistoricalCsvRefreshService",
            return_value=FakeHistoricalCsvService(),
        ):
            result = jobs.prune_historical_csvs()

        self.assertEqual(result["discovered"], 3)
        self.assertEqual(result["pruned"], 2)

    def test_refresh_market_breadth_returns_service_summary(self):
        class FakeMarketBreadthService:
            def refresh_default_symbols(self):
                return {"requested": 16, "refreshed": 16, "failed": 0}

        with patch(
            "algo_trading.jobs.MarketBreadthService",
            return_value=FakeMarketBreadthService(),
        ):
            result = jobs.refresh_market_breadth()

        self.assertEqual(result["requested"], 16)
        self.assertEqual(result["failed"], 0)

    def test_refresh_futoi_returns_service_summary(self):
        class FakeFutoiRefreshService:
            def refresh_daily(self):
                return {"requested": 1, "refreshed": 1, "records": 10, "failed": 0, "skipped": 0}

        with patch(
            "algo_trading.jobs.FutoiRefreshService",
            return_value=FakeFutoiRefreshService(),
        ):
            result = jobs.refresh_futoi()

        self.assertEqual(result["records"], 10)
        self.assertEqual(result["skipped"], 0)

    def test_prune_futoi_returns_service_summary(self):
        class FakeFutoiRefreshService:
            def prune_history(self):
                return {"retention_days": 730, "store_deleted": 2, "csv_deleted": 2, "failed": 0}

        with patch(
            "algo_trading.jobs.FutoiRefreshService",
            return_value=FakeFutoiRefreshService(),
        ):
            result = jobs.prune_futoi()

        self.assertEqual(result["retention_days"], 730)
        self.assertEqual(result["store_deleted"], 2)

    def test_deactivate_expired_users_uses_configured_store(self):
        class FakeAuthStore:
            def __init__(self) -> None:
                self.schema_ready = False

            def ensure_schema(self) -> None:
                self.schema_ready = True

            def deactivate_expired_users(self) -> int:
                if not self.schema_ready:
                    raise AssertionError("schema was not initialized")
                return 4

        store = FakeAuthStore()
        with patch("algo_trading.jobs.auth_store_from_env", return_value=store):
            result = jobs.deactivate_expired_users()

        self.assertEqual(result, {"deactivated": 4})


if __name__ == "__main__":
    unittest.main()
