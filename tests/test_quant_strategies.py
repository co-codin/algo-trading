import unittest
from datetime import date

from algo_trading.market_breadth import MarketBreadthBar
from algo_trading.models import Candle
from algo_trading.quant_strategies import build_quant_strategy_ideas


def candle(index: int, close: float) -> Candle:
    return Candle(
        open_time=index,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=100.0,
    )


def candles(prices: list[float]) -> list[Candle]:
    return [candle(index, price) for index, price in enumerate(prices)]


class QuantStrategyTests(unittest.TestCase):
    def idea_by_id(self, idea_id: str, ideas):
        return next(idea for idea in ideas if idea.id == idea_id)

    def test_time_series_momentum_scores_positive_trend(self):
        ideas = build_quant_strategy_ideas(
            candles([100 + index for index in range(80)]),
            market="crypto_spot",
            symbol="BTCUSDT",
        )

        momentum = self.idea_by_id("time-series-momentum", ideas)

        self.assertEqual(momentum.action, "bullish")
        self.assertGreater(momentum.score, 50)
        self.assertGreater(momentum.metrics["lookback_return_pct"], 50)

    def test_rsi_mean_reversion_detects_oversold_setup(self):
        prices = [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86]

        ideas = build_quant_strategy_ideas(
            candles(prices),
            market="crypto_spot",
            symbol="BTCUSDT",
        )

        rsi_idea = self.idea_by_id("rsi-mean-reversion", ideas)

        self.assertEqual(rsi_idea.action, "bullish")
        self.assertLessEqual(rsi_idea.metrics["rsi"], 30)
        self.assertIn("oversold", " ".join(rsi_idea.reasons).lower())

    def test_breadth_confirmation_uses_latest_breadth_average(self):
        breadth_bars = {
            "$S5FD": [
                MarketBreadthBar("$S5FD", date(2026, 1, 2), 55, 60, 54, 60, 1),
            ],
            "$S5TW": [
                MarketBreadthBar("$S5TW", date(2026, 1, 2), 55, 58, 54, 58, 1),
            ],
        }

        ideas = build_quant_strategy_ideas(
            candles([100 + index for index in range(30)]),
            market="cme_futures",
            symbol="SPY",
            breadth_bars_by_symbol=breadth_bars,
        )

        breadth = self.idea_by_id("breadth-confirmation", ideas)

        self.assertEqual(breadth.action, "bullish")
        self.assertEqual(breadth.metrics["average_breadth"], 59.0)
        self.assertEqual(breadth.metrics["series_count"], 2)

