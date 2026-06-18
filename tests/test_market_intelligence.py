import unittest
from datetime import date

from algo_trading.algopack import AlgoPackRecord
from algo_trading.futoi import FutoiInstrument, FutoiRecord
from algo_trading.market_breadth import MarketBreadthBar
from algo_trading.market_intelligence import (
    build_algopack_events,
    build_breadth_confirmation_events,
    build_futoi_position_dashboard,
    build_unusual_futoi_events,
    build_volume_spike_events,
    public_futoi_dashboard,
    public_market_event,
)
from algo_trading.models import Candle


class MarketIntelligenceTests(unittest.TestCase):
    def test_futoi_dashboard_reports_latest_positioning_and_net_changes(self):
        records = [
            _futoi_record(date(2024, 4, 1), "IMOEXF", "FIZ", 100.0, 130.0, -30.0),
            _futoi_record(date(2024, 4, 7), "IMOEXF", "FIZ", 140.0, 180.0, -40.0),
            _futoi_record(date(2024, 4, 8), "IMOEXF", "FIZ", 190.0, 240.0, -50.0),
            _futoi_record(date(2024, 4, 8), "IMOEXF", "YUR", -20.0, 30.0, -50.0),
        ]

        dashboard = build_futoi_position_dashboard(
            records,
            [
                FutoiInstrument(
                    ticker="IMOEXF",
                    last_trade_date=date(2024, 4, 8),
                    gross_position=370.0,
                    net_position=170.0,
                    row_count=2,
                )
            ],
        )

        self.assertEqual(dashboard.summary["ticker"], "IMOEXF")
        self.assertEqual(dashboard.summary["net_position"], 170.0)
        self.assertEqual(dashboard.summary["gross_position"], 370.0)
        self.assertEqual(dashboard.summary["net_change_1d"], 30.0)
        self.assertEqual(dashboard.summary["net_change_1w"], 70.0)
        self.assertAlmostEqual(dashboard.summary["net_change_1d_pct"], 21.4286, places=4)
        self.assertEqual(
            [snapshot.net_position for snapshot in dashboard.snapshots],
            [100.0, 140.0, 170.0],
        )
        payload = public_futoi_dashboard(dashboard)
        self.assertEqual(payload["instrument_count"], 1)
        self.assertEqual(payload["snapshot_count"], 3)
        self.assertEqual(payload["latest"][0]["ticker"], "IMOEXF")
        self.assertEqual(payload["unusual_events"], payload["events"])

    def test_unusual_futoi_events_flag_large_net_position_change(self):
        records = [
            _futoi_record(date(2024, 4, 7), "SBERF", "FIZ", 100.0, 150.0, -50.0),
            _futoi_record(date(2024, 4, 8), "SBERF", "FIZ", 180.0, 230.0, -50.0),
        ]

        events = build_unusual_futoi_events(records, min_net_change_pct=50.0)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, "futoi_change")
        self.assertEqual(events[0].symbol, "SBERF")
        self.assertEqual(events[0].severity, "high")
        self.assertEqual(events[0].metrics["net_change"], 80.0)
        self.assertEqual(events[0].metrics["net_change_pct"], 80.0)
        self.assertIn("FUTOI", events[0].title)

    def test_unusual_futoi_events_do_not_compare_different_tickers(self):
        records = [
            _futoi_record(date(2024, 4, 7), "AAA", "FIZ", 100.0, 100.0, 0.0),
            _futoi_record(date(2024, 4, 8), "AAA", "FIZ", 100.0, 100.0, 0.0),
            _futoi_record(date(2024, 4, 7), "BBB", "FIZ", 10_000.0, 10_000.0, 0.0),
            _futoi_record(date(2024, 4, 8), "BBB", "FIZ", 10_000.0, 10_000.0, 0.0),
        ]

        events = build_unusual_futoi_events(records)

        self.assertEqual(events, [])

    def test_algopack_events_only_emit_explicit_megaalerts(self):
        records = [
            AlgoPackRecord(
                dataset="orderstats",
                market="russian_bluechips",
                ticker="SBER",
                trade_date=date(2024, 4, 8),
                trade_time="10:05:00",
                metrics={"put_orders": 12, "cancel_orders": 5},
            ),
            AlgoPackRecord(
                dataset="obstats",
                market="russian_bluechips",
                ticker="SBER",
                trade_date=date(2024, 4, 8),
                trade_time="10:05:00",
                metrics={"imbalance_val_bbo": -0.2},
            ),
            AlgoPackRecord(
                dataset="alerts",
                market="russian_bluechips",
                ticker="SBER",
                trade_date=date(2024, 4, 8),
                trade_time="10:05:00",
                metrics={"alert_type": "pr_high_max", "threshold": 307.77, "value": 308.04},
            ),
        ]

        events = build_algopack_events(records)

        self.assertEqual([event.type for event in events], ["mega_alert"])
        self.assertEqual(events[0].symbol, "SBER")

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


def _futoi_record(
    trade_date: date,
    ticker: str,
    client_group: str,
    position: float,
    long_position: float,
    short_position: float,
) -> FutoiRecord:
    return FutoiRecord(
        trade_date=trade_date,
        trade_time="18:45:00",
        ticker=ticker,
        client_group=client_group,
        position=position,
        position_long=long_position,
        position_short=short_position,
        position_long_count=1,
        position_short_count=1,
    )


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
