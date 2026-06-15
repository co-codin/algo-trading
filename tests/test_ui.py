import json
import tempfile
import unittest
from pathlib import Path

from algo_trading.data import TransientMarketDataError
from algo_trading.models import Candle
from algo_trading.ui import (
    is_frontend_route,
    is_vite_asset_route,
    load_run_details,
    list_runs,
    live_chart_payload,
    paper_trade_markers,
    run_backtest_payload,
    strategies_payload,
    strategy_lab_payload,
    top_symbols_payload,
)


def candle(time: int, close: float) -> Candle:
    return Candle(
        open_time=time,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1.0,
    )


class FakeClient:
    def __init__(self) -> None:
        self.kline_symbols: list[str] = []
        self.candles: list[Candle] | None = None

    def get_24h_tickers(self) -> list[dict[str, object]]:
        return [
            {"symbol": "BTCUSDT", "quoteVolume": "500", "lastPrice": "65000"},
            {"symbol": "ETHUSDT", "quoteVolume": "250", "lastPrice": "1700"},
            {"symbol": "USDCUSDT", "quoteVolume": "999", "lastPrice": "1"},
        ]

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        self.kline_symbols.append(symbol)
        if self.candles is not None:
            return self.candles[:limit]
        return [candle(index, price) for index, price in enumerate([10, 12, 13, 14])]


class FlakyLiveClient(FakeClient):
    def __init__(self) -> None:
        super().__init__()
        self.failures_remaining = 1

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise TransientMarketDataError("temporary market data outage")
        return super().get_klines(symbol, interval, limit)


def trending_candles() -> list[Candle]:
    prices = [10, 9, 8, 9, 11, 13, 12, 10, 8, 7, 9, 11]
    return [candle(index, price) for index, price in enumerate(prices)]


