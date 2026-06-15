import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from algo_trading.auth import InMemoryAuthStore, utcnow
import algo_trading.ui as ui
from algo_trading.data import (
    BinanceMarketDataClient,
    TransientMarketDataError,
    YahooFuturesMarketDataClient,
)
from algo_trading.models import Candle
from algo_trading.ui import (
    is_frontend_route,
    is_vite_asset_route,
    load_run_details,
    list_runs,
    live_chart_payload,
    market_data_client_from_payload,
    paper_trade_markers,
    run_backtest_payload,
    strategies_payload,
    strategy_lab_csv,
    strategy_lab_payload,
    top_symbols_payload,
)
from algo_trading.web_app import create_app


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
        self.assertIn("const liveMarketOptions = computed<SelectOption[]>(() => [", source)
        self.assertIn("const liveSymbolsByMarket", source)
        self.assertIn("const liveIntervalOptions = [", source)
        self.assertIn("const liveCandleOptions = [", source)
        self.assertIn("const liveStrategyOptions = computed(() => [", source)
        self.assertIn('name: "all"', source)
        self.assertIn('t("options.allStrategies")', source)
        self.assertIn('value: "crypto_spot"', source)
        self.assertIn('t("options.cryptoSpot")', source)
        self.assertIn('value: "cme_futures"', source)
        self.assertIn('t("options.usIndexFutures")', source)
        self.assertIn('value: "ES=F"', source)
        self.assertIn('t("options.sp500Future")', source)
        self.assertIn('<select v-model="liveMarket"', source)
        self.assertIn('<select v-model="liveSymbol"', source)
        self.assertIn('<select v-model="liveInterval"', source)
        self.assertIn('const liveInterval = ref("5m");', source)
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

    def test_live_crypto_spot_symbols_are_limited_to_btc_and_eth(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")
        options_source = source.split("const liveSymbolOptions = [", 1)[1].split(
            "] satisfies SelectOption[];",
            1,
        )[0]

        self.assertIn('value: "BTCUSDT"', options_source)
        self.assertIn('value: "ETHUSDT"', options_source)
        self.assertNotIn('value: "SOLUSDT"', options_source)
        self.assertNotIn('value: "BNBUSDT"', options_source)
        self.assertNotIn('value: "XRPUSDT"', options_source)
        self.assertNotIn('value: "DOGEUSDT"', options_source)
        self.assertNotIn('value: "ADAUSDT"', options_source)
        self.assertNotIn('value: "AVAXUSDT"', options_source)

    def test_live_market_selector_changes_auto_refresh_chart(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")

        self.assertIn('import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";', source)
        self.assertIn("watch([liveMarket, liveSymbol, liveInterval, liveLimit, () => settings.strategy], () => {", source)
        self.assertIn('if (activeMode.value === "live") {', source)
        self.assertIn("refreshLiveChart();", source)
        self.assertIn("market: liveMarket.value", source)

    def test_live_chart_refresh_preserves_user_zoom(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        chart_source = (
            root / "frontend" / "src" / "components" / "TradingViewChart.vue"
        ).read_text(encoding="utf-8")

        self.assertIn(':reset-key="liveChartResetKey"', app_source)
        self.assertIn("const liveChartResetKey = computed", app_source)
        self.assertIn("resetKey: string;", chart_source)
        self.assertIn("let shouldFitContent = true;", chart_source)
        self.assertIn("watch(() => props.resetKey", chart_source)
        self.assertIn("shouldFitContent = true;", chart_source)
        self.assertIn("if (shouldFitContent) {", chart_source)
        self.assertIn("timeScale?.fitContent();", chart_source)
        self.assertIn("shouldFitContent = false;", chart_source)
        self.assertIn("getVisibleLogicalRange()", chart_source)
        self.assertIn("setVisibleLogicalRange(visibleRange)", chart_source)

    def test_all_strategies_selection_stays_live_only(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")

        self.assertIn('if (nextMode !== "live" && settings.strategy === "all") {', source)
        self.assertIn('settings.strategy = "ema-rsi";', source)

    def test_frontend_keeps_trading_modes_plus_account_management_modes(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        types_source = (root / "frontend" / "src" / "types.ts").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'export type Mode = "live" | "breadth" | "lab" | "profile" | "admin";',
            types_source,
        )
        self.assertIn('"/": "lab"', source)
        self.assertIn('"/profile": "profile"', source)
        self.assertIn('"/admin": "admin"', source)
        self.assertIn('return routeModes[window.location.pathname] ?? "lab";', source)
        self.assertIn('{ mode: "lab" as const, label: t("tabs.lab") }', source)
        self.assertIn('{ mode: "live" as const, label: t("tabs.live") }', source)
        self.assertIn('{ mode: "breadth" as const, label: t("tabs.breadth") }', source)
        self.assertIn('{ mode: "profile" as const, label: t("tabs.profile") }', source)
        self.assertIn('{ mode: "admin" as const, label: t("tabs.admin") }', source)
        self.assertNotIn('{ mode: "backtest" as const', source)
        self.assertNotIn('{ mode: "paper" as const', source)
        self.assertNotIn('{ mode: "combos" as const', source)
        self.assertNotIn('{ mode: "runs" as const', source)
        self.assertNotIn('"tabs.backtest"', i18n_source)
        self.assertNotIn('"tabs.paper"', i18n_source)
        self.assertNotIn('"tabs.combos"', i18n_source)
        self.assertNotIn('"tabs.runs"', i18n_source)

    def test_removed_frontend_pages_do_not_keep_client_functions(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")

        self.assertNotIn("activeMode === 'backtest'", source)
        self.assertNotIn("activeMode === 'paper'", source)
        self.assertNotIn('activeMode === "runs"', source)
        self.assertNotIn('activeMode === "combos"', source)
        self.assertNotIn("async function runCurrentMode()", source)
        self.assertNotIn("async function runCombinationSignals()", source)
        self.assertNotIn("async function loadRuns()", source)
        self.assertNotIn("async function loadRunDetails(", source)
        self.assertNotIn("/api/backtest", source)
        self.assertNotIn("/api/paper", source)
        self.assertNotIn("/api/combination-signals", source)
        self.assertNotIn("/api/runs", source)
        self.assertNotIn("/api/run?", source)

    def test_frontend_exposes_market_breadth_page(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        types_source = (root / "frontend" / "src" / "types.ts").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn('"/breadth": "breadth"', source)
        self.assertIn('breadth: "/breadth"', source)
        self.assertIn('{ mode: "breadth" as const, label: t("tabs.breadth") }', source)
        self.assertIn("const breadthPayload = ref<MarketBreadthPayload | null>(null);", source)
        self.assertIn("async function loadMarketBreadth()", source)
        self.assertIn('requestJson<MarketBreadthPayload>("/api/market-breadth")', source)
        self.assertIn('activeMode === "breadth"', source)
        self.assertIn('class="breadth-grid"', source)
        self.assertIn('v-for="group in breadthGroups"', source)
        self.assertIn('v-for="item in group.items"', source)
        self.assertIn('breadthPayload?.series[item.symbol]', source)
        self.assertIn('export type MarketBreadthPayload', types_source)
        self.assertIn('"tabs.breadth": "Breadth"', i18n_source)
        self.assertIn('"tabs.breadth": "Ширина"', i18n_source)

    def test_frontend_defines_bilingual_i18n_contract(self):
        root = Path(__file__).resolve().parents[1]
        i18n_path = root / "frontend" / "src" / "i18n.ts"
        self.assertTrue(i18n_path.exists())
        i18n_source = i18n_path.read_text(encoding="utf-8")
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )

        self.assertIn('export type Locale = "en" | "ru";', i18n_source)
        self.assertIn("SUPPORTED_LOCALES", i18n_source)
        self.assertIn('flag: "🇺🇸"', i18n_source)
        self.assertIn('flag: "🇷🇺"', i18n_source)
        self.assertIn('LOCALE_STORAGE_KEY = "algoTradingLocale"', i18n_source)
        self.assertIn("export const messages", i18n_source)
        self.assertIn("en:", i18n_source)
        self.assertIn("ru:", i18n_source)
        self.assertIn("strategyDescriptions", i18n_source)
        self.assertIn("translateStrategyDescription", i18n_source)
        self.assertIn("setLocale", app_source)
        self.assertIn("localStorage.setItem(LOCALE_STORAGE_KEY", app_source)
        self.assertIn('class="language-switcher"', app_source)
        self.assertIn("SUPPORTED_LOCALES", app_source)

    def test_frontend_exposes_auth_shell_and_session_calls(self):
        root = Path(__file__).resolve().parents[1]
        api_source = (root / "frontend" / "src" / "api.ts").read_text(
            encoding="utf-8"
        )
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )
        types_source = (root / "frontend" / "src" / "types.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn('credentials: "same-origin"', api_source)
        self.assertIn("export type AuthUser", types_source)
        self.assertIn('is_active: boolean;', types_source)
        self.assertIn('activated_at: string | null;', types_source)
        self.assertIn('expired_at: string | null;', types_source)
        self.assertIn('export type AdminUsersPayload', types_source)
        self.assertIn("const authChecked = ref(false);", app_source)
        self.assertIn("const authUser = ref<AuthUser | null>(null);", app_source)
        self.assertIn('const adminUsers = ref<AuthUser[]>([]);', app_source)
        self.assertIn('const authMode = ref<"login" | "register">("login");', app_source)
        self.assertIn("const authForm = reactive", app_source)
        self.assertIn('const canUseFeatures = computed(() => Boolean(authUser.value?.is_active));', app_source)
        self.assertIn('authUser.value?.username === "cuiyeqing960904@gmail.com"', app_source)
        self.assertIn("async function loadCurrentUser()", app_source)
        self.assertIn('requestJson<AuthMePayload>("/api/auth/me")', app_source)
        self.assertIn('requestJson<AuthMePayload>("/api/profile")', app_source)
        self.assertIn('requestJson<AdminUsersPayload>("/api/admin/users")', app_source)
        self.assertIn("async function submitAuth()", app_source)
        self.assertIn('authMode.value === "login" ? "/api/auth/login" : "/api/auth/register"', app_source)
        self.assertIn("async function logout()", app_source)
        self.assertIn('requestJson<{ ok: true }>("/api/auth/logout"', app_source)
        self.assertIn('class="auth-shell"', app_source)
        self.assertIn("profile-panel", app_source)
        self.assertIn("admin-panel", app_source)
        self.assertIn('t("auth.inactive")', app_source)
        self.assertIn('"tabs.profile"', i18n_source)
        self.assertIn('"tabs.admin"', i18n_source)
        self.assertIn('"auth.inactive"', i18n_source)
        self.assertIn('@submit.prevent="submitAuth"', app_source)
        self.assertIn('@click="logout"', app_source)
        self.assertIn('t("auth.login")', app_source)
        self.assertIn('t("auth.register")', app_source)
        self.assertIn('"auth.username"', i18n_source)
        self.assertIn('"auth.password"', i18n_source)
        self.assertIn('"auth.logout"', i18n_source)

    def test_chart_accepts_translated_labels_from_parent(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        chart_source = (
            root / "frontend" / "src" / "components" / "TradingViewChart.vue"
        ).read_text(encoding="utf-8")

        self.assertIn("ariaLabel?: string;", chart_source)
        self.assertIn("emptyLabel?: string;", chart_source)
        self.assertIn("paperEntryLabel?: string;", chart_source)
        self.assertIn("paperExitLabel?: string;", chart_source)
        self.assertIn("longSignalLabel?: string;", chart_source)
        self.assertIn("shortSignalLabel?: string;", chart_source)
        self.assertIn(':aria-label="chartLabels.aria"', app_source)
        self.assertIn(':empty-label="chartLabels.empty"', app_source)
        self.assertIn(':paper-entry-label="chartLabels.paperEntry"', app_source)
        self.assertIn(':paper-exit-label="chartLabels.paperExit"', app_source)
        self.assertIn(':long-signal-label="chartLabels.longSignal"', app_source)
        self.assertIn(':short-signal-label="chartLabels.shortSignal"', app_source)

    def test_live_all_strategy_view_collapses_markers_by_consensus(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")

        self.assertIn('type SignalDisplayMode = "consensus" | "individual";', source)
        self.assertIn(
            'const liveSignalDisplayMode = ref<SignalDisplayMode>("consensus");',
            source,
        )
        self.assertIn("const liveConsensusMinConfirmations = ref(2);", source)
        self.assertIn(
            "const liveSignalDisplayOptions = computed<SelectOption[]>(() => [",
            source,
        )
        self.assertIn('t("options.consensusSignals")', source)
        self.assertIn('t("options.individualSignals")', source)
        self.assertIn("const consensusSignals = computed", source)
        self.assertIn("const displayedSignals = computed", source)
        self.assertIn('settings.strategy !== "all"', source)
        self.assertIn("liveConsensusMinConfirmations.value", source)
        self.assertIn("groupSignalsByConsensus", source)
        self.assertIn("formatConsensusReason", source)
        self.assertIn(':signals="displayedSignals"', source)
        self.assertIn('v-model="liveSignalDisplayMode"', source)
        self.assertIn('v-model.number="liveConsensusMinConfirmations"', source)
        reset_key_source = source.split("const liveChartResetKey = computed", 1)[1].split(
            ");",
            1,
        )[0]
        self.assertNotIn("liveSignalDisplayMode.value", reset_key_source)
        self.assertNotIn("liveConsensusMinConfirmations.value", reset_key_source)

    def test_live_page_does_not_show_paper_trade_markers(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")
        live_section = source.split(
            '<section v-if="activeMode === \'live\'" class="panel live-panel">',
            1,
        )[1].split(
            "<section v-else-if='activeMode === \"breadth\"' class=\"panel breadth-panel\">",
            1,
        )[0]

        self.assertNotIn('t("labels.paper")', live_section)
        self.assertNotIn("livePaperMarkerCount", live_section)
        self.assertNotIn('v-model="showPaper"', live_section)
        self.assertNotIn('t("labels.paperMarkers")', live_section)
        self.assertNotIn("paper-entry", live_section)
        self.assertNotIn("paper-exit", live_section)
        self.assertNotIn('t("chart.paperEntryLegend")', live_section)
        self.assertNotIn('t("chart.paperExitLegend")', live_section)
        self.assertNotIn(':paper-markers="filteredPaperMarkers"', live_section)
        self.assertNotIn(':show-paper="showPaper"', live_section)
        self.assertIn(':paper-markers="[]"', live_section)
        self.assertIn(':show-paper="false"', live_section)

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
        self.assertTrue(is_frontend_route("/live"))
        self.assertTrue(is_frontend_route("/chart"))
        self.assertTrue(is_frontend_route("/breadth"))
        self.assertTrue(is_frontend_route("/lab"))
        self.assertTrue(is_frontend_route("/profile"))
        self.assertTrue(is_frontend_route("/admin"))
        self.assertFalse(is_frontend_route("/backtest"))
        self.assertFalse(is_frontend_route("/paper"))
        self.assertFalse(is_frontend_route("/runs"))
        self.assertFalse(is_frontend_route("/history"))
        self.assertFalse(is_frontend_route("/combos"))

    def test_frontend_routes_do_not_capture_api_or_unknown_paths(self):
        self.assertFalse(is_frontend_route("/api/runs"))
        self.assertFalse(is_frontend_route("/styles.css"))
        self.assertFalse(is_frontend_route("/unknown"))

    def test_vite_asset_routes_are_restricted_to_assets_directory(self):
        self.assertTrue(is_vite_asset_route("/assets/index.js"))
        self.assertTrue(is_vite_asset_route("/assets/index.css"))
        self.assertFalse(is_vite_asset_route("/api/runs"))
        self.assertFalse(is_vite_asset_route("/assets/../index.html"))

    def test_tradingview_chart_resizes_to_rendered_container_height(self):
        chart_source = (
            Path(__file__).resolve().parents[1]
            / "frontend"
            / "src"
            / "components"
            / "TradingViewChart.vue"
        ).read_text(encoding="utf-8")

        self.assertIn("const DEFAULT_CHART_HEIGHT = 560;", chart_source)
        self.assertIn("function chartHeight(): number", chart_source)
        self.assertIn("return chartEl.value?.clientHeight || DEFAULT_CHART_HEIGHT;", chart_source)
        self.assertIn("height: chartHeight(),", chart_source)
        self.assertIn("chart.value?.resize(chartEl.value.clientWidth, chartHeight());", chart_source)
        self.assertNotIn("chart.value?.resize(chartEl.value.clientWidth, 560);", chart_source)

    def test_breadth_page_uses_stacked_readable_group_layout(self):
        style_source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "style.css"
        ).read_text(encoding="utf-8")

        self.assertIn(".breadth-grid {\n  display: grid;\n  grid-template-columns: minmax(0, 1fr);", style_source)
        self.assertIn("padding: 14px;", style_source)
        self.assertIn(".breadth-group {\n  display: grid;\n  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));", style_source)
        self.assertIn("grid-column: 1 / -1;", style_source)
        self.assertIn(".breadth-card .tv-chart {\n  height: 220px;", style_source)

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
        self.assertIn("sma-crossover", strategy_names)
        self.assertIn("combined-signals", strategy_names)
        self.assertTrue(all(strategy["description"] for strategy in payload["strategies"]))

    def test_combination_signals_payload_returns_summary_and_markers(self):
        client = FakeClient()
        client.candles = [
            candle(index, price)
            for index, price in enumerate([10, 9, 8, 9, 11, 13, 15])
        ]

        payload = ui.combination_signals_payload(
            {
                "symbol": "BTCUSDT",
                "interval": "1h",
                "limit": 7,
                "fast_ema": 2,
                "slow_ema": 5,
                "rsi_period": 2,
                "rsi_overbought": 100,
                "macd_signal": 2,
                "combo_strategies": "ema-rsi,macd",
                "combo_entry_confirmations": 2,
                "combo_exit_confirmations": 2,
                "combo_lookback": 2,
                "fee_rate": 0,
                "slippage_rate": 0,
                "stop_loss_pct": 1,
                "take_profit_pct": 1,
            },
            client=client,
        )

        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["mode"], "combination-signals")
        self.assertEqual(payload["config"]["strategy"], "combined-signals")
        self.assertEqual(payload["config"]["combo_strategies"], "ema-rsi,macd")
        self.assertIn("final_balance", payload["summary"])
        self.assertTrue(
            any(
                marker["reason"] == "combined_long:2/2:ema-rsi,macd"
                for marker in payload["signals"]
            )
        )

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
        strategy_rows = [
            row for row in payload["rows"] if row["strategy"] in {"ema-rsi", "macd"}
        ]
        self.assertEqual(len(strategy_rows), 2)
        self.assertEqual(payload["rows"][0]["rank"], 1)
        returns = [row["total_return_pct"] for row in payload["rows"]]
        self.assertEqual(returns, sorted(returns, reverse=True))

    def test_strategy_lab_payload_accepts_combined_signals(self):
        client = FakeClient()
        client.candles = [
            candle(index, price)
            for index, price in enumerate([10, 9, 8, 9, 11, 13, 15])
        ]

        payload = strategy_lab_payload(
            {
                "symbols": "BTCUSDT",
                "strategies": "combined-signals",
                "presets": "custom",
                "interval": "1h",
                "limit": 7,
                "fast_ema": 2,
                "slow_ema": 5,
                "rsi_period": 2,
                "rsi_overbought": 100,
                "macd_signal": 2,
                "combo_strategies": "ema-rsi,macd",
                "combo_entry_confirmations": 2,
                "combo_exit_confirmations": 2,
                "combo_lookback": 2,
                "fee_rate": 0,
                "slippage_rate": 0,
                "stop_loss_pct": 1,
                "take_profit_pct": 1,
            },
            client=client,
        )

        strategy_rows = [
            row for row in payload["rows"] if row["strategy"] == "combined-signals"
        ]
        self.assertEqual(len(strategy_rows), 1)

    def test_strategy_lab_payload_adds_buy_and_hold_benchmark_row(self):
        client = FakeClient()
        client.candles = trending_candles()

        payload = strategy_lab_payload(
            {
                "symbols": "BTCUSDT",
                "strategies": "ema-rsi",
                "presets": "custom",
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

        benchmark = next(
            row for row in payload["rows"] if row["strategy"] == "buy-and-hold"
        )
        expected_return = ((client.candles[-1].close / client.candles[0].close) - 1.0) * 100.0
        self.assertEqual(benchmark["symbol"], "BTCUSDT")
        self.assertEqual(benchmark["preset"], "benchmark")
        self.assertEqual(benchmark["trades"], 0)
        self.assertEqual(benchmark["total_return_pct"], round(expected_return, 8))

    def test_strategy_lab_payload_adds_market_benchmark_symbols(self):
        client = FakeClient()
        futures_client = FakeClient()
        client.candles = trending_candles()
        futures_client.candles = [
            candle(index, price) for index, price in enumerate([100, 101, 102, 103])
        ]

        payload = strategy_lab_payload(
            {
                "symbols": "BTCUSDT",
                "benchmark_symbols": "SP500,NASDAQ",
                "strategies": "ema-rsi",
                "presets": "custom",
                "interval": "1h",
                "limit": 12,
                "fast_ema": 1,
                "slow_ema": 3,
                "rsi_period": 2,
                "rsi_overbought": 100,
                "rsi_oversold": 0,
            },
            client=client,
            benchmark_client=futures_client,
        )

        benchmark_symbols = {
            row["symbol"]
            for row in payload["rows"]
            if row["strategy"] == "buy-and-hold"
        }
        self.assertIn("SP500", benchmark_symbols)
        self.assertIn("NASDAQ", benchmark_symbols)
        self.assertEqual(futures_client.kline_symbols, ["SP500", "NASDAQ"])

    def test_strategy_lab_payload_adds_walk_forward_metrics(self):
        client = FakeClient()
        client.candles = trending_candles()

        payload = strategy_lab_payload(
            {
                "symbols": "BTCUSDT",
                "strategies": "ema-rsi",
                "presets": "custom",
                "interval": "1h",
                "limit": 12,
                "fast_ema": 1,
                "slow_ema": 3,
                "rsi_period": 2,
                "rsi_overbought": 100,
                "rsi_oversold": 0,
                "walk_forward_windows": 2,
                "walk_forward_min_candles": 4,
            },
            client=client,
        )

        strategy_row = next(row for row in payload["rows"] if row["strategy"] == "ema-rsi")
        self.assertEqual(strategy_row["walk_forward_windows"], 2)
        self.assertIn("walk_forward_avg_return_pct", strategy_row)
        self.assertIn("walk_forward_worst_return_pct", strategy_row)
        self.assertIn("walk_forward_best_return_pct", strategy_row)
        self.assertIn("walk_forward_profitable_pct", strategy_row)

    def test_strategy_lab_csv_exports_ranked_rows(self):
        csv_text = strategy_lab_csv(
            [
                {
                    "rank": 1,
                    "symbol": "BTC,USDT",
                    "strategy": "buy-and-hold",
                    "preset": "benchmark",
                    "final_balance": 11000.0,
                    "total_return_pct": 10.0,
                    "max_drawdown_pct": 2.0,
                    "trades": 0,
                    "win_rate": 0.0,
                    "profit_factor": 0.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.4,
                    "max_drawdown_duration": 2,
                    "average_trade_duration": 0.0,
                    "exposure_pct": 100.0,
                    "worst_trade": 0.0,
                    "walk_forward_windows": 2,
                    "walk_forward_avg_return_pct": 5.0,
                    "walk_forward_worst_return_pct": -1.0,
                    "walk_forward_best_return_pct": 11.0,
                    "walk_forward_profitable_pct": 50.0,
                }
            ]
        )

        lines = csv_text.splitlines()
        self.assertTrue(lines[0].startswith("rank,symbol,strategy,preset"))
        self.assertIn('"BTC,USDT"', lines[1])
        self.assertIn("walk_forward_profitable_pct", lines[0])

    def test_strategy_lab_frontend_exposes_validation_and_csv_controls(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")

        self.assertIn("labBenchmarkSymbols", source)
        self.assertIn("walk_forward_windows", source)
        self.assertIn("exportLabCsv", source)
        self.assertIn("strategy-lab.csv", source)
        self.assertIn('t("actions.exportCsv")', source)

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
                    "strategy": "keltner-breakout",
                    "atr_period": 3,
                    "keltner_multiplier": 0.5,
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
            config_path = sorted(Path(tmp).glob("backtests/*/config.json"))[0]
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(config["strategy"], "keltner-breakout")
            self.assertEqual(config["keltner_multiplier"], 0.5)

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

    def test_live_chart_payload_accepts_sp500_future_with_all_strategy_signals(self):
        client = FakeClient()
        client.candles = [candle(index, price) for index, price in enumerate([10, 9, 8, 9, 11, 13, 15])]

        payload = live_chart_payload(
            {
                "market": "cme_futures",
                "symbol": "ES=F",
                "interval": "5m",
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
        self.assertEqual(client.kline_symbols, ["ES=F"])
        self.assertEqual(payload["market"], "cme_futures")
        self.assertEqual(payload["symbol"], "ES=F")
        self.assertEqual(payload["strategy"], "all")
        self.assertIn("ema-rsi", strategy_names)
        self.assertIn("macd", strategy_names)

    def test_market_data_client_from_payload_selects_futures_provider(self):
        self.assertIsInstance(
            market_data_client_from_payload({"market": "cme_futures"}),
            YahooFuturesMarketDataClient,
        )
        self.assertIsInstance(
            market_data_client_from_payload({"market": "crypto_spot"}),
            BinanceMarketDataClient,
        )

    def test_live_chart_route_uses_market_provider_from_query(self):
        client = FakeClient()
        client.candles = [
            candle(index, price)
            for index, price in enumerate([10, 9, 8, 9, 11, 13, 15])
        ]

        with tempfile.TemporaryDirectory() as tmp:
            with patch("algo_trading.ui.YahooFuturesMarketDataClient", return_value=client):
                auth_store = InMemoryAuthStore()
                http = TestClient(
                    create_app(
                        output_root=Path(tmp),
                        auth_store=auth_store,
                    )
                )
                http.post(
                    "/api/auth/register",
                    json={"username": "alice", "password": "password123"},
                )
                auth_store.set_user_access(
                    auth_store.list_users()[0].id,
                    is_active=True,
                    activated_at=utcnow(),
                )
                response = http.get(
                    "/api/live-chart"
                    "?market=cme_futures&symbol=ES%3DF&interval=5m&limit=7"
                    "&strategy=all&fast_ema=2&slow_ema=5&macd_signal=2"
                    "&rsi_period=2&rsi_overbought=100&rsi_oversold=0"
                    "&bollinger_period=3&donchian_period=3&atr_period=2"
                    "&vwap_period=3&stoch_rsi_period=2"
                    "&ema_ribbon_fast=2&ema_ribbon_mid=3&ema_ribbon_slow=5"
                    "&momentum_period=2"
                )
                payload = response.json()

        self.assertEqual(payload["market"], "cme_futures")
        self.assertEqual(payload["symbol"], "ES=F")
        self.assertEqual(client.kline_symbols, ["ES=F"])

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
