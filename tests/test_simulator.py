import unittest
from dataclasses import replace

from algo_trading.models import AllowedSide, Candle, PositionSide, StrategyConfig, StrategyName
from algo_trading.simulator import run_backtest


def candle(time: int, close: float, volume: float = 1.0) -> Candle:
    return Candle(
        open_time=time,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=volume,
    )


def candles(prices: list[float], volumes: list[float] | None = None) -> list[Candle]:
    source_volumes = volumes or [1.0] * len(prices)
    return [
        candle(index, price, volume)
        for index, (price, volume) in enumerate(zip(prices, source_volumes))
    ]


class SimulatorTests(unittest.TestCase):
    def test_backtest_rejects_candles_before_indicator_warmup(self):
        candles = [candle(index, price) for index, price in enumerate([10, 11, 12, 13])]

        with self.assertRaisesRegex(ValueError, "not enough candles"):
            run_backtest(candles, StrategyConfig())

    def test_backtest_rejects_invalid_risk_config(self):
        candles = [candle(index, float(index + 10)) for index in range(30)]
        config = StrategyConfig(stop_loss_pct=-0.01)

        with self.assertRaisesRegex(ValueError, "stop_loss_pct"):
            run_backtest(candles, config)

    def test_backtest_rejects_risk_percentages_above_one(self):
        candles = [candle(index, float(index + 10)) for index in range(30)]

        for config in [
            StrategyConfig(stop_loss_pct=1.5),
            StrategyConfig(take_profit_pct=1.5),
            StrategyConfig(trailing_stop_pct=1.5),
        ]:
            with self.subTest(config=config):
                with self.assertRaisesRegex(ValueError, "between 0 and 1"):
                    run_backtest(candles, config)

    def test_backtest_rejects_inverted_rsi_thresholds(self):
        candles = [candle(index, float(index + 10)) for index in range(30)]
        config = StrategyConfig(rsi_oversold=75.0, rsi_overbought=70.0)

        with self.assertRaisesRegex(ValueError, "rsi"):
            run_backtest(candles, config)

    def test_backtest_produces_trade_and_equity(self):
        candles = [
            candle(index, price)
            for index, price in enumerate([10, 12, 13, 14, 13, 12, 11, 10])
        ]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            position_fraction=0.5,
            fee_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(candles, config)

        self.assertGreaterEqual(len(result.equity), len(candles))
        self.assertIn("final_balance", result.summary)
        self.assertGreater(len(result.trades), 0)

    def test_backtest_summary_includes_risk_and_exposure_metrics(self):
        sample_candles = [
            candle(index, price)
            for index, price in enumerate([10, 12, 14, 13, 11, 9, 10, 12])
        ]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            fee_rate=0.0,
            slippage_rate=0.0,
            stop_loss_pct=1.0,
            take_profit_pct=1.0,
        )

        result = run_backtest(sample_candles, config)

        self.assertIn("sharpe_ratio", result.summary)
        self.assertIn("sortino_ratio", result.summary)
        self.assertIn("max_drawdown_duration", result.summary)
        self.assertIn("average_trade_duration", result.summary)
        self.assertIn("exposure_pct", result.summary)
        self.assertIn("worst_trade", result.summary)
        self.assertGreater(result.summary["exposure_pct"], 0)
        self.assertGreaterEqual(result.summary["max_drawdown_duration"], 0)
        self.assertEqual(
            result.summary["worst_trade"],
            round(min(trade.realized_pnl for trade in result.trades), 8),
        )

    def test_long_trade_can_profit_when_price_rises(self):
        candles = [candle(index, price) for index, price in enumerate([10, 12, 13, 14])]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            fee_rate=0.0,
            slippage_rate=0.0,
            position_fraction=1.0,
        )

        result = run_backtest(candles, config)

        long_trades = [trade for trade in result.trades if trade.side is PositionSide.LONG]
        self.assertTrue(long_trades)
        self.assertTrue(any(trade.realized_pnl > 0 for trade in long_trades))

    def test_short_trade_can_profit_when_price_falls(self):
        candles = [candle(index, price) for index, price in enumerate([12, 10, 9, 8])]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            fee_rate=0.0,
            slippage_rate=0.0,
            position_fraction=1.0,
        )

        result = run_backtest(candles, config)

        short_trades = [trade for trade in result.trades if trade.side is PositionSide.SHORT]
        self.assertTrue(short_trades)
        self.assertTrue(any(trade.realized_pnl > 0 for trade in short_trades))

    def test_stop_loss_exit_reason_is_recorded(self):
        candles = [candle(index, price) for index, price in enumerate([10, 12, 11, 10])]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            stop_loss_pct=0.05,
            take_profit_pct=1.0,
            fee_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(candles, config)

        self.assertEqual(result.trades[0].exit_reason, "stop_loss")

    def test_take_profit_exit_reason_is_recorded(self):
        candles = [candle(index, price) for index, price in enumerate([10, 12, 13, 14])]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            stop_loss_pct=1.0,
            take_profit_pct=0.05,
            fee_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(candles, config)

        self.assertEqual(result.trades[0].exit_reason, "take_profit")

    def test_trailing_stop_exit_reason_is_recorded(self):
        candles = [candle(index, price) for index, price in enumerate([10, 12, 14, 13])]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            stop_loss_pct=1.0,
            take_profit_pct=1.0,
            trailing_stop_pct=0.05,
            fee_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(candles, config)

        self.assertEqual(result.trades[0].exit_reason, "trailing_stop")

    def test_fees_and_slippage_are_recorded(self):
        candles = [candle(index, price) for index, price in enumerate([10, 12, 13, 14])]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            fee_rate=0.001,
            slippage_rate=0.0005,
        )

        result = run_backtest(candles, config)

        self.assertGreater(result.trades[0].fees, 0)
        self.assertGreater(result.trades[0].slippage, 0)
        self.assertGreater(result.summary["fee_total"], 0)
        self.assertGreater(result.summary["slippage_estimate"], 0)

    def test_profit_factor_is_explicit_when_there_are_no_losses(self):
        candles = [candle(index, price) for index, price in enumerate([10, 12, 13, 14])]
        config = StrategyConfig(
            fast_ema=1,
            slow_ema=2,
            rsi_period=2,
            fee_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(candles, config)

        self.assertEqual(result.summary["profit_factor"], "infinite")

    def test_backtest_runs_macd_strategy(self):
        candles = [
            candle(index, price)
            for index, price in enumerate([10, 9, 8, 9, 11, 13, 15, 14, 12, 10])
        ]
        config = StrategyConfig(
            strategy=StrategyName.MACD,
            fast_ema=2,
            slow_ema=5,
            macd_signal=2,
            stop_loss_pct=1.0,
            take_profit_pct=1.0,
            fee_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(candles, config)

        self.assertGreater(len(result.trades), 0)
        self.assertTrue(
            any(trade.entry_reason.startswith("macd_") for trade in result.trades)
        )

    def test_backtest_runs_bollinger_reversion_strategy(self):
        candles = [
            candle(index, price)
            for index, price in enumerate([10, 10, 10, 7, 10, 11, 10, 9])
        ]
        config = StrategyConfig(
            strategy=StrategyName.BOLLINGER_REVERSION,
            bollinger_period=3,
            bollinger_stddev=1.0,
            stop_loss_pct=1.0,
            take_profit_pct=1.0,
            fee_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(candles, config)

        self.assertGreater(len(result.trades), 0)
        self.assertEqual(result.trades[0].entry_reason, "bollinger_lower_reclaim")

    def test_backtest_runs_donchian_breakout_strategy(self):
        candles = [
            candle(index, price)
            for index, price in enumerate([10, 10, 10, 14, 15, 16, 12, 9, 8])
        ]
        config = StrategyConfig(
            strategy=StrategyName.DONCHIAN_BREAKOUT,
            donchian_period=3,
            stop_loss_pct=1.0,
            take_profit_pct=1.0,
            fee_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(candles, config)

        self.assertGreater(len(result.trades), 0)
        self.assertEqual(result.trades[0].entry_reason, "donchian_breakout_high")

    def test_backtest_runs_rsi_reversal_strategy(self):
        candles = [
            candle(index, price)
            for index, price in enumerate([10, 9, 8, 9, 10, 11, 10, 9])
        ]
        config = StrategyConfig(
            strategy=StrategyName.RSI_REVERSAL,
            rsi_period=2,
            rsi_oversold=30.0,
            rsi_overbought=70.0,
            stop_loss_pct=1.0,
            take_profit_pct=1.0,
            fee_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(candles, config)

        self.assertGreater(len(result.trades), 0)
        self.assertEqual(result.trades[0].entry_reason, "rsi_reversal_long")

    def test_backtest_rejects_invalid_strategy_periods(self):
        candles = [candle(index, float(index + 10)) for index in range(30)]

        for config in [
            StrategyConfig(macd_signal=0),
            StrategyConfig(bollinger_period=0),
            StrategyConfig(bollinger_stddev=0),
            StrategyConfig(donchian_period=0),
            StrategyConfig(rsi_midline=101),
        ]:
            with self.subTest(config=config):
                with self.assertRaisesRegex(ValueError, "strategy"):
                    run_backtest(candles, config)

    def test_backtest_rejects_invalid_extended_strategy_periods(self):
        candles = [candle(index, float(index + 10)) for index in range(80)]

        for config in [
            StrategyConfig(strategy=StrategyName("supertrend"), atr_period=0),
            StrategyConfig(strategy=StrategyName("supertrend"), supertrend_multiplier=0),
            StrategyConfig(strategy=StrategyName("vwap-reversion"), vwap_period=0),
            StrategyConfig(strategy=StrategyName("vwap-reversion"), vwap_threshold_pct=-0.1),
            StrategyConfig(strategy=StrategyName("stoch-rsi-reversal"), stoch_rsi_period=0),
            StrategyConfig(strategy=StrategyName("stoch-rsi-reversal"), stoch_rsi_oversold=90, stoch_rsi_overbought=80),
            StrategyConfig(strategy=StrategyName("ema-ribbon"), ema_ribbon_fast=5, ema_ribbon_mid=3, ema_ribbon_slow=8),
            StrategyConfig(strategy=StrategyName("momentum-scalping"), momentum_period=0),
        ]:
            with self.subTest(config=config):
                with self.assertRaisesRegex(ValueError, "strategy"):
                    run_backtest(candles, config)

    def test_backtest_rejects_invalid_new_strategy_parameters(self):
        candles = [candle(index, float(index + 10)) for index in range(90)]

        for config in [
            StrategyConfig(strategy=StrategyName("keltner-breakout"), keltner_multiplier=0),
            StrategyConfig(strategy=StrategyName("cci-reversal"), cci_period=0),
            StrategyConfig(strategy=StrategyName("cci-reversal"), cci_oversold=120, cci_overbought=100),
            StrategyConfig(strategy=StrategyName("williams-r-reversal"), williams_period=0),
            StrategyConfig(
                strategy=StrategyName("williams-r-reversal"),
                williams_oversold=-10,
                williams_overbought=-20,
            ),
            StrategyConfig(strategy=StrategyName("obv-trend"), volume_period=0),
            StrategyConfig(strategy=StrategyName("volume-breakout"), volume_multiplier=0),
            StrategyConfig(
                strategy=StrategyName("bollinger-squeeze-release"),
                squeeze_threshold_pct=-0.01,
            ),
        ]:
            with self.subTest(config=config):
                with self.assertRaisesRegex(ValueError, "strategy"):
                    run_backtest(candles, config)

    def test_backtest_rejects_new_strategy_candles_before_warmup(self):
        for config, sample_candles in [
            (
                StrategyConfig(
                    strategy=StrategyName("keltner-breakout"),
                    fast_ema=1,
                    slow_ema=2,
                    rsi_period=2,
                    atr_period=5,
                ),
                candles([10, 11, 12, 13, 14]),
            ),
            (
                StrategyConfig(
                    strategy=StrategyName("volume-breakout"),
                    fast_ema=1,
                    slow_ema=2,
                    rsi_period=2,
                    donchian_period=3,
                    volume_period=5,
                ),
                candles([10, 11, 12, 13, 14]),
            ),
        ]:
            with self.subTest(config=config):
                with self.assertRaisesRegex(ValueError, "not enough candles"):
                    run_backtest(sample_candles, config)

    def test_backtest_runs_new_strategy_bundle(self):
        cases = [
            (
                StrategyConfig(
                    strategy=StrategyName("keltner-breakout"),
                    atr_period=3,
                    keltner_multiplier=0.5,
                ),
                candles([10, 10, 10, 13, 14]),
                "keltner_breakout_long",
            ),
            (
                StrategyConfig(
                    strategy=StrategyName("ema-pullback"),
                    fast_ema=2,
                    slow_ema=4,
                ),
                candles([10, 11, 12, 11, 13, 14]),
                "ema_pullback_long",
            ),
            (
                StrategyConfig(
                    strategy=StrategyName("atr-trailing-trend"),
                    atr_period=2,
                    supertrend_multiplier=1.0,
                ),
                candles([12, 11, 10, 9, 10, 12, 14, 16, 17]),
                "atr_trailing_trend_long",
            ),
            (
                StrategyConfig(
                    strategy=StrategyName("cci-reversal"),
                    cci_period=3,
                    cci_oversold=-100.0,
                    cci_overbought=100.0,
                ),
                candles([10, 10, 7, 10, 11, 12]),
                "cci_reversal_long",
            ),
            (
                StrategyConfig(
                    strategy=StrategyName("williams-r-reversal"),
                    williams_period=3,
                    williams_oversold=-80.0,
                    williams_overbought=-20.0,
                ),
                candles([10, 10, 7, 10, 11, 12]),
                "williams_r_reversal_long",
            ),
            (
                StrategyConfig(
                    strategy=StrategyName("bollinger-squeeze-release"),
                    bollinger_period=3,
                    bollinger_stddev=1.0,
                    squeeze_threshold_pct=0.05,
                ),
                candles([10, 10, 10, 12, 14, 15]),
                "bollinger_squeeze_release_long",
            ),
            (
                StrategyConfig(
                    strategy=StrategyName("obv-trend"),
                    fast_ema=1,
                    slow_ema=3,
                    volume_period=2,
                ),
                candles([10, 9, 10, 11, 12, 13], [100, 100, 300, 300, 300, 300]),
                "obv_trend_long",
            ),
            (
                StrategyConfig(
                    strategy=StrategyName("volume-breakout"),
                    donchian_period=3,
                    volume_period=3,
                    volume_multiplier=1.5,
                ),
                candles([10, 10, 10, 14, 15], [100, 100, 100, 400, 400]),
                "volume_breakout_long",
            ),
            (
                StrategyConfig(
                    strategy=StrategyName("vwap-trend-continuation"),
                    fast_ema=2,
                    slow_ema=4,
                    vwap_period=3,
                ),
                candles([10, 11, 12, 11, 13, 14]),
                "vwap_trend_continuation_long",
            ),
        ]

        for config, sample_candles, entry_reason in cases:
            with self.subTest(strategy=config.strategy):
                result = run_backtest(
                    sample_candles,
                    replace(
                        config,
                        fee_rate=0.0,
                        slippage_rate=0.0,
                        stop_loss_pct=1.0,
                        take_profit_pct=1.0,
                        allowed_side=AllowedSide.LONG_ONLY,
                    ),
                )

                self.assertGreater(len(result.trades), 0)
                self.assertEqual(result.trades[0].entry_reason, entry_reason)


if __name__ == "__main__":
    unittest.main()
