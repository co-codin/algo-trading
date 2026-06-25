import unittest
from datetime import date

from algo_trading.market_breadth import MarketBreadthBar
from algo_trading.market_intelligence import (
    build_breadth_confirmation_events,
    build_volume_spike_events,
    public_market_event,
)
from algo_trading.models import Candle


class MarketIntelligenceTests(unittest.TestCase):
    def test_volume_spike_events_compare_latest_volume_to_prior_average(self):
        candles = [
            Candle(index, 10.0, 11.0, 9.0, 10.0, volume)
            for index, volume in enumerate([100.0, 120.0, 80.0, 360.0])
        ]

        events = build_volume_spike_events(
            candles,
            market="crypto_spot",
            symbol="BTCUSDT",
            interval="1h",
            lookback=3,
            min_ratio=3.0,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, "volume_spike")
        self.assertEqual(events[0].market, "crypto_spot")
        self.assertEqual(events[0].symbol, "BTCUSDT")
        self.assertEqual(events[0].time, 3)
        self.assertEqual(events[0].metrics["volume"], 360.0)
        self.assertEqual(events[0].metrics["volume_ratio"], 3.6)

    def test_breadth_confirmation_events_use_average_latest_breadth(self):
        bars_by_symbol = {
            "$S5FD": [_breadth_bar("$S5FD", date(2024, 4, 8), 68.0)],
            "$NDFD": [_breadth_bar("$NDFD", date(2024, 4, 8), 72.0)],
            "$NCFD": [_breadth_bar("$NCFD", date(2024, 4, 8), 65.0)],
        }

        events = build_breadth_confirmation_events(bars_by_symbol, bullish_threshold=60.0)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, "breadth_confirmation")
        self.assertEqual(events[0].severity, "medium")
        self.assertEqual(events[0].metrics["average_breadth"], 68.3333)
        self.assertEqual(events[0].metrics["series_count"], 3)
        self.assertIn("Breadth", events[0].title)

    def test_public_market_event_is_stable_for_api_payloads(self):
        event = build_volume_spike_events(
            [
                Candle(1, 10.0, 11.0, 9.0, 10.0, 100.0),
                Candle(2, 10.0, 11.0, 9.0, 10.0, 400.0),
            ],
            market="crypto_spot",
            symbol="BTCUSDT",
            interval="1h",
            lookback=1,
            min_ratio=3.0,
        )[0]

        payload = public_market_event(event)

        self.assertEqual(payload["type"], "volume_spike")
        self.assertEqual(payload["market"], "crypto_spot")
        self.assertEqual(payload["symbol"], "BTCUSDT")
        self.assertEqual(payload["severity"], "high")
        self.assertEqual(payload["time"], 2)
        self.assertEqual(payload["details"], payload["description"])
        self.assertEqual(payload["metrics"]["volume_ratio"], 4.0)


def _breadth_bar(symbol: str, bar_date: date, close: float) -> MarketBreadthBar:
    return MarketBreadthBar(
        symbol=symbol,
        date=bar_date,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
    )


if __name__ == "__main__":
    unittest.main()
