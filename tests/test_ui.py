import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from algo_trading.auth import InMemoryAuthStore, utcnow
import algo_trading.ui as ui
from algo_trading.data import (
    BinanceMarketDataClient,
    MoexSharesMarketDataClient,
    TransientMarketDataError,
    YahooFuturesMarketDataClient,
)
from algo_trading.models import Candle
from algo_trading.ui import (
    is_frontend_route,
    is_vite_asset_route,
    live_chart_payload,
    market_data_client_from_payload,
    strategies_payload,
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
        self.assertIn("const liveStrategyOptions = computed<StrategyOption[]>(() =>", source)
        self.assertIn("const liveSelectedStrategies = ref<string[]>([\"ema-rsi\"]);", source)
        self.assertIn("const liveStrategyRequest = computed(() =>", source)
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
        self.assertIn('class="strategy-picker live-strategy-field"', source)
        self.assertIn("toggleLiveStrategy(strategy.name)", source)
        self.assertIn('v-for="group in liveStrategyGroups"', source)
        self.assertIn('value: "BTCUSDT"', source)
        self.assertIn('value: "ETHUSDT"', source)
        self.assertIn('value: "1m"', source)
        self.assertIn('value: "1h"', source)
        self.assertIn("value: 180", source)
        self.assertIn("value: 500", source)

    def test_live_page_uses_strategy_multiselect(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")

        self.assertIn('class="strategy-picker live-strategy-field"', source)
        self.assertIn('<summary class="strategy-summary">', source)
        self.assertIn("selectedLiveStrategyPreview", source)
        self.assertIn("const liveStrategyGroups = computed<StrategyGroup[]>(() =>", source)
        self.assertIn("const strategyGroupCatalog", source)
        self.assertIn("toggleLiveStrategy(strategy.name)", source)
        self.assertIn("selectLiveStrategyGroup(group.strategyNames)", source)
        self.assertIn("selectAllLiveStrategies", source)
        self.assertIn("clearLiveStrategies", source)
        self.assertIn(":checked=\"liveSelectedStrategies.includes(strategy.name)\"", source)
        self.assertIn("strategy: liveStrategyRequest.value", source)
        self.assertIn("watch([liveMarket, liveSymbol, liveInterval, liveLimit, liveStrategyRequest], () => {", source)
        self.assertNotIn('<select v-model="settings.strategy"', source)

    def test_frontend_defines_human_strategy_titles_and_groups(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("translateStrategyTitle", app_source)
        self.assertIn("strategyTitle(strategy.name)", app_source)
        self.assertIn("strategyTitles", i18n_source)
        self.assertIn("translateStrategyTitle", i18n_source)
        self.assertIn('"strategyGroups.recommended": "Recommended"', i18n_source)
        self.assertIn('"strategyGroups.trend": "Trend following"', i18n_source)
        self.assertIn('"strategyGroups.reversal": "Mean reversion"', i18n_source)
        self.assertIn('"strategyGroups.breakout": "Breakout"', i18n_source)
        self.assertIn('"strategyGroups.volume": "Volume confirmation"', i18n_source)
        self.assertIn('"labels.strategyPickerHint": "Pick one preset or combine strategies by group."', i18n_source)
        self.assertIn('"strategyGroups.recommended": "Рекомендуемые"', i18n_source)
        self.assertIn('"labels.strategyPickerHint": "Выберите пресет или соберите набор по группам."', i18n_source)

    def test_live_page_exposes_popular_indicator_controls(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        chart_source = (
            root / "frontend" / "src" / "components" / "TradingViewChart.vue"
        ).read_text(encoding="utf-8")
        types_source = (root / "frontend" / "src" / "types.ts").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )

        for indicator_id in (
            "sma",
            "ema",
            "bollinger",
            "vwap",
            "donchian",
            "volume",
            "rsi",
            "macd",
            "atr",
            "stoch-rsi",
        ):
            self.assertIn(f'value: "{indicator_id}"', app_source)

        self.assertIn("const liveVisibleIndicators = ref<string[]>([", app_source)
        self.assertIn("const visibleLiveIndicators = computed<IndicatorDefinition[]>(() =>", app_source)
        self.assertIn('class="indicator-picker"', app_source)
        self.assertIn("toggleLiveIndicator(String(option.value))", app_source)
        self.assertIn(':indicators="visibleLiveIndicators"', app_source)
        self.assertIn('"labels.indicators": "Indicators"', i18n_source)
        self.assertIn("export type IndicatorDefinition", types_source)
        self.assertIn("indicators: IndicatorDefinition[];", types_source)
        self.assertIn("LineSeries", chart_source)
        self.assertIn("HistogramSeries", chart_source)
        self.assertIn("syncIndicatorSeries", chart_source)
        self.assertIn("paneIndexForIndicator", chart_source)

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
        self.assertIn("watch([liveMarket, liveSymbol, liveInterval, liveLimit, liveStrategyRequest], () => {", source)
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

        self.assertIn('if (nextMode !== "live") {', source)
        self.assertIn("resetLiveStrategies();", source)

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
            'export type Mode = "live" | "breadth" | "profile" | "admin";',
            types_source,
        )
        self.assertIn('"/": "live"', source)
        self.assertNotIn('"/lab": "lab"', source)
        self.assertIn('"/profile": "profile"', source)
        self.assertIn('"/admin": "admin"', source)
        self.assertIn('return routeModes[window.location.pathname] ?? "live";', source)
        self.assertNotIn('{ mode: "lab" as const, label: t("tabs.lab") }', source)
        self.assertIn('{ mode: "live" as const, label: t("tabs.live") }', source)
        self.assertIn('{ mode: "breadth" as const, label: t("tabs.breadth") }', source)
        self.assertIn('{ mode: "profile" as const, label: t("tabs.profile") }', source)
        self.assertIn('{ mode: "admin" as const, label: t("tabs.admin") }', source)
        self.assertNotIn('"tabs.lab"', i18n_source)
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
        self.assertNotIn('activeMode === "lab"', source)
        self.assertNotIn("async function runCurrentMode()", source)
        self.assertNotIn("async function runCombinationSignals()", source)
        self.assertNotIn("async function runStrategyLab()", source)
        self.assertNotIn("function exportLabCsv()", source)
        self.assertNotIn("async function loadRuns()", source)
        self.assertNotIn("async function loadRunDetails(", source)
        self.assertNotIn("/api/backtest", source)
        self.assertNotIn("/api/paper", source)
        self.assertNotIn("/api/combination-signals", source)
        self.assertNotIn("/api/strategy-lab", source)
        self.assertNotIn("/api/runs", source)
        self.assertNotIn("/api/run?", source)
        self.assertNotIn("labRows", source)
        self.assertNotIn("labSymbols", source)
        self.assertNotIn("labPresets", source)
        self.assertNotIn("StrategyLabPayload", source)

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
        self.assertIn('is_admin: boolean;', types_source)
        self.assertIn('first_name: string | null;', types_source)
        self.assertIn('last_name: string | null;', types_source)
        self.assertIn('middle_name: string | null;', types_source)
        self.assertIn('export type AdminUsersPayload', types_source)
        self.assertIn("const authChecked = ref(false);", app_source)
        self.assertIn("const authUser = ref<AuthUser | null>(null);", app_source)
        self.assertIn("const profileForm = reactive", app_source)
        self.assertIn('const adminUsers = ref<AuthUser[]>([]);', app_source)
        self.assertIn('const adminSearch = ref("");', app_source)
        self.assertIn("const filteredAdminUsers = computed", app_source)
        self.assertIn("user.username.toLowerCase().includes(query)", app_source)
        self.assertIn('const authMode = ref<"login" | "register">("login");', app_source)
        self.assertIn("const authForm = reactive", app_source)
        self.assertIn('const canUseFeatures = computed(() => Boolean(authUser.value?.is_active));', app_source)
        self.assertIn('authUser.value?.is_admin === true', app_source)
        self.assertNotIn('authUser.value?.username === "cuiyeqing960904@gmail.com"', app_source)
        self.assertIn("async function loadCurrentUser()", app_source)
        self.assertIn('requestJson<AuthMePayload>("/api/auth/me")', app_source)
        self.assertIn('requestJson<AuthMePayload>("/api/profile")', app_source)
        self.assertIn("async function saveProfile()", app_source)
        self.assertIn('requestJson<AuthPayload>("/api/profile"', app_source)
        self.assertIn('requestJson<AdminUsersPayload>("/api/admin/users")', app_source)
        self.assertIn("async function updateUserAccess(user: AuthUser, isActive: boolean)", app_source)
        self.assertIn('`/api/admin/users/${user.id}/access`', app_source)
        self.assertIn("async function submitAuth()", app_source)
        self.assertIn('authMode.value === "login" ? "/api/auth/login" : "/api/auth/register"', app_source)
        self.assertIn("async function logout()", app_source)
        self.assertIn('requestJson<{ ok: true }>("/api/auth/logout"', app_source)
        self.assertIn('class="auth-shell"', app_source)
        self.assertIn("profile-panel", app_source)
        self.assertIn("admin-panel", app_source)
        self.assertIn('t("auth.inactive")', app_source)
        self.assertIn('class="secondary profile-button"', app_source)
        self.assertNotIn('class="safety"', app_source)
        self.assertNotIn('t("app.safety")', app_source)
        self.assertNotIn('"app.safety"', i18n_source)
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
        self.assertIn('"actions.saveProfile"', i18n_source)
        self.assertIn('"actions.activateUser"', i18n_source)
        self.assertIn('"actions.deactivateUser"', i18n_source)
        self.assertIn('"labels.firstName"', i18n_source)
        self.assertIn('"labels.lastName"', i18n_source)
        self.assertIn('"labels.middleName"', i18n_source)
        self.assertIn('"labels.searchEmail"', i18n_source)
        self.assertIn('v-model="profileForm.first_name"', app_source)
        self.assertIn('v-model="profileForm.last_name"', app_source)
        self.assertIn('v-model="profileForm.middle_name"', app_source)
        self.assertIn('@submit.prevent="saveProfile"', app_source)
        self.assertIn('v-model.trim="adminSearch"', app_source)
        self.assertIn('v-for="user in filteredAdminUsers"', app_source)
        self.assertIn('@click="updateUserAccess(user, !user.is_active)"', app_source)

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
        self.assertNotIn("paperEntryLabel?: string;", chart_source)
        self.assertNotIn("paperExitLabel?: string;", chart_source)
        self.assertIn("longSignalLabel?: string;", chart_source)
        self.assertIn("shortSignalLabel?: string;", chart_source)
        self.assertIn(':aria-label="chartLabels.aria"', app_source)
        self.assertIn(':empty-label="chartLabels.empty"', app_source)
        self.assertNotIn(':paper-entry-label="chartLabels.paperEntry"', app_source)
        self.assertNotIn(':paper-exit-label="chartLabels.paperExit"', app_source)
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
        self.assertIn("!isMultiStrategyLive.value", source)
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

    def test_live_all_strategy_view_limits_marker_noise(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("const liveMaxSignals = ref(80);", source)
        self.assertIn("limitRecentSignals(consensusSignals.value, liveMaxSignals.value)", source)
        self.assertIn("limitRecentSignals(rawSignals, liveMaxSignals.value)", source)
        self.assertIn("function limitRecentSignals(signals: Marker[], limit: number): Marker[]", source)
        self.assertIn('v-model.number="liveMaxSignals"', source)
        self.assertIn('t("labels.maxMarkers")', source)
        self.assertIn('"labels.maxMarkers": "Max markers"', i18n_source)
        self.assertIn('"labels.maxMarkers": "Макс. меток"', i18n_source)

    def test_live_page_exposes_moex_bluechips_market(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("const moexBluechipSymbolOptions = [", source)
        self.assertIn('value: "SBER"', source)
        self.assertIn('value: "GAZP"', source)
        self.assertIn('value: "LKOH"', source)
        self.assertIn('value: "YNDX"', source)
        self.assertIn('value: "russian_bluechips"', source)
        self.assertIn('t("options.moexBluechips")', source)
        self.assertIn("russian_bluechips: moexBluechipSymbolOptions", source)
        self.assertIn('"options.moexBluechips": "Russian Bluechips"', i18n_source)
        self.assertIn('"options.moexBluechips": "Голубые фишки РФ"', i18n_source)

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
        self.assertNotIn(':paper-markers="[]"', live_section)
        self.assertNotIn(':show-paper="false"', live_section)

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
        self.assertFalse(is_frontend_route("/lab"))
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
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        style_source = (
            root / "frontend" / "src" / "style.css"
        ).read_text(encoding="utf-8")
        breadth_loaded_source = app_source.split(
            '<template v-else>',
            1,
        )[1]

        self.assertIn(".breadth-grid {\n  display: grid;\n  grid-template-columns: minmax(0, 1fr);", style_source)
        self.assertIn("padding: 14px;", style_source)
        self.assertLess(
            breadth_loaded_source.index('class="breadth-put-call"'),
            breadth_loaded_source.index('class="breadth-grid"'),
        )
        self.assertIn(".breadth-group {\n  display: grid;\n  grid-template-columns: repeat(auto-fit, minmax(520px, 1fr));", style_source)
        self.assertIn("grid-column: 1 / -1;", style_source)
        self.assertIn(".breadth-card .tv-chart {\n  height: 360px;", style_source)
        self.assertIn(".breadth-put-call .tv-chart {\n  height: 440px;", style_source)
        self.assertIn(".breadth-card .tv-chart {\n    height: 300px;", style_source)

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

    def test_removed_web_workflow_helpers_are_removed(self):
        self.assertFalse(hasattr(ui, "strategy_lab_payload"))
        self.assertFalse(hasattr(ui, "strategy_lab_csv"))
        self.assertFalse(hasattr(ui, "run_backtest_payload"))
        self.assertFalse(hasattr(ui, "run_paper_payload"))
        self.assertFalse(hasattr(ui, "combination_signals_payload"))
        self.assertFalse(hasattr(ui, "paper_trade_markers"))
        self.assertFalse(hasattr(ui, "list_runs"))
        self.assertFalse(hasattr(ui, "load_run_details"))

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
        self.assertIn("indicators", payload)

    def test_live_chart_payload_returns_ten_popular_indicators(self):
        client = FakeClient()
        client.candles = [
            candle(index, float(100 + ((index % 8) * 2) - (index // 5)))
            for index in range(40)
        ]

        payload = live_chart_payload(
            {
                "symbol": "BTCUSDT",
                "interval": "5m",
                "limit": 40,
                "fast_ema": 3,
                "slow_ema": 8,
                "rsi_period": 5,
                "macd_signal": 4,
                "bollinger_period": 6,
                "bollinger_stddev": 2,
                "donchian_period": 6,
                "atr_period": 5,
                "vwap_period": 6,
                "stoch_rsi_period": 5,
            },
            client=client,
        )

        indicators = payload["indicators"]
        indicator_ids = [indicator["id"] for indicator in indicators]
        self.assertEqual(
            indicator_ids,
            [
                "sma",
                "ema",
                "bollinger",
                "vwap",
                "donchian",
                "volume",
                "rsi",
                "macd",
                "atr",
                "stoch-rsi",
            ],
        )
        self.assertEqual(len(indicators), 10)
        indicator_by_id = {indicator["id"]: indicator for indicator in indicators}
        self.assertEqual(indicator_by_id["ema"]["pane"], "price")
        self.assertEqual(indicator_by_id["volume"]["pane"], "volume")
        self.assertEqual(indicator_by_id["rsi"]["pane"], "oscillator")
        self.assertEqual(indicator_by_id["macd"]["series"][2]["type"], "histogram")
        for indicator in indicators:
            self.assertTrue(indicator["label"])
            self.assertTrue(indicator["series"])
            for series in indicator["series"]:
                self.assertEqual(len(series["points"]), 40)
                self.assertEqual(series["points"][0]["time"], 0)
                self.assertIsInstance(series["points"][0]["value"], float)

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

    def test_live_chart_payload_accepts_comma_separated_strategies_for_markers(self):
        client = FakeClient()
        client.candles = [
            candle(index, price)
            for index, price in enumerate([10, 9, 8, 9, 11, 13, 15])
        ]

        payload = live_chart_payload(
            {
                "symbol": "BTCUSDT",
                "interval": "1h",
                "limit": 7,
                "strategy": "ema-rsi,macd",
                "fast_ema": 2,
                "slow_ema": 5,
                "macd_signal": 2,
                "rsi_period": 2,
                "rsi_overbought": 100,
                "rsi_oversold": 0,
            },
            client=client,
        )

        strategy_names = {
            str(marker["reason"]).split(": ", 1)[0] for marker in payload["signals"]
        }
        self.assertEqual(payload["strategy"], "ema-rsi,macd")
        self.assertIn("ema-rsi", strategy_names)
        self.assertIn("macd", strategy_names)

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

    def test_live_chart_payload_accepts_moex_bluechip_market(self):
        client = FakeClient()
        client.candles = [candle(index, price) for index, price in enumerate([300, 301, 302, 303, 304])]

        payload = live_chart_payload(
            {
                "market": "russian_bluechips",
                "symbol": "SBER",
                "interval": "5m",
                "limit": 5,
                "strategy": "ema-rsi",
                "fast_ema": 1,
                "slow_ema": 3,
                "rsi_period": 2,
                "rsi_overbought": 100,
                "rsi_oversold": 0,
            },
            client=client,
        )

        self.assertEqual(client.kline_symbols, ["SBER"])
        self.assertEqual(payload["market"], "russian_bluechips")
        self.assertEqual(payload["data_source"], "MOEX ISS shares")
        self.assertEqual(payload["symbol"], "SBER")

    def test_market_data_client_from_payload_selects_futures_provider(self):
        self.assertIsInstance(
            market_data_client_from_payload({"market": "cme_futures"}),
            YahooFuturesMarketDataClient,
        )
        self.assertIsInstance(
            market_data_client_from_payload({"market": "russian_bluechips"}),
            MoexSharesMarketDataClient,
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
                        seed_admin=False,
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

    def test_live_chart_route_uses_moex_market_provider_from_query(self):
        client = FakeClient()
        client.candles = [
            candle(index, price)
            for index, price in enumerate([300, 301, 302, 303, 304, 305, 306])
        ]

        with tempfile.TemporaryDirectory() as tmp:
            with patch("algo_trading.ui.MoexSharesMarketDataClient", return_value=client):
                auth_store = InMemoryAuthStore()
                http = TestClient(
                    create_app(
                        output_root=Path(tmp),
                        auth_store=auth_store,
                        seed_admin=False,
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
                    "?market=russian_bluechips&symbol=SBER&interval=5m&limit=7"
                    "&strategy=ema-rsi&fast_ema=2&slow_ema=5"
                    "&rsi_period=2&rsi_overbought=100&rsi_oversold=0"
                )
                payload = response.json()

        self.assertEqual(payload["market"], "russian_bluechips")
        self.assertEqual(payload["symbol"], "SBER")
        self.assertEqual(client.kline_symbols, ["SBER"])

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

if __name__ == "__main__":
    unittest.main()
