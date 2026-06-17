import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from algo_trading.data import MoexSharesMarketDataClient, YahooFuturesMarketDataClient
from algo_trading.historical_data import (
    HistoricalDataRefreshService,
    historical_client_for_market,
)
from algo_trading.historical_store import InMemoryHistoricalDataStore
from algo_trading.models import Candle


class FakeHistoricalClient:
    def __init__(self, candles: list[Candle]) -> None:
        self.candles = candles
        self.requests: list[tuple[str, str, int, int, int]] = []

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        return self.candles[:limit]

    def get_24h_tickers(self) -> list[dict[str, object]]:
        return []

    def get_historical_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        limit: int,
    ) -> list[Candle]:
        self.requests.append((symbol, interval, start_time, end_time, limit))
        return self.candles


class HistoricalDataTests(unittest.TestCase):
    def test_refresh_service_updates_tracked_db_series_and_keeps_three_years(self):
        day_ms = 24 * 60 * 60 * 1000
        now = int(datetime(2026, 6, 16, tzinfo=timezone.utc).timestamp() * 1000)
        store = InMemoryHistoricalDataStore()
        store.upsert_candles(
            "crypto_spot",
            "BTCUSDT",
            "1d",
            [_candle(now - (1096 * day_ms), 9.0)],
            source="seed",
        )
        client = FakeHistoricalClient(
            [
                _candle(now - (1096 * day_ms), 10.0),
                _candle(now - (1095 * day_ms), 11.0),
                _candle(now, 12.0),
            ]
        )
        service = HistoricalDataRefreshService(
            store=store,
            client_factory=lambda _market: client,
            now=lambda: datetime(2026, 6, 16, tzinfo=timezone.utc),
        )

        summary = service.refresh_all()
        stored = store.load_candles("crypto_spot", "BTCUSDT", "1d")

        self.assertEqual(summary["discovered"], 1)
        self.assertEqual(summary["refreshed"], 1)
        self.assertGreaterEqual(summary["pruned"], 1)
        self.assertEqual(client.requests[0][0:2], ("BTCUSDT", "1d"))
        self.assertEqual(client.requests[0][2], now - (1095 * day_ms))
        self.assertEqual(
            [candle.open_time for candle in stored],
            [now - (1095 * day_ms), now],
        )

    def test_prune_all_deletes_old_db_candles_from_all_series(self):
        day_ms = 24 * 60 * 60 * 1000
        now = int(datetime(2026, 6, 16, tzinfo=timezone.utc).timestamp() * 1000)
        store = InMemoryHistoricalDataStore()
        store.upsert_candles(
            "crypto_spot",
            "BTCUSDT",
            "1d",
            [
                _candle(now - (1096 * day_ms), 9.0),
                _candle(now - (1095 * day_ms), 10.0),
            ],
            source="seed",
        )
        service = HistoricalDataRefreshService(
            store=store,
            client_factory=lambda _market: FakeHistoricalClient([]),
            now=lambda: datetime(2026, 6, 16, tzinfo=timezone.utc),
        )

        summary = service.prune_all()

        self.assertEqual(summary["discovered"], 1)
        self.assertEqual(summary["pruned"], 1)
        self.assertEqual(
            [candle.open_time for candle in store.load_candles("crypto_spot", "BTCUSDT", "1d")],
            [now - (1095 * day_ms)],
        )

    def test_refresh_service_imports_legacy_csv_then_refreshes_tracked_series(self):
        day_ms = 24 * 60 * 60 * 1000
        now = int(datetime(2026, 6, 16, tzinfo=timezone.utc).timestamp() * 1000)
        store = InMemoryHistoricalDataStore()
        client = FakeHistoricalClient(
            [
                _candle(now - (1096 * day_ms), 10.0),
                _candle(now - (1095 * day_ms), 11.0),
                _candle(now, 12.0),
            ]
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "BTCUSDT-1d-1095d.csv"
            path.write_text(
                "open_time,open,high,low,close,volume\n"
                f"{now - (1096 * day_ms)},10,11,9,10,1\n",
                encoding="utf-8",
            )
            service = HistoricalDataRefreshService(
                data_dir=Path(tmp),
                client_factory=lambda _market: client,
                now=lambda: datetime(2026, 6, 16, tzinfo=timezone.utc),
                store=store,
                import_legacy_csv=True,
            )

            summary = service.refresh_all()

        self.assertEqual(summary["refreshed"], 1)
        self.assertEqual(client.requests[0][0:2], ("BTCUSDT", "1d"))
        self.assertEqual(client.requests[0][2], now - (1095 * day_ms))
        self.assertEqual(
            [candle.open_time for candle in store.load_candles("crypto_spot", "BTCUSDT", "1d")],
            [now - (1095 * day_ms), now],
        )

    def test_prune_all_uses_current_clock_for_three_year_cutoff(self):
        day_ms = 24 * 60 * 60 * 1000
        now = int(datetime(2026, 6, 16, tzinfo=timezone.utc).timestamp() * 1000)
        store = InMemoryHistoricalDataStore()
        store.upsert_candles(
            "crypto_spot",
            "BTCUSDT",
            "1d",
            [
                _candle(now - (1096 * day_ms), 10.0),
                _candle(now - (1095 * day_ms), 11.0),
            ],
            source="seed",
        )
        service = HistoricalDataRefreshService(
            store=store,
            client_factory=lambda _market: FakeHistoricalClient([]),
            now=lambda: datetime(2026, 6, 16, tzinfo=timezone.utc),
        )

        summary = service.prune_all()

        self.assertEqual(summary["pruned"], 1)
        self.assertEqual(
            [candle.open_time for candle in store.load_candles("crypto_spot", "BTCUSDT", "1d")],
            [now - (1095 * day_ms)],
        )

    def test_refresh_service_infers_mag7_stock_market_from_symbol_and_directory(self):
        now = int(datetime(2026, 6, 16, tzinfo=timezone.utc).timestamp() * 1000)
        markets: list[str] = []
        store = InMemoryHistoricalDataStore()

        def client_factory(market: str) -> FakeHistoricalClient:
            markets.append(market)
            return FakeHistoricalClient([_candle(now, 12.0)])

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "AAPL-1d.csv").write_text(
                "open_time,open,high,low,close,volume\n"
                f"{now},12,13,11,12,1\n",
                encoding="utf-8",
            )
            mag7_dir = base / "mag7_stocks"
            mag7_dir.mkdir()
            (mag7_dir / "MSFT-1d.csv").write_text(
                "open_time,open,high,low,close,volume\n"
                f"{now},13,14,12,13,1\n",
                encoding="utf-8",
            )
            service = HistoricalDataRefreshService(
                data_dir=base,
                client_factory=client_factory,
                now=lambda: datetime(2026, 6, 16, tzinfo=timezone.utc),
                store=store,
                import_legacy_csv=True,
            )

            summary = service.refresh_all()

        self.assertEqual(summary["refreshed"], 2)
        self.assertEqual(markets, ["mag7_stocks", "mag7_stocks"])

    def test_refresh_service_infers_hong_kong_stock_market_from_symbol_and_directory(self):
        now = int(datetime(2026, 6, 16, tzinfo=timezone.utc).timestamp() * 1000)
        markets: list[str] = []
        store = InMemoryHistoricalDataStore()

        def client_factory(market: str) -> FakeHistoricalClient:
            markets.append(market)
            return FakeHistoricalClient([_candle(now, 108.0)])

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "9988.HK-1d.csv").write_text(
                "open_time,open,high,low,close,volume\n"
                f"{now},108,109,107,108,1\n",
                encoding="utf-8",
            )
            hk_dir = base / "hong_kong_stocks"
            hk_dir.mkdir()
            (hk_dir / "9888.HK-1d.csv").write_text(
                "open_time,open,high,low,close,volume\n"
                f"{now},110,111,109,110,1\n",
                encoding="utf-8",
            )
            service = HistoricalDataRefreshService(
                data_dir=base,
                client_factory=client_factory,
                now=lambda: datetime(2026, 6, 16, tzinfo=timezone.utc),
                store=store,
                import_legacy_csv=True,
            )

            summary = service.refresh_all()

        self.assertEqual(summary["refreshed"], 2)
        self.assertEqual(markets, ["hong_kong_stocks", "hong_kong_stocks"])

    def test_refresh_service_infers_moex_index_and_futures_markets(self):
        now = int(datetime(2026, 6, 16, tzinfo=timezone.utc).timestamp() * 1000)
        markets: list[str] = []
        store = InMemoryHistoricalDataStore()

        def client_factory(market: str) -> FakeHistoricalClient:
            markets.append(market)
            return FakeHistoricalClient([_candle(now, 12.0)])

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "IMOEX-1d.csv").write_text(
                "open_time,open,high,low,close,volume\n"
                f"{now},12,13,11,12,1\n",
                encoding="utf-8",
            )
            futures_dir = base / "russian_futures"
            futures_dir.mkdir()
            (futures_dir / "RIM6-1d.csv").write_text(
                "open_time,open,high,low,close,volume\n"
                f"{now},113000,114000,112000,113500,1\n",
                encoding="utf-8",
            )
            service = HistoricalDataRefreshService(
                data_dir=base,
                client_factory=client_factory,
                now=lambda: datetime(2026, 6, 16, tzinfo=timezone.utc),
                store=store,
                import_legacy_csv=True,
            )

            summary = service.refresh_all()

        self.assertEqual(summary["refreshed"], 2)
        self.assertCountEqual(markets, ["russian_indices", "russian_futures"])

    def test_historical_client_accepts_moex_index_and_futures_markets(self):
        self.assertIsInstance(
            historical_client_for_market("russian_indices"),
            MoexSharesMarketDataClient,
        )
        self.assertIsInstance(
            historical_client_for_market("russian_futures"),
            MoexSharesMarketDataClient,
        )

    def test_historical_client_accepts_hong_kong_stock_market(self):
        self.assertIsInstance(
            historical_client_for_market("hong_kong_stocks"),
            YahooFuturesMarketDataClient,
        )


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
