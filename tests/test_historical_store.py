import unittest
from datetime import date, datetime, timedelta, timezone

from algo_trading.historical_store import (
    CandleSeries,
    InMemoryHistoricalDataStore,
)
from algo_trading.futoi import FutoiRecord
from algo_trading.market_breadth import MarketBreadthBar
from algo_trading.models import Candle


class HistoricalStoreTests(unittest.TestCase):
    def test_memory_store_upserts_dedupes_and_loads_candles_by_series(self):
        store = InMemoryHistoricalDataStore()
        older = _candle(1000, 10.0)
        replacement = _candle(1000, 11.0)
        newer = _candle(2000, 12.0)

        inserted = store.upsert_candles(
            "crypto_spot",
            "btcusdt",
            "5m",
            [older, replacement, newer],
            source="unit-test",
        )

        self.assertEqual(inserted, 2)
        self.assertEqual(
            store.list_candle_series(),
            [CandleSeries("crypto_spot", "BTCUSDT", "5m")],
        )
        self.assertEqual(
            [candle.close for candle in store.load_candles("crypto_spot", "BTCUSDT", "5m")],
            [11.0, 12.0],
        )
        self.assertEqual(
            [candle.open_time for candle in store.load_candles("crypto_spot", "BTCUSDT", "5m", limit=1)],
            [2000],
        )

    def test_memory_store_prunes_old_candles(self):
        store = InMemoryHistoricalDataStore()
        store.upsert_candles(
            "crypto_spot",
            "BTCUSDT",
            "1d",
            [_candle(1000, 10.0), _candle(2000, 20.0)],
            source="unit-test",
        )

        deleted = store.prune_candles(cutoff_open_time=1500)

        self.assertEqual(deleted, 1)
        self.assertEqual(
            [candle.open_time for candle in store.load_candles("crypto_spot", "BTCUSDT", "1d")],
            [2000],
        )

    def test_memory_store_tracks_breadth_freshness_and_prunes_non_exempt_symbols(self):
        current_time = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
        store = InMemoryHistoricalDataStore(now=lambda: current_time)
        store.upsert_breadth_bars(
            "$S5FD",
            [
                _breadth_bar("$S5FD", date(2025, 6, 15), 41.0),
                _breadth_bar("$S5FD", date(2026, 6, 16), 60.0),
            ],
            source="unit-test",
        )
        store.upsert_breadth_bars(
            "$CPC",
            [_breadth_bar("$CPC", date(2020, 1, 2), 0.9)],
            source="unit-test",
        )

        self.assertTrue(store.is_breadth_fresh("$S5FD", max_age_seconds=3600))
        store.advance_time(timedelta(hours=2))
        self.assertFalse(store.is_breadth_fresh("$S5FD", max_age_seconds=3600))

        deleted = store.prune_breadth_bars(
            cutoff_date=date(2025, 6, 16),
            exclude_symbols={"$CPC"},
        )

        self.assertEqual(deleted, 1)
        self.assertEqual(
            [bar.date for bar in store.load_breadth_bars("$S5FD")],
            [date(2026, 6, 16)],
        )
        self.assertEqual(
            [bar.date for bar in store.load_breadth_bars("$CPC")],
            [date(2020, 1, 2)],
        )

    def test_memory_store_upserts_and_loads_futoi_records(self):
        store = InMemoryHistoricalDataStore()
        original = _futoi_record(date(2024, 4, 8), "IMOEXF", "YUR", -19.0)
        replacement = _futoi_record(date(2024, 4, 8), "IMOEXF", "YUR", -21.0)
        other_ticker = _futoi_record(date(2024, 4, 8), "SBERF", "FIZ", 9.0)

        inserted = store.upsert_futoi_records(
            [original, replacement, other_ticker],
            source="unit-test",
        )

        self.assertEqual(inserted, 2)
        self.assertEqual(
            [record.position for record in store.load_futoi_records(ticker="imoexf")],
            [-21.0],
        )
        self.assertEqual(
            [record.ticker for record in store.load_futoi_records(trading_date=date(2024, 4, 8))],
            ["IMOEXF", "SBERF"],
        )

    def test_memory_store_prunes_futoi_records_older_than_cutoff(self):
        store = InMemoryHistoricalDataStore()
        store.upsert_futoi_records(
            [
                _futoi_record(date(2024, 6, 16), "IMOEXF", "YUR", -19.0),
                _futoi_record(date(2024, 6, 17), "IMOEXF", "FIZ", 21.0),
            ],
            source="unit-test",
        )

        deleted = store.prune_futoi_records(cutoff_date=date(2024, 6, 17))

        self.assertEqual(deleted, 1)
        self.assertEqual(
            [record.client_group for record in store.load_futoi_records()],
            ["FIZ"],
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


def _breadth_bar(symbol: str, bar_date: date, close: float) -> MarketBreadthBar:
    return MarketBreadthBar(
        symbol=symbol,
        date=bar_date,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=100.0,
    )


def _futoi_record(
    trade_date: date,
    ticker: str,
    client_group: str,
    position: float,
) -> FutoiRecord:
    return FutoiRecord(
        trade_date=trade_date,
        trade_time="18:45:00",
        ticker=ticker,
        client_group=client_group,
        position=position,
        position_long=abs(position),
        position_short=0.0,
        position_long_count=1,
        position_short_count=0,
    )


if __name__ == "__main__":
    unittest.main()
