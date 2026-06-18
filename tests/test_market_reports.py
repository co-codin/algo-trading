import unittest
from datetime import date

from algo_trading.algopack import AlgoPackRecord
from algo_trading.futoi import FutoiRecord
from algo_trading.market_breadth import MarketBreadthBar
from algo_trading.market_intelligence import build_unusual_futoi_events
from algo_trading.market_reports import (
    build_daily_market_report,
    public_daily_market_report,
)


class MarketReportTests(unittest.TestCase):
    def test_daily_market_report_summarizes_russian_market_context(self):
        futoi_records = [
            _futoi_record(date(2024, 4, 7), "IMOEXF", 100.0),
            _futoi_record(date(2024, 4, 8), "IMOEXF", 180.0),
            _futoi_record(date(2024, 4, 7), "SBERF", -50.0),
            _futoi_record(date(2024, 4, 8), "SBERF", -20.0),
        ]
        algopack_records = [
            AlgoPackRecord(
                dataset="alerts",
                market="russian_bluechips",
                ticker="SBER",
                trade_date=date(2024, 4, 8),
                trade_time="10:05:00",
                metrics={"alert_type": "vol_b_99_9_pctl", "threshold": 61475, "value": 78552},
            )
        ]
        breadth_bars_by_symbol = {
            "$S5FD": [_breadth_bar("$S5FD", date(2024, 4, 8), 68.0)],
            "$NDFD": [_breadth_bar("$NDFD", date(2024, 4, 8), 72.0)],
        }

        report = build_daily_market_report(
            trading_date=date(2024, 4, 8),
            futoi_records=futoi_records,
            algopack_records=algopack_records,
            breadth_bars_by_symbol=breadth_bars_by_symbol,
            triggered_events=build_unusual_futoi_events(futoi_records, min_net_change_pct=20.0),
        )

        self.assertEqual(report.language, "ru")
        self.assertIn("Ежедневный отчет рынка", report.title)
        self.assertIn("Что изменилось сегодня", report.text)
        self.assertIn("Позиционирование FUTOI", report.text)
        self.assertIn("IMOEXF", report.text)
        self.assertIn("SBER", report.text)
        self.assertIn("vol_b_99_9_pctl", report.text)
        self.assertIn("Ширина рынка", report.text)
        self.assertTrue(report.triggered_symbols)

    def test_public_daily_market_report_is_api_ready(self):
        report = build_daily_market_report(
            trading_date=date(2024, 4, 8),
            futoi_records=[],
            algopack_records=[],
            breadth_bars_by_symbol={},
            triggered_events=[],
        )

        payload = public_daily_market_report(report)

        self.assertEqual(payload["date"], "2024-04-08")
        self.assertEqual(payload["language"], "ru")
        self.assertIn("title", payload)
        self.assertIn("sections", payload)
        self.assertIn("text", payload)
        self.assertEqual(payload["triggered_symbols"], [])


def _futoi_record(trade_date: date, ticker: str, position: float) -> FutoiRecord:
    return FutoiRecord(
        trade_date=trade_date,
        trade_time="18:45:00",
        ticker=ticker,
        client_group="FIZ",
        position=position,
        position_long=max(position, 0.0),
        position_short=min(position, 0.0),
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
