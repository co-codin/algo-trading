import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from algo_trading.historical_data import HistoricalCsvRefreshService
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
    def test_refresh_service_updates_existing_csv_and_keeps_three_years(self):
        day_ms = 24 * 60 * 60 * 1000
        now = int(datetime(2026, 6, 16, tzinfo=timezone.utc).timestamp() * 1000)
        latest = _candle(now, 12.0)
        client = FakeHistoricalClient(
            [
                _candle(now - (1096 * day_ms), 10.0),
                _candle(now - (1095 * day_ms), 11.0),
                latest,
            ]
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "BTCUSDT-1d-1095d.csv"
            path.write_text(
                "open_time,open,high,low,close,volume\n"
                f"{now - (1096 * day_ms)},10,11,9,10,1\n",
                encoding="utf-8",
            )
            service = HistoricalCsvRefreshService(
                data_dir=Path(tmp),
                client_factory=lambda _market: client,
                now=lambda: datetime(2026, 6, 16, tzinfo=timezone.utc),
            )

            summary = service.refresh_all()

            rows = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(summary["refreshed"], 1)
        self.assertEqual(client.requests[0][0:2], ("BTCUSDT", "1d"))
        self.assertEqual(client.requests[0][2], now - (1095 * day_ms))
        self.assertNotIn(str(now - (1096 * day_ms)), "\n".join(rows))
        self.assertIn(str(now - (1095 * day_ms)), "\n".join(rows))
        self.assertIn(str(now), "\n".join(rows))

    def test_prune_all_uses_current_clock_for_three_year_cutoff(self):
        day_ms = 24 * 60 * 60 * 1000
        now = int(datetime(2026, 6, 16, tzinfo=timezone.utc).timestamp() * 1000)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "BTCUSDT-1d-1095d.csv"
            path.write_text(
                "open_time,open,high,low,close,volume\n"
                f"{now - (1096 * day_ms)},10,11,9,10,1\n"
                f"{now - (1095 * day_ms)},11,12,10,11,1\n",
                encoding="utf-8",
            )
            service = HistoricalCsvRefreshService(
                data_dir=Path(tmp),
                client_factory=lambda _market: FakeHistoricalClient([]),
                now=lambda: datetime(2026, 6, 16, tzinfo=timezone.utc),
            )

            summary = service.prune_all()
            rows = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(summary["pruned"], 1)
        self.assertNotIn(str(now - (1096 * day_ms)), "\n".join(rows))
        self.assertIn(str(now - (1095 * day_ms)), "\n".join(rows))

    def test_refresh_service_infers_mag7_stock_market_from_symbol_and_directory(self):
        now = int(datetime(2026, 6, 16, tzinfo=timezone.utc).timestamp() * 1000)
        markets: list[str] = []

        def client_factory(market: str) -> FakeHistoricalClient:
            markets.append(market)
            return FakeHistoricalClient([_candle(now, 12.0)])

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "AAPL-1d.csv").write_text(
                "open_time,open,high,low,close,volume\n",
                encoding="utf-8",
            )
            mag7_dir = base / "mag7_stocks"
            mag7_dir.mkdir()
            (mag7_dir / "MSFT-1d.csv").write_text(
                "open_time,open,high,low,close,volume\n",
                encoding="utf-8",
            )
            service = HistoricalCsvRefreshService(
                data_dir=base,
                client_factory=client_factory,
                now=lambda: datetime(2026, 6, 16, tzinfo=timezone.utc),
            )

            summary = service.refresh_all()

        self.assertEqual(summary["refreshed"], 2)
        self.assertEqual(markets, ["mag7_stocks", "mag7_stocks"])


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