class UiTests(unittest.TestCase):
    def test_live_market_controls_are_selectable(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")

        self.assertIn("const liveSymbolOptions = [", source)
        self.assertIn("const liveIntervalOptions = [", source)
        self.assertIn("const liveCandleOptions = [", source)
        self.assertIn("const liveStrategyOptions = computed(() => [", source)
        self.assertIn('name: "all"', source)
        self.assertIn("All strategies", source)
        self.assertIn('<select v-model="liveSymbol"', source)
        self.assertIn('<select v-model="liveInterval"', source)
        self.assertIn('<select v-model="liveLimit"', source)
        self.assertIn('class="live-strategy-field"', source)
        self.assertIn('<select v-model="settings.strategy"', source)
        self.assertIn("v-for=\"strategy in liveStrategyOptions\"", source)
        self.assertIn('value: "BTCUSDT"', source)
        self.assertIn('value: "ETHUSDT"', source)
        self.assertIn('value: "1m"', source)
        self.assertIn('value: "1h"', source)
        self.assertIn("value: 180", source)
        self.assertIn("value: 500", source)

    def test_live_market_selector_changes_auto_refresh_chart(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")

        self.assertIn('import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";', source)
        self.assertIn("watch([liveSymbol, liveInterval, liveLimit, () => settings.strategy], () => {", source)
        self.assertIn('if (activeMode.value === "live") {', source)
        self.assertIn("refreshLiveChart();", source)

    def test_all_strategies_selection_stays_live_only(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")

        self.assertIn('if (mode !== "live" && settings.strategy === "all") {', source)
        self.assertIn('settings.strategy = "ema-rsi";', source)

    def test_live_ui_uses_trading_terminal_visual_language(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        style_source = (root / "frontend" / "src" / "style.css").read_text(
            encoding="utf-8"
        )
        chart_source = (
            root / "frontend" / "src" / "components" / "TradingViewChart.vue"
        ).read_text(encoding="utf-8")

        self.assertIn('class="live-market-strip"', app_source)
        self.assertIn('class="ticker-pill"', app_source)
        self.assertIn("--bg: #0f1318;", style_source)
        self.assertIn("--chart-bg: #131722;", style_source)
        self.assertIn(".live-market-strip", style_source)
        self.assertIn('textColor: "#d1d4dc"', chart_source)
        self.assertIn('color: "#131722"', chart_source)

    def test_frontend_routes_allow_direct_view_urls(self):
        self.assertTrue(is_frontend_route("/"))
        self.assertTrue(is_frontend_route("/backtest"))
        self.assertTrue(is_frontend_route("/paper"))
        self.assertTrue(is_frontend_route("/live"))
        self.assertTrue(is_frontend_route("/chart"))
        self.assertTrue(is_frontend_route("/runs"))
        self.assertTrue(is_frontend_route("/history"))
        self.assertTrue(is_frontend_route("/lab"))

    def test_frontend_routes_do_not_capture_api_or_unknown_paths(self):
        self.assertFalse(is_frontend_route("/api/runs"))
        self.assertFalse(is_frontend_route("/styles.css"))
        self.assertFalse(is_frontend_route("/unknown"))

    def test_vite_asset_routes_are_restricted_to_assets_directory(self):
        self.assertTrue(is_vite_asset_route("/assets/index.js"))
        self.assertTrue(is_vite_asset_route("/assets/index.css"))
        self.assertFalse(is_vite_asset_route("/api/runs"))
        self.assertFalse(is_vite_asset_route("/assets/../index.html"))

    def test_top_symbols_payload_filters_and_ranks(self):
        payload = top_symbols_payload(FakeClient(), top=2)

        self.assertEqual(
            [item["symbol"] for item in payload["symbols"]],
            ["BTCUSDT", "ETHUSDT"],
        )

    def test_strategies_payload_lists_strategy_metadata(self):
        payload = strategies_payload()

        strategy_names = [strategy["name"] for strategy in payload["strategies"]]
        self.assertIn("supertrend", strategy_names)
        self.assertIn("vwap-reversion", strategy_names)
        self.assertTrue(all(strategy["description"] for strategy in payload["strategies"]))

    def test_strategy_lab_payload_ranks_strategy_results(self):
        client = FakeClient()
        client.candles = trending_candles()

        payload = strategy_lab_payload(
            {
                "symbols": "BTCUSDT",
                "strategies": "ema-rsi,macd",
                "presets": "custom",
                "interval": "1h",
                "limit": 12,
                "fast_ema": 1,
                "slow_ema": 3,
                "macd_signal": 2,
                "rsi_period": 2,
                "rsi_overbought": 100,
                "rsi_oversold": 0,
            },
            client=client,
        )

        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["mode"], "strategy-lab")
        self.assertEqual(len(payload["rows"]), 2)
        self.assertEqual(payload["rows"][0]["rank"], 1)
        self.assertGreaterEqual(
            payload["rows"][0]["total_return_pct"],
            payload["rows"][1]["total_return_pct"],
        )

    def test_run_backtest_payload_writes_one_run_per_symbol(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as tmp:
            payload = run_backtest_payload(
                {
                    "symbols": "BTCUSDT,ETHUSDT",
                    "interval": "1h",
                    "limit": 4,
                    "fast_ema": 1,
                    "slow_ema": 2,
                    "rsi_period": 2,
                    "fee_rate": 0,
                    "slippage_rate": 0,
                },
                client=client,
                output_root=Path(tmp),
            )

            self.assertEqual(client.kline_symbols, ["BTCUSDT", "ETHUSDT"])
            self.assertEqual(
                [run["symbol"] for run in payload["runs"]],
                ["BTCUSDT", "ETHUSDT"],
            )
            self.assertEqual(len(list(Path(tmp).glob("backtests/*/summary.json"))), 2)

    def test_list_runs_reads_recent_summaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "backtests" / "20260614T010203Z"
            run_dir.mkdir(parents=True)
            (run_dir / "summary.json").write_text(
                json.dumps({"symbol": "BTCUSDT", "final_balance": 10100}),
                encoding="utf-8",
            )

            runs = list_runs(Path(tmp))

            self.assertEqual(runs[0]["mode"], "backtest")
            self.assertEqual(runs[0]["symbol"], "BTCUSDT")

    def test_load_run_details_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                load_run_details("../outside", output_root=Path(tmp))

    def test_live_chart_payload_returns_candles_and_strategy_signals(self):
        client = FakeClient()
        client.candles = trending_candles()

        payload = live_chart_payload(
            {
                "symbol": "BTCUSDT",
                "interval": "1h",
                "limit": 12,
                "fast_ema": 1,
                "slow_ema": 3,
                "rsi_period": 2,
                "rsi_overbought": 100,
                "rsi_oversold": 0,
            },
            client=client,
        )

        self.assertEqual(payload["symbol"], "BTCUSDT")
        self.assertEqual(len(payload["candles"]), 12)
        signal_types = {marker["type"] for marker in payload["signals"]}
        self.assertIn("long_signal", signal_types)
        self.assertIn("short_signal", signal_types)

    def test_live_chart_payload_uses_selected_strategy_for_markers(self):
        client = FakeClient()
        client.candles = [candle(index, price) for index, price in enumerate([10, 9, 8, 9, 11, 13, 15])]

        payload = live_chart_payload(
            {
                "symbol": "BTCUSDT",
                "interval": "1h",
                "limit": 7,
                "strategy": "macd",
                "fast_ema": 2,
                "slow_ema": 5,
                "macd_signal": 2,
            },
            client=client,
        )

        self.assertTrue(
            any(marker["reason"].startswith("macd_") for marker in payload["signals"])
        )

    def test_live_chart_payload_can_overlay_all_strategy_signals(self):
        client = FakeClient()
        client.candles = [candle(index, price) for index, price in enumerate([10, 9, 8, 9, 11, 13, 15])]

        payload = live_chart_payload(
            {
                "symbol": "BTCUSDT",
                "interval": "1h",
                "limit": 7,
                "strategy": "all",
                "fast_ema": 2,
                "slow_ema": 5,
                "macd_signal": 2,
                "rsi_period": 2,
                "rsi_overbought": 100,
                "rsi_oversold": 0,
                "rsi_midline": 50,
                "bollinger_period": 3,
                "bollinger_stddev": 1,
                "donchian_period": 3,
                "atr_period": 2,
                "supertrend_multiplier": 1,
                "vwap_period": 3,
                "vwap_threshold_pct": 0,
                "stoch_rsi_period": 2,
                "stoch_rsi_oversold": 20,
                "stoch_rsi_overbought": 80,
                "ema_ribbon_fast": 2,
                "ema_ribbon_mid": 3,
                "ema_ribbon_slow": 5,
                "momentum_period": 2,
            },
            client=client,
        )

        strategy_names = {
            str(marker["reason"]).split(": ", 1)[0] for marker in payload["signals"]
        }
        self.assertEqual(client.kline_symbols, ["BTCUSDT"])
        self.assertIn("ema-rsi", strategy_names)
        self.assertIn("macd", strategy_names)
        self.assertIn("supertrend", strategy_names)
        self.assertIn("momentum-scalping", strategy_names)
        self.assertEqual(payload["strategy"], "all")

    def test_live_chart_payload_retries_transient_market_data_failures(self):
        client = FlakyLiveClient()
        client.candles = trending_candles()

        payload = live_chart_payload(
            {
                "symbol": "BTCUSDT",
                "interval": "1h",
                "limit": 12,
                "market_data_retries": 1,
                "retry_delay": 0,
                "fast_ema": 1,
                "slow_ema": 3,
                "rsi_period": 2,
                "rsi_overbought": 100,
                "rsi_oversold": 0,
            },
            client=client,
        )

        self.assertEqual(len(client.kline_symbols), 1)
        self.assertEqual(payload["symbol"], "BTCUSDT")
        self.assertEqual(len(payload["candles"]), 12)

    def test_paper_trade_markers_reads_entry_and_exit_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "paper" / "run-a"
            run_dir.mkdir(parents=True)
            (run_dir / "trades.csv").write_text(
                "\n".join(
                    [
                        "side,entry_time,exit_time,entry_price,exit_price,quantity,realized_pnl,fees,slippage,entry_reason,exit_reason",
                        "long,2,5,10,13,1,3,0,0,ema_cross_above,take_profit",
                        "short,7,9,12,9,1,3,0,0,ema_cross_below,ema_cross_above",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            markers = paper_trade_markers("BTCUSDT", 0, 10, Path(tmp))

            self.assertEqual(
                [marker["type"] for marker in markers],
                [
                    "paper_entry_long",
                    "paper_exit_long",
                    "paper_entry_short",
                    "paper_exit_short",
                ],
            )


if __name__ == "__main__":
    unittest.main()
