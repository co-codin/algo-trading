import tempfile
import time
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from algo_trading.auth import InMemoryAuthStore, utcnow
import algo_trading.ui as ui
from algo_trading.algopack import AlgoPackRecord
from algo_trading.data import (
    BinanceMarketDataClient,
    MoexSharesMarketDataClient,
    TransientMarketDataError,
    YahooFuturesMarketDataClient,
)
from algo_trading.historical_store import InMemoryHistoricalDataStore
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
        root = Path(__file__).resolve().parents[1]
        source = (root / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
        config_source = (root / "frontend" / "src" / "liveConfig.ts").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("const liveMarketOptions = computed<SelectOption[]>(() => [", source)
        self.assertIn("const liveSymbolsByMarket = ref<Record<string, SelectOption[]>>({});", source)
        self.assertIn("async function loadLiveSymbols()", source)
        self.assertIn('requestJson<LiveSymbolsPayload>("/api/live-symbols")', source)
        self.assertIn("liveIntervalOptions", source)
        self.assertIn('value: "1w"', config_source)
        self.assertIn('value: "1M"', config_source)
        self.assertIn("liveCandleOptions", source)
        self.assertIn("const liveStrategyOptions = computed<StrategyOption[]>(() =>", source)
        self.assertIn("const liveSelectedStrategies = ref<string[]>([\"ema-rsi\"]);", source)
        self.assertIn("const liveStrategyRequest = computed(() =>", source)
        self.assertIn('value: "crypto_spot"', source)
        self.assertIn('t("options.cryptoSpot")', source)
        self.assertIn('value: "cme_futures"', source)
        self.assertIn('t("options.usMarket")', source)
        self.assertIn('"options.usMarket": "US Market"', i18n_source)
        self.assertIn('"options.usMarket": "Рынок США"', i18n_source)
        self.assertIn('"options.usMarket": "美国市场"', i18n_source)
        self.assertIn('<select v-model="liveMarket"', source)
        self.assertIn('<select v-model="liveSymbol"', source)
        self.assertIn('<select v-model="liveInterval"', source)
        self.assertIn('const liveInterval = ref("1h");', source)
        self.assertIn('<select v-model="liveLimit"', source)
        self.assertIn('class="strategy-picker live-strategy-field"', source)
        self.assertIn("toggleLiveStrategy(strategy.name)", source)
        self.assertIn('v-for="group in filteredLiveStrategyGroups"', source)
        self.assertIn('value: "1m"', config_source)
        self.assertIn('value: "1h"', config_source)
        self.assertIn("value: 180", config_source)
        self.assertIn("value: 500", config_source)

    def test_live_page_uses_strategy_multiselect(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")

        self.assertIn('class="strategy-picker live-strategy-field"', source)
        self.assertIn('<strong class="strategy-picker-label">{{ t("labels.strategy") }}</strong>', source)
        self.assertIn('<summary class="strategy-summary">', source)
        self.assertIn("selectedLiveStrategyPreview", source)
        self.assertIn("const liveStrategyMenu = ref<HTMLDetailsElement | null>(null)", source)
        self.assertIn("const liveStrategyGroups = computed<StrategyGroup[]>(() =>", source)
        self.assertIn("strategyGroupCatalog", source)
        self.assertIn("toggleLiveStrategy(strategy.name)", source)
        self.assertIn("selectLiveStrategyGroup(group.strategyNames)", source)
        self.assertIn("selectAllLiveStrategies", source)
        self.assertIn("closeLiveStrategyMenu();", source)
        self.assertIn("function closeLiveStrategyMenu()", source)
        self.assertIn('liveStrategyMenu.value?.removeAttribute("open")', source)
        self.assertIn("clearLiveStrategies", source)
        self.assertIn('<details ref="liveStrategyMenu" class="strategy-menu"', source)
        self.assertIn(":checked=\"liveSelectedStrategies.includes(strategy.name)\"", source)
        self.assertIn("strategy: liveStrategyRequest.value", source)
        self.assertIn("watch([liveMarket, liveSymbol, liveInterval, liveLimit, liveStrategyRequest], () => {", source)
        self.assertNotIn('<select v-model="settings.strategy"', source)

    def test_project_documents_focused_skills(self):
        root = Path(__file__).resolve().parents[1]
        skill_paths = (
            root / "docs" / "skills" / "live-chart-ux.md",
            root / "docs" / "skills" / "market-data-integrations.md",
            root / "docs" / "skills" / "auth-admin-ops.md",
            root / "docs" / "skills" / "refactoring.md",
        )

        for skill_path in skill_paths:
            self.assertTrue(skill_path.exists(), f"{skill_path} is missing")
            source = skill_path.read_text(encoding="utf-8")
            self.assertIn("# ", source)
            self.assertIn("## When To Use", source)
            self.assertIn("## Checklist", source)
            self.assertIn("## Verification", source)

        skills_index = (root / "SKILLS.md").read_text(encoding="utf-8")
        self.assertIn("docs/skills/live-chart-ux.md", skills_index)
        self.assertIn("docs/skills/market-data-integrations.md", skills_index)
        self.assertIn("docs/skills/auth-admin-ops.md", skills_index)
        self.assertIn("docs/skills/refactoring.md", skills_index)

    def test_live_page_exposes_saved_workspaces_alerts_health_and_snapshot(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(encoding="utf-8")
        style_source = (root / "frontend" / "src" / "styles" / "live.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("LIVE_WORKSPACE_STORAGE_KEY", app_source)
        self.assertIn("const liveWorkspaces = ref<LiveWorkspace[]>([]);", app_source)
        self.assertIn("saveLiveWorkspace", app_source)
        self.assertIn("applyLiveWorkspace", app_source)
        self.assertIn("deleteLiveWorkspace", app_source)
        self.assertIn("class=\"workspace-controls\"", app_source)
        self.assertIn("class=\"workspace-list\"", app_source)

        self.assertIn("const liveAlertsEnabled = ref(false);", app_source)
        self.assertIn("const lastAlertSignature = ref(\"\");", app_source)
        self.assertIn("maybeNotifyLiveAlert", app_source)
        self.assertIn("Notification.permission", app_source)
        self.assertIn("class=\"alert-controls\"", app_source)

        self.assertIn("const liveDataHealth = computed", app_source)
        self.assertIn("class=\"health-badge\"", app_source)
        self.assertIn("class=\"health-strip\"", app_source)
        self.assertIn('t("health.liveDetail")', app_source)

        self.assertIn("exportLiveSnapshot", app_source)
        self.assertIn("URL.createObjectURL", app_source)
        self.assertIn("algo-live-snapshot", app_source)
        self.assertIn('t("actions.exportSnapshot")', app_source)

        self.assertIn('"actions.saveWorkspace": "Save workspace"', i18n_source)
        self.assertIn('"actions.exportSnapshot": "Export snapshot"', i18n_source)
        self.assertIn('"labels.dataHealth": "Data health"', i18n_source)
        self.assertIn('"labels.alerts": "Alerts"', i18n_source)
        self.assertIn('"actions.saveWorkspace": "Сохранить рабочее место"', i18n_source)
        self.assertIn('"actions.exportSnapshot": "Экспорт снимка"', i18n_source)

        self.assertIn(".workspace-controls", style_source)
        self.assertIn(".health-badge", style_source)
        self.assertIn(".alert-controls", style_source)

    def test_frontend_exposes_market_intelligence_reports_and_persisted_lists(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
        types_source = (root / "frontend" / "src" / "types.ts").read_text(encoding="utf-8")
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(encoding="utf-8")
        style_source = (root / "frontend" / "src" / "styles" / "live.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("export type MarketEvent", types_source)
        self.assertIn("events: MarketEvent[];", types_source)
        self.assertIn("export type FutoiDashboard", types_source)
        self.assertIn("dashboard: FutoiDashboard;", types_source)
        self.assertIn("export type DailyMarketReportPayload", types_source)
        self.assertIn("export type SavedWorkspacesPayload", types_source)
        self.assertIn("export type SavedWatchlistsPayload", types_source)

        self.assertIn('"reports" | "feedback"', types_source)
        self.assertIn('requestJson<SavedWorkspacesPayload>("/api/workspaces")', app_source)
        self.assertIn('requestJson<SavedWatchlistsPayload>("/api/watchlists")', app_source)
        self.assertIn('requestJson<DailyMarketReportPayload>(`/api/reports/daily?${params.toString()}`)', app_source)
        self.assertIn('class="market-event-feed"', app_source)
        self.assertIn('class="watchlist-panel"', app_source)
        self.assertIn('class="report-panel"', app_source)
        self.assertIn('class="futoi-dashboard-grid"', app_source)

        self.assertIn('"tabs.reports": "Daily report"', i18n_source)
        self.assertIn('"tabs.reports": "Ежедневный отчет"', i18n_source)
        self.assertIn('"tabs.reports": "每日报告"', i18n_source)
        self.assertIn('"labels.watchlists": "Watchlists"', i18n_source)
        self.assertIn('"labels.futoiDashboard": "FUTOI dashboard"', i18n_source)

        self.assertIn(".market-event-feed", style_source)
        self.assertIn(".watchlist-panel", style_source)
        self.assertIn(".report-panel", style_source)
        self.assertIn(".futoi-dashboard-grid", style_source)

    def test_frontend_exposes_quant_strategy_tab(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
        types_source = (root / "frontend" / "src" / "types.ts").read_text(encoding="utf-8")
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(encoding="utf-8")
        style_source = (root / "frontend" / "src" / "styles" / "live.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("QuantStrategyIdea", types_source)
        self.assertIn("QuantStrategiesPayload", types_source)
        self.assertIn("candles: Candle[];", types_source)
        self.assertIn("signals: Marker[];", types_source)
        self.assertIn("indicators: IndicatorDefinition[];", types_source)
        self.assertIn('"quant"', types_source)
        self.assertIn('"/quant": "quant"', app_source)
        self.assertIn('quant: "/quant"', app_source)
        self.assertIn('{ mode: "quant" as const, label: t("tabs.quant") }', app_source)
        self.assertIn("const quantPayload = ref<QuantStrategiesPayload | null>(null);", app_source)
        self.assertIn("const quantStrategyIdeas = ref<QuantStrategyIdea[]>([]);", app_source)
        self.assertIn("const quantStatus = ref(t(\"status.ready\"));", app_source)
        self.assertIn("async function loadQuantStrategyIdeas()", app_source)
        self.assertIn('requestJson<QuantStrategiesPayload>(`/api/quant-strategies?${query}`)', app_source)
        self.assertIn('if (nextMode === "quant")', app_source)
        self.assertIn('v-if="quantPayload"', app_source)
        self.assertIn(':candles="quantPayload.candles"', app_source)
        self.assertIn(':signals="quantPayload.signals"', app_source)
        self.assertIn(':indicators="quantPayload.indicators"', app_source)
        self.assertIn('class="strategy-ideas"', app_source)
        self.assertIn('activeMode === "quant"', app_source)
        self.assertIn('v-for="idea in sortedQuantStrategyIdeas"', app_source)
        self.assertIn("quantIdeaActionLabel", app_source)
        self.assertIn("quantIdeaGroupLabel(idea.group)", app_source)
        self.assertIn("quantIdeaTitle(idea)", app_source)
        self.assertIn("quantIdeaMetricLabel(String(key))", app_source)
        self.assertIn("quantIdeaReasonLabel(idea, reason)", app_source)
        self.assertNotIn("<span>{{ idea.group }}</span>", app_source)
        self.assertNotIn("<h3>{{ idea.title }}</h3>", app_source)
        self.assertNotIn("<dt>{{ key }}</dt>", app_source)
        self.assertNotIn("<li v-for=\"reason in idea.reasons\" :key=\"reason\">{{ reason }}</li>", app_source)
        self.assertIn("quantIdeaScoreStyle", app_source)
        self.assertIn('"tabs.quant": "Quant Strategies"', i18n_source)
        self.assertIn('"pages.quantStrategies": "Quant strategies"', i18n_source)
        self.assertIn('"labels.confidence": "Confidence"', i18n_source)
        self.assertIn('"quant.groups.trend": "Trend"', i18n_source)
        self.assertIn('"quant.ideas.time-series-momentum.title": "Time-series momentum"', i18n_source)
        self.assertIn('"quant.metrics.lookback_return_pct": "Lookback return %"', i18n_source)
        self.assertIn('"quant.reasons.rsi-mean-reversion.oversold": "RSI is oversold at {value}."', i18n_source)
        self.assertIn('"strategyActions.bullish": "Bullish"', i18n_source)
        self.assertIn('"tabs.quant": "Квант-стратегии"', i18n_source)
        self.assertIn('"pages.quantStrategies": "Квант-стратегии"', i18n_source)
        self.assertIn('"quant.groups.trend": "Тренд"', i18n_source)
        self.assertIn('"quant.ideas.time-series-momentum.title": "Моментум временного ряда"', i18n_source)
        self.assertIn('"quant.reasons.rsi-mean-reversion.oversold": "RSI в зоне перепроданности: {value}."', i18n_source)
        self.assertIn('"tabs.quant": "量化策略"', i18n_source)
        self.assertIn('"pages.quantStrategies": "量化策略"', i18n_source)
        self.assertIn('"quant.groups.trend": "趋势"', i18n_source)
        self.assertIn('"quant.ideas.time-series-momentum.title": "时间序列动量"', i18n_source)
        self.assertIn('"quant.reasons.rsi-mean-reversion.oversold": "RSI 超卖：{value}。"', i18n_source)
        self.assertIn(".strategy-ideas", style_source)
        self.assertIn(".strategy-idea-card", style_source)

    def test_russian_live_page_exposes_algopack_and_megaalerts_chart(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
        types_source = (root / "frontend" / "src" / "types.ts").read_text(encoding="utf-8")
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(encoding="utf-8")
        config_source = (root / "frontend" / "src" / "liveConfig.ts").read_text(
            encoding="utf-8"
        )
        chart_source = (
            root / "frontend" / "src" / "components" / "TradingViewChart.vue"
        ).read_text(encoding="utf-8")

        self.assertIn("algopackIndicatorOptions", config_source)
        self.assertIn('export type Mode = "landing" | "live" | "russian-live"', types_source)
        self.assertIn('"/moex-live": "russian-live"', app_source)
        self.assertIn('"/russian-live": "russian-live"', app_source)
        self.assertIn('"russian-live": "/moex-live"', app_source)
        self.assertIn('{ mode: "russian-live" as const, label: t("tabs.russianLive") }', app_source)
        self.assertIn("const russianLivePayload = ref<LiveChartPayload | null>(null);", app_source)
        self.assertIn("async function loadRussianLiveChart()", app_source)
        self.assertIn('params.set("algopack", russianLiveAlgoPackDatasets.value.join(","))', app_source)
        self.assertIn("visibleRussianAlgoPackIndicatorOptions", app_source)
        self.assertIn("isAlgoPackIndicator", app_source)
        default_indicator_block = app_source.split(
            "const russianLiveVisibleIndicators = ref<string[]>([", 1
        )[1].split("]);", 1)[0]
        self.assertNotIn('"algopack-alerts"', default_indicator_block)
        self.assertIn('{ value: "algopack-alerts", dataset: "alerts"', config_source)
        self.assertIn("activeMode === 'russian-live'", app_source)
        self.assertIn("russianLivePayload.candles", app_source)
        self.assertNotIn('{ value: "russian_bluechips", label: t("options.moexBluechips") }', app_source)
        self.assertIn('indicator.pane === "volume"', chart_source)
        self.assertIn('"tabs.russianLive": "MOEX Live"', i18n_source)
        self.assertIn('"tabs.russianLive": "Рынок РФ"', i18n_source)
        self.assertIn('"tabs.russianLive": "MOEX 实时"', i18n_source)
        self.assertIn('"indicators.tradeStats": "TradeStats"', i18n_source)
        self.assertIn('"indicators.orderStats": "OrderStats"', i18n_source)
        self.assertIn('"indicators.obStats": "OBStats"', i18n_source)
        self.assertIn('"indicators.megaAlerts": "MegaAlerts"', i18n_source)

    def test_admin_panel_exposes_free_trial_toggle(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(encoding="utf-8")
        types_source = (root / "frontend" / "src" / "types.ts").read_text(encoding="utf-8")
        style_source = (root / "frontend" / "src" / "styles" / "account.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("FREE_TRIAL_ADMIN_EMAIL", app_source)
        self.assertIn("const freeTrialSettings", app_source)
        self.assertIn("canManageFreeTrial", app_source)
        self.assertIn("/api/admin/settings/free-trial", app_source)
        self.assertIn('class="admin-settings-section"', app_source)
        self.assertIn('v-model="freeTrialSettings.is_free_trial_enabled"', app_source)
        self.assertIn('t("pages.freeTrialSettings")', app_source)
        self.assertIn('t("labels.freeTrialEndAt")', app_source)
        self.assertIn("free_trial_end_at: string | null;", types_source)
        self.assertIn("PlatformSettingsPayload", types_source)
        self.assertIn('"pages.freeTrialSettings": "Free trial"', i18n_source)
        self.assertIn('"labels.freeTrialEndAt": "Free trial ends"', i18n_source)
        self.assertIn('"pages.freeTrialSettings": "Пробный период"', i18n_source)
        self.assertIn('"pages.freeTrialSettings": "免费试用"', i18n_source)
        self.assertIn(".admin-settings-section", style_source)

    def test_frontend_splits_live_configuration_and_styles(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
        main_source = (root / "frontend" / "src" / "main.ts").read_text(encoding="utf-8")
        style_source = (root / "frontend" / "src" / "style.css").read_text(encoding="utf-8")
        config_source = (root / "frontend" / "src" / "liveConfig.ts").read_text(encoding="utf-8")
        helpers_source = (root / "frontend" / "src" / "liveUtils.ts").read_text(encoding="utf-8")

        self.assertIn("from \"./liveConfig\"", app_source)
        self.assertIn("from \"./liveUtils\"", app_source)
        self.assertNotIn("export const liveSymbolOptions", config_source)
        self.assertNotIn("export const moexBluechipSymbolOptions", config_source)
        self.assertIn("export const strategyGroupCatalog", config_source)
        self.assertIn("export function groupSignalsByConsensus", helpers_source)
        self.assertIn("export function limitRecentSignals", helpers_source)
        self.assertNotIn("const moexBluechipSymbolOptions = [", app_source)
        self.assertNotIn("function groupSignalsByConsensus(", app_source)

        self.assertIn('import "./style.css";', main_source)
        self.assertIn('@import "./styles/live.css";', style_source)
        self.assertIn('@import "./styles/breadth.css";', style_source)
        self.assertIn('@import "./styles/account.css";', style_source)

    def test_live_controls_are_grouped_and_strategy_menu_is_searchable(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(encoding="utf-8")
        style_source = (root / "frontend" / "src" / "styles" / "live.css").read_text(encoding="utf-8")

        self.assertIn('class="live-control-section market-controls"', source)
        self.assertIn('class="live-control-section signal-controls"', source)
        self.assertIn('class="live-control-section refresh-controls"', source)
        self.assertIn("const liveStrategySearch = ref(\"\");", source)
        self.assertIn("const filteredLiveStrategyGroups = computed<StrategyGroup[]>(() =>", source)
        self.assertIn("strategyMatchesSearch(strategy, group, query)", source)
        self.assertIn("function strategyMatchesSearch(", source)
        self.assertIn("normalizeSearchText", source)
        self.assertIn("group.label", source)
        self.assertIn('class="strategy-search"', source)
        self.assertIn(':placeholder="t(\'labels.strategySearch\')"', source)
        self.assertIn('v-for="group in filteredLiveStrategyGroups"', source)
        self.assertIn('"labels.strategySearch": "Search strategies"', i18n_source)
        self.assertIn('"labels.strategySearch": "Поиск стратегий"', i18n_source)
        self.assertIn(".live-control-section", style_source)
        self.assertIn(".market-controls", style_source)
        self.assertIn(".signal-controls", style_source)
        self.assertIn(".refresh-controls", style_source)

    def test_removed_frontend_styles_do_not_keep_dead_layout_classes(self):
        style_source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "style.css"
        ).read_text(encoding="utf-8")

        for stale_class in (
            ".workspace",
            ".lab-layout",
            ".symbols-row",
            ".symbol-list",
            ".symbol-chip",
        ):
            self.assertNotIn(stale_class, style_source)

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
        for strategy_name in (
            "adx-trend",
            "ichimoku-breakout",
            "mfi-reversal",
            "parabolic-sar",
            "zscore-reversion",
        ):
            self.assertIn(f'"{strategy_name}"', i18n_source)

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
        self.assertIn("color?: string;", types_source)
        self.assertIn("color: point.color ?? indicatorSeriesItem.color", chart_source)

    def test_live_symbols_are_loaded_from_api_catalog(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")
        config_source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "liveConfig.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("const liveSymbolsByMarket = ref<Record<string, SelectOption[]>>({});", source)
        self.assertIn("async function loadLiveSymbols()", source)
        self.assertIn('requestJson<LiveSymbolsPayload>("/api/live-symbols")', source)
        self.assertIn("ensureLiveSymbolForMarket", source)
        self.assertNotIn("export const liveSymbolOptions = [", config_source)
        self.assertNotIn('value: "BTCUSDT"', config_source)
        self.assertNotIn('value: "ETHUSDT"', config_source)
        self.assertNotIn('value: "ADAUSDT"', config_source)
        self.assertNotIn('value: "AVAXUSDT"', config_source)

    def test_live_symbol_labels_follow_russian_locale(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")

        self.assertIn("const russianLiveSymbolLabels: Record<string, string> = {", source)
        self.assertIn('SBER: "SBER · Сбербанк"', source)
        self.assertIn('IMOEX: "IMOEX · Индекс МосБиржи"', source)
        self.assertIn("function localizedLiveSymbolOption(option: SelectOption): SelectOption", source)
        self.assertIn("locale.value === \"ru\"", source)
        self.assertIn(".map(localizedLiveSymbolOption)", source)

    def test_live_market_selector_changes_auto_refresh_chart(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";',
            source,
        )
        self.assertIn("watch([liveMarket, liveSymbol, liveInterval, liveLimit, liveStrategyRequest], () => {", source)
        self.assertIn('if (activeMode.value === "live") {', source)
        self.assertIn("refreshLiveChart();", source)
        self.assertIn("market: liveMarket.value", source)

    def test_live_symbol_switch_uses_full_list_and_ignores_stale_chart_responses(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")
        symbol_picker_source = source.split('<label class="symbol-picker">', 1)[1].split(
            "</label>",
            1,
        )[0]
        select_source = symbol_picker_source.split('<select v-model="liveSymbol"', 1)[1].split(
            "</select>",
            1,
        )[0]

        self.assertIn('v-for="option in filteredLiveSymbolOptions"', symbol_picker_source)
        self.assertIn('@change="liveSymbolSearch = \'\'"', symbol_picker_source)
        self.assertIn('v-for="option in activeLiveSymbolOptions"', select_source)
        self.assertNotIn('v-for="option in filteredLiveSymbolOptions"', select_source)
        self.assertIn("let liveChartRequestId = 0;", source)
        self.assertIn("const requestId = ++liveChartRequestId;", source)
        self.assertIn(
            "if (requestId !== liveChartRequestId) {\n"
            "      return;\n"
            "    }\n"
            "    livePayload.value = chartPayload;",
            source,
        )
        self.assertIn(
            "if (requestId !== liveChartRequestId) {\n"
            "      return;\n"
            "    }\n"
            "    livePayload.value = null;",
            source,
        )

    def test_live_page_does_not_render_chart_loader(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        style_source = (root / "frontend" / "src" / "style.css").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("async function loadLiveChart()", app_source)
        self.assertIn("void loadLiveChart();", app_source)
        self.assertIn("window.setInterval(() => void loadLiveChart(), seconds * 1000)", app_source)
        self.assertIn("startLivePolling();", app_source)
        self.assertNotIn("liveChartLoading", app_source)
        self.assertNotIn("showLoader", app_source)
        self.assertNotIn("chart-loader", app_source)
        self.assertNotIn("status.loadingChart", app_source)
        self.assertNotIn("chart-shell.is-loading", style_source)
        self.assertNotIn(".chart-loader", style_source)
        self.assertNotIn("chartLoaderSpin", style_source)
        self.assertNotIn('"status.loadingChart"', i18n_source)

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

    def test_live_indicator_toggle_preserves_chart_focus(self):
        root = Path(__file__).resolve().parents[1]
        chart_source = (
            root / "frontend" / "src" / "components" / "TradingViewChart.vue"
        ).read_text(encoding="utf-8")

        self.assertIn("() => [props.candles, visibleMarkers.value],", chart_source)
        self.assertNotIn(
            "() => [props.candles, visibleMarkers.value, props.indicators]",
            chart_source,
        )
        self.assertIn("watch(\n  () => props.indicators,", chart_source)
        self.assertIn("function syncVisibleIndicators()", chart_source)
        indicator_sync = chart_source.split(
            "function syncVisibleIndicators()",
            1,
        )[1].split("\nfunction ", 1)[0]
        self.assertIn("preserveVisibleLogicalRange(() => {", indicator_sync)
        self.assertIn("syncIndicatorSeries();", indicator_sync)
        self.assertNotIn("series.value?.setData", indicator_sync)
        self.assertNotIn("markerApi.value?.setMarkers", indicator_sync)
        self.assertNotIn("fitContent", indicator_sync)

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
            'export type Mode = "landing" | "live" | "russian-live" | "breadth" | "quant" | "futoi" | "reports" | "feedback" | "profile" | "admin";',
            types_source,
        )
        self.assertIn('"/": "landing"', source)
        self.assertIn('"/markets": "live"', source)
        self.assertIn('"/live": "live"', source)
        self.assertIn('"/chart": "live"', source)
        self.assertIn('landing: "/"', source)
        self.assertIn('live: "/markets"', source)
        self.assertNotIn('"/lab": "lab"', source)
        self.assertIn('"/moex-live": "russian-live"', source)
        self.assertIn('"/russian-live": "russian-live"', source)
        self.assertIn('"/futoi": "futoi"', source)
        self.assertIn('"/reports": "reports"', source)
        self.assertIn('"/feedback": "feedback"', source)
        self.assertIn('"/profile": "profile"', source)
        self.assertIn('"/admin": "admin"', source)
        self.assertIn('return routeModes[window.location.pathname] ?? "landing";', source)
        self.assertNotIn('{ mode: "lab" as const, label: t("tabs.lab") }', source)
        self.assertIn('{ mode: "live" as const, label: t("tabs.live") }', source)
        self.assertIn('...(isRussianLocale.value ? [{ mode: "russian-live" as const, label: t("tabs.russianLive") }] : []),', source)
        self.assertIn('{ mode: "breadth" as const, label: t("tabs.breadth") }', source)
        self.assertIn('{ mode: "quant" as const, label: t("tabs.quant") }', source)
        self.assertIn('const isRussianLocale = computed(() => locale.value === "ru");', source)
        self.assertIn('...(isRussianLocale.value ? [{ mode: "futoi" as const, label: t("tabs.futoi") }] : []),', source)
        self.assertIn('{ mode: "reports" as const, label: t("tabs.reports") }', source)
        self.assertIn('const accountMenuItems = computed', source)
        self.assertIn('{ mode: "profile" as const, label: t("tabs.profile") }', source)
        self.assertIn('...(canUseFeatures.value ? [{ mode: "feedback" as const, label: t("tabs.feedback") }] : []),', source)
        self.assertNotIn("const accountTabs = computed", source)
        self.assertIn('{ mode: "admin" as const, label: t("tabs.admin") }', source)
        self.assertNotIn('"tabs.lab"', i18n_source)
        self.assertIn('"tabs.feedback"', i18n_source)
        self.assertIn('"tabs.russianLive"', i18n_source)
        self.assertIn('"tabs.quant"', i18n_source)
        self.assertIn('"tabs.futoi"', i18n_source)
        self.assertIn('"tabs.live": "Global Markets"', i18n_source)
        self.assertIn('"tabs.live": "Глобальные рынки"', i18n_source)
        self.assertIn('"tabs.live": "全球市场"', i18n_source)
        self.assertIn('"pages.liveMarket": "Global markets"', i18n_source)
        self.assertNotIn('{ mode: "backtest" as const', source)
        self.assertNotIn('{ mode: "paper" as const', source)
        self.assertNotIn('{ mode: "combos" as const', source)
        self.assertNotIn('{ mode: "runs" as const', source)
        self.assertNotIn('"tabs.backtest"', i18n_source)
        self.assertNotIn('"tabs.paper"', i18n_source)
        self.assertNotIn('"tabs.combos"', i18n_source)
        self.assertNotIn('"tabs.runs"', i18n_source)

    def test_frontend_exposes_futoi_only_for_russian_locale(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )
        types_source = (root / "frontend" / "src" / "types.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("export type FutoiRecord", types_source)
        self.assertIn("export type FutoiInstrument", types_source)
        self.assertIn("export type FutoiPayload", types_source)
        self.assertIn("chart_records: FutoiRecord[];", types_source)
        self.assertIn("export type FutoiInstrumentsPayload", types_source)
        self.assertIn('const futoiRecords = ref<FutoiRecord[]>([]);', source)
        self.assertIn('const futoiChartRecords = ref<FutoiRecord[]>([]);', source)
        self.assertIn('const futoiInstruments = ref<FutoiInstrument[]>([]);', source)
        self.assertIn('const futoiInstrumentSearch = ref("");', source)
        self.assertIn("const filteredFutoiInstruments = computed(() =>", source)
        self.assertIn("const selectedFutoiInstrument = computed(() =>", source)
        self.assertIn("async function loadFutoi()", source)
        self.assertIn("async function loadFutoiInstruments()", source)
        self.assertIn("async function loadFutoiDashboard()", source)
        self.assertIn("function selectFutoiInstrument(ticker: string)", source)
        self.assertIn('if (mode === "futoi" && !isRussianLocale.value) {', source)
        self.assertIn('if (!isRussianLocale.value && (activeMode.value === "futoi" || activeMode.value === "russian-live")) {', source)
        self.assertIn('requestJson<FutoiInstrumentsPayload>("/api/futoi/instruments")', source)
        self.assertIn('requestJson<FutoiPayload>(`/api/futoi?${params.toString()}`)', source)
        self.assertIn('params.set("history_days", "365");', source)
        self.assertIn("futoiChartRecords.value = payload.chart_records;", source)
        self.assertIn('activeMode === "futoi"', source)
        self.assertIn('class="panel futoi-panel"', source)
        self.assertIn('class="futoi-dashboard"', source)
        self.assertIn('class="futoi-instrument-list"', source)
        self.assertIn('class="futoi-instrument-button"', source)
        self.assertIn('class="futoi-detail-panel"', source)
        self.assertIn('class="futoi-metrics"', source)
        self.assertIn('v-for="instrument in filteredFutoiInstruments"', source)
        self.assertIn('v-for="record in futoiRecords"', source)
        self.assertIn('"tabs.futoi": "FUTOI"', i18n_source)
        self.assertIn('"pages.futoi": "FUTOI"', i18n_source)
        self.assertIn('"pages.futoiSubtitle"', i18n_source)
        self.assertIn('"labels.futoiInstruments": "FUTOI instruments"', i18n_source)
        self.assertIn('"labels.futoiInstruments": "Инструменты FUTOI"', i18n_source)
        self.assertIn('"labels.futoiOpenInterest": "Открытый интерес"', i18n_source)
        self.assertIn('"empty.noFutoi"', i18n_source)
        self.assertIn('"empty.noFutoiInstruments"', i18n_source)

    def test_frontend_shows_russian_live_markets_only_for_russian_locale(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")

        self.assertIn("const russianLiveMarkets = new Set([", source)
        self.assertIn("function isRussianLiveMarket(market: string): boolean", source)
        self.assertIn("const liveSymbolsByMarket = ref<Record<string, SelectOption[]>>({});", source)
        self.assertIn("const russianLiveSymbolsByMarket = ref<Record<string, SelectOption[]>>({});", source)
        self.assertIn("liveSymbolsByMarket.value = payload.symbols;", source)
        self.assertIn("russianLiveSymbolsByMarket.value = payload.russian_symbols;", source)
        self.assertNotIn("const visibleLiveSymbolsByMarket = computed<Record<string, SelectOption[]>>(() =>", source)
        self.assertIn("const russianLiveMarketOptions = computed<SelectOption[]>(() => [", source)
        self.assertIn("const activeRussianLiveSymbolOptions = computed", source)
        self.assertIn("const filteredRussianLiveSymbolOptions = computed", source)
        self.assertIn('if (mode === "russian-live" && !isRussianLocale.value) {', source)
        self.assertIn('activeMode.value === "russian-live"', source)

    def test_russian_live_page_syncs_chart_controls_to_moex_url(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")
        i18n_source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "i18n.ts"
        ).read_text(encoding="utf-8")
        russian_section = source.split(
            '<section v-else-if="activeMode === \'russian-live\'"',
            1,
        )[1].split(
            '<section v-else-if=\'activeMode === "breadth"\'',
            1,
        )[0]

        self.assertIn("function applyRussianLiveSettingsFromLocation()", source)
        self.assertIn("function syncRussianLiveUrl()", source)
        self.assertIn("function russianLiveUrlPath()", source)
        self.assertIn('params.set("market", russianLiveMarket.value)', source)
        self.assertIn('params.set("symbol", russianLiveSymbol.value)', source)
        self.assertIn('params.set("interval", String(russianLiveInterval.value))', source)
        self.assertIn('params.set("limit", String(russianLiveLimit.value))', source)
        self.assertIn('params.set("indicators", russianLiveVisibleIndicators.value.join(","))', source)
        self.assertIn('params.set("strategy", russianLiveStrategyRequest.value)', source)
        self.assertIn('russianLiveVisibleIndicators.value = parseRussianLiveIndicators(params.get("indicators"));', source)
        self.assertIn('russianLiveSelectedStrategies.value = parseLiveStrategyRequest(params.get("strategy"), true);', source)
        self.assertIn('window.history.replaceState({ mode: "russian-live" }, "", nextUrl)', source)
        self.assertIn(
            "[russianLiveMarket, russianLiveSymbol, russianLiveInterval, russianLiveLimit, russianLiveStrategyRequest, russianLiveAlgoPackDatasets],",
            source,
        )
        self.assertIn(
            "if (activeMode.value === \"russian-live\" && !isApplyingRussianLiveSettingsFromUrl) {",
            source,
        )
        self.assertIn('class="strategy-picker live-strategy-field"', russian_section)
        self.assertIn('details ref="liveStrategyMenu" class="strategy-menu"', russian_section)
        self.assertIn('v-for="group in filteredLiveStrategyGroups"', russian_section)
        self.assertIn('russianLiveSelectedStrategies.includes(strategy.name)', russian_section)
        self.assertIn('toggleRussianLiveStrategy(strategy.name)', russian_section)
        self.assertIn('const russianLiveSelectedStrategies = ref<string[]>([]);', source)
        self.assertIn('const russianLiveStrategyRequest = computed(() =>', source)
        self.assertIn('return t("options.noStrategy");', source)
        self.assertIn('"options.noStrategy": "No strategy"', i18n_source)
        self.assertIn('"options.noStrategy": "Без стратегии"', i18n_source)
        self.assertIn('"options.noStrategy": "无策略"', i18n_source)
        self.assertIn("const russianLiveConsensusSignals = computed", source)
        self.assertIn("const displayedRussianLiveSignals = computed", source)
        self.assertIn(
            "groupSignalsByConsensus(russianLivePayload.value?.signals ?? [], liveConsensusMinConfirmations.value)",
            source,
        )
        self.assertIn(
            "limitRecentSignals(russianLiveConsensusSignals.value, liveMaxSignals.value)",
            source,
        )
        self.assertIn('v-model="liveSignalDisplayMode"', russian_section)
        self.assertIn('v-model.number="liveConsensusMinConfirmations"', russian_section)
        self.assertIn('v-model.number="liveMaxSignals"', russian_section)
        self.assertIn('v-model="showSignals"', russian_section)
        self.assertIn(':signals="displayedRussianLiveSignals"', russian_section)

    def test_frontend_adds_futoi_position_chart(self):
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
        style_source = (root / "frontend" / "src" / "styles" / "live.css").read_text(
            encoding="utf-8"
        )
        chart_source = (
            root / "frontend" / "src" / "components" / "FutoiPositionChart.vue"
        ).read_text(encoding="utf-8")

        self.assertIn("export type FutoiChartPoint", types_source)
        self.assertIn(
            'const FutoiPositionChart = defineAsyncComponent(() => import("./components/FutoiPositionChart.vue"));',
            source,
        )
        self.assertIn("type FutoiChartLabels", source)
        self.assertIn(
            "const futoiChartPoints = computed<FutoiChartPoint[]>(() => buildFutoiChartPoints(futoiChartRecords.value));",
            source,
        )
        self.assertIn("function buildFutoiChartPoints(records: FutoiRecord[]): FutoiChartPoint[]", source)
        self.assertIn("record.trade_date", source)
        self.assertIn("record.trade_time", source)
        self.assertIn("point.net_position += Number(record.position)", source)
        self.assertIn("point.long_position += Number(record.position_long)", source)
        self.assertIn("point.short_position += Number(record.position_short)", source)
        self.assertIn("point.open_interest += Math.abs(Number(record.position_long))", source)
        self.assertIn(".sort((left, right) => left.time - right.time)", source)
        self.assertIn('class="futoi-chart-shell"', source)
        self.assertIn("<FutoiPositionChart", source)
        self.assertIn(':points="futoiChartPoints"', source)
        self.assertIn(':labels="futoiChartLabels"', source)
        self.assertIn('"chart.futoiNet": "Net"', i18n_source)
        self.assertIn('"chart.futoiLong": "Long"', i18n_source)
        self.assertIn('"chart.futoiShort": "Short"', i18n_source)
        self.assertIn('"chart.futoiOpenInterest": "Open interest"', i18n_source)
        self.assertIn('"chart.futoiNet": "Чистая"', i18n_source)
        self.assertIn('"chart.futoiNet": "净持仓"', i18n_source)
        self.assertIn(".futoi-chart-shell", style_source)
        self.assertIn(".futoi-chart-legend", style_source)
        self.assertIn("createChart", chart_source)
        self.assertIn("addSeries(LineSeries", chart_source)
        self.assertIn("netSeries.value?.setData", chart_source)
        self.assertIn("longSeries.value?.setData", chart_source)
        self.assertIn("shortSeries.value?.setData", chart_source)

    def test_frontend_lazy_loads_chart_components(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")

        self.assertIn("defineAsyncComponent", source)
        self.assertIn(
            'const TradingViewChart = defineAsyncComponent(() => import("./components/TradingViewChart.vue"));',
            source,
        )
        self.assertIn(
            'const FutoiPositionChart = defineAsyncComponent(() => import("./components/FutoiPositionChart.vue"));',
            source,
        )
        self.assertNotIn('import TradingViewChart from "./components/TradingViewChart.vue";', source)
        self.assertNotIn('import FutoiPositionChart from "./components/FutoiPositionChart.vue";', source)

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
        self.assertIn('class="breadth-overview-grid"', source)
        self.assertIn('class="breadth-detail-stack"', source)
        self.assertIn('v-for="view in breadthGroupViews"', source)
        self.assertIn('v-for="item in view.group.items"', source)
        self.assertIn('breadthPayload?.series[item.symbol]', source)
        self.assertIn('export type MarketBreadthPayload', types_source)
        self.assertIn('"tabs.breadth": "US Market Breadth"', i18n_source)
        self.assertIn('"tabs.breadth": "Ширина рынка США"', i18n_source)

    def test_frontend_defines_bilingual_i18n_contract(self):
        root = Path(__file__).resolve().parents[1]
        i18n_path = root / "frontend" / "src" / "i18n.ts"
        self.assertTrue(i18n_path.exists())
        i18n_source = i18n_path.read_text(encoding="utf-8")
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )

        self.assertIn('export type Locale = "en" | "ru" | "zh";', i18n_source)
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

    def test_frontend_defines_chinese_i18n_contract(self):
        root = Path(__file__).resolve().parents[1]
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )

        self.assertIn('export type Locale = "en" | "ru" | "zh";', i18n_source)
        self.assertIn('{ code: "zh", label: "ZH", flag: "🇨🇳" }', i18n_source)
        self.assertIn("zh:", i18n_source)
        self.assertIn('"auth.title": "交易工作区"', i18n_source)
        self.assertIn('"tabs.breadth": "美国市场宽度"', i18n_source)
        self.assertIn('"actions.refreshChart": "刷新图表"', i18n_source)
        self.assertIn('"labels.strategySearch": "搜索策略"', i18n_source)
        self.assertIn('"empty.noCandles": "未返回K线"', i18n_source)
        self.assertIn('"chart.longLegend": "做多信号"', i18n_source)
        self.assertIn('"ema-rsi": "EMA + RSI"', i18n_source)
        self.assertIn('macd: "MACD交叉"', i18n_source)
        self.assertIn('"combined-signals": "组合信号"', i18n_source)
        self.assertIn('"combined-signals": "可配置的策略确认组合"', i18n_source)
        self.assertIn('return value === "ru" || value === "zh" ? value : "en";', i18n_source)
        self.assertIn("SUPPORTED_LOCALES", app_source)
        self.assertIn("setLocale(item.code)", app_source)

    def test_frontend_exposes_auth_shell_and_session_calls(self):
        root = Path(__file__).resolve().parents[1]
        api_source = (root / "frontend" / "src" / "api.ts").read_text(
            encoding="utf-8"
        )
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        header_source = app_source[
            app_source.index('<header class="topbar">') : app_source.index("</header>")
        ]
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
        self.assertIn('const adminExpiryEdits = reactive<Record<number, string>>({});', app_source)
        self.assertIn('const adminSearch = ref("");', app_source)
        self.assertIn("const filteredAdminUsers = computed", app_source)
        self.assertIn("user.username.toLowerCase().includes(query)", app_source)
        self.assertIn('const authMode = ref<"login" | "register">("login");', app_source)
        self.assertIn("const authForm = reactive", app_source)
        self.assertIn('const canUseFeatures = computed(() => Boolean(authUser.value?.is_active));', app_source)
        self.assertIn('authUser.value?.is_admin === true', app_source)
        self.assertIn("FREE_TRIAL_ADMIN_EMAIL", app_source)
        self.assertIn("async function loadCurrentUser()", app_source)
        self.assertIn('requestJson<AuthMePayload>("/api/auth/me")', app_source)
        self.assertIn('requestJson<AuthMePayload>("/api/profile")', app_source)
        self.assertIn("async function saveProfile()", app_source)
        self.assertIn('requestJson<AuthPayload>("/api/profile"', app_source)
        self.assertIn('requestJson<AdminUsersPayload>("/api/admin/users")', app_source)
        self.assertIn("async function updateUserAccess(user: AuthUser, isActive: boolean)", app_source)
        self.assertIn("async function updateUserExpiry(user: AuthUser)", app_source)
        self.assertIn('`/api/admin/users/${user.id}/access`', app_source)
        self.assertIn("expired_at: isoDateTimeFromDateInput(adminExpiryEdits[user.id])", app_source)
        self.assertIn("function dateInputValue(value: string | null | undefined): string", app_source)
        self.assertIn("function isoDateTimeFromDateInput(value: string): string | null", app_source)
        self.assertIn("async function submitAuth()", app_source)
        self.assertIn('authMode.value === "login" ? "/api/auth/login" : "/api/auth/register"', app_source)
        self.assertIn("async function logout()", app_source)
        self.assertIn('requestJson<{ ok: true }>("/api/auth/logout"', app_source)
        self.assertIn('class="auth-shell"', app_source)
        self.assertIn("profile-panel", app_source)
        self.assertIn("admin-panel", app_source)
        self.assertIn('t("auth.inactive")', app_source)
        self.assertIn('ref="accountMenu"', app_source)
        self.assertIn('class="profile-menu account-menu"', app_source)
        self.assertIn('class="account-menu-trigger"', app_source)
        self.assertIn('class="account-menu-panel"', app_source)
        self.assertIn('class="account-menu-footer"', app_source)
        self.assertIn('t("labels.account")', app_source)
        self.assertIn('v-for="item in accountMenuItems"', app_source)
        self.assertIn('@click="selectAccountMode(item.mode)"', app_source)
        self.assertIn('@click="logoutFromMenu"', app_source)
        self.assertNotIn('class="user-pill"', app_source)
        self.assertNotIn("{{ authUser.username }}", header_source)
        self.assertNotIn("{{ authUser.is_active ? t(\"auth.active\") : t(\"auth.inactive\") }}", header_source)
        self.assertNotIn('class="secondary logout-button"', app_source)
        self.assertNotIn('class="safety"', app_source)
        self.assertNotIn('t("app.safety")', app_source)
        self.assertNotIn('"app.safety"', i18n_source)
        self.assertIn('"tabs.profile"', i18n_source)
        self.assertIn('"tabs.admin"', i18n_source)
        self.assertIn('"labels.account"', i18n_source)
        self.assertIn('"auth.inactive"', i18n_source)
        self.assertIn('@submit.prevent="submitAuth"', app_source)
        self.assertIn('@click="logoutFromMenu"', app_source)
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
        self.assertIn('v-model="adminExpiryEdits[user.id]"', app_source)
        self.assertIn('type="date"', app_source)
        self.assertIn('@click="updateUserExpiry(user)"', app_source)
        self.assertIn('"actions.saveExpiration"', i18n_source)

    def test_frontend_exposes_public_landing_page(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )
        style_source = (root / "frontend" / "src" / "style.css").read_text(
            encoding="utf-8"
        )

        self.assertIn('class="landing-shell"', app_source)
        self.assertIn('v-if="!authChecked && activeMode !== \'landing\'"', app_source)
        self.assertIn('v-else-if="!authUser || activeMode === \'landing\'"', app_source)
        self.assertIn('class="landing-header"', app_source)
        self.assertIn('class="landing-header-actions"', app_source)
        self.assertIn('class="landing-visual"', app_source)
        self.assertIn('class="landing-terminal-preview"', app_source)
        self.assertIn('class="landing-terminal-chart"', app_source)
        self.assertIn('class="landing-candle"', app_source)
        self.assertIn('class="landing-feature-grid"', app_source)
        self.assertIn('class="landing-feature-band"', app_source)
        self.assertIn('class="landing-info-band"', app_source)
        self.assertIn('class="landing-info-header"', app_source)
        self.assertIn('class="landing-info-grid"', app_source)
        self.assertIn('class="landing-info-panel"', app_source)
        self.assertIn('class="landing-info-list"', app_source)
        self.assertIn('class="landing-metrics"', app_source)
        self.assertIn('v-for="section in landingInfoSections"', app_source)
        self.assertIn('v-for="item in section.items"', app_source)
        self.assertIn('const showLandingAuthForm = ref(false);', app_source)
        self.assertIn('const landingInfoSections:', app_source)
        self.assertIn('function openLandingAuth(mode: "login" | "register")', app_source)
        self.assertIn('v-if="!authUser && showLandingAuthForm"', app_source)
        self.assertIn('class="landing-auth-overlay"', app_source)
        self.assertNotIn('class="landing-public-panel"', app_source)
        self.assertIn('v-if="authUser" class="landing-session-inline"', app_source)
        self.assertIn('@click="openLandingAuth(\'login\')"', app_source)
        self.assertIn('@click="openLandingAuth(\'register\')"', app_source)
        self.assertIn('@click="setMode(\'live\')"', app_source)
        self.assertIn('id="landing-title">{{ t("app.title") }}', app_source)
        self.assertIn('t("landing.title")', app_source)
        self.assertIn('t("actions.openDashboard")', app_source)
        self.assertIn('"landing.title": "Market intelligence terminal"', i18n_source)
        self.assertIn('"landing.title": "Терминал рыночной аналитики"', i18n_source)
        self.assertIn('"landing.title": "市场情报终端"', i18n_source)
        self.assertIn('"landing.metric.markets"', i18n_source)
        self.assertIn('"landing.sessionTitle"', i18n_source)
        self.assertIn('"landing.info.heading": "Built for daily market review"', i18n_source)
        self.assertIn('"landing.info.heading": "Для ежедневного обзора рынка"', i18n_source)
        self.assertIn('"landing.info.heading": "为每日市场复盘而建"', i18n_source)
        self.assertIn('"landing.info.coverage.title"', i18n_source)
        self.assertIn('"landing.info.pipeline.title"', i18n_source)
        self.assertIn('"landing.info.signals.title"', i18n_source)
        self.assertIn('"landing.info.access.title"', i18n_source)
        self.assertIn('"landing.info.coverage.hk"', i18n_source)
        self.assertIn('"landing.info.pipeline.postgres"', i18n_source)
        self.assertIn('"landing.info.signals.megaalerts"', i18n_source)
        self.assertIn('"landing.info.access.trial"', i18n_source)
        self.assertIn('"actions.openDashboard"', i18n_source)
        self.assertIn(".landing-shell", style_source)
        self.assertIn(".landing-header-actions", style_source)
        self.assertIn(".landing-visual", style_source)
        self.assertIn(".landing-terminal-preview", style_source)
        self.assertIn(".landing-feature-band", style_source)
        self.assertIn(".landing-info-band", style_source)
        self.assertIn(".landing-info-grid", style_source)
        self.assertIn(".landing-info-panel", style_source)
        self.assertIn(".landing-info-list", style_source)
        self.assertIn(".landing-auth-overlay", style_source)
        self.assertIn(".landing-auth-card", style_source)

    def test_frontend_exposes_feedback_form_and_admin_status_controls(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )
        types_source = (root / "frontend" / "src" / "types.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("export type FeedbackStatus", types_source)
        self.assertIn("export type FeedbackItem", types_source)
        self.assertIn("export type FeedbackPayload", types_source)
        self.assertIn("export type AdminFeedbackPayload", types_source)
        self.assertIn('const feedbackForm = reactive({', app_source)
        self.assertIn('const feedbackStatus = ref(t("status.ready"));', app_source)
        self.assertIn('const adminFeedback = ref<FeedbackItem[]>([]);', app_source)
        self.assertIn("const feedbackStatusOptions = computed", app_source)
        self.assertIn("async function submitFeedback()", app_source)
        self.assertIn('requestJson<FeedbackPayload>("/api/feedback"', app_source)
        self.assertIn("async function loadAdminFeedback()", app_source)
        self.assertIn('requestJson<AdminFeedbackPayload>("/api/admin/feedback")', app_source)
        self.assertIn("async function updateFeedbackStatus(feedback: FeedbackItem, status: FeedbackStatus)", app_source)
        self.assertIn('`/api/admin/feedback/${feedback.id}/status`', app_source)
        self.assertIn('activeMode === "feedback"', app_source)
        self.assertIn('class="panel feedback-panel"', app_source)
        self.assertIn('class="feedback-form"', app_source)
        self.assertIn('class="feedback-form-body"', app_source)
        self.assertIn('class="feedback-form-footer"', app_source)
        self.assertIn('class="feedback-title-field"', app_source)
        self.assertIn('class="feedback-description-field"', app_source)
        self.assertNotIn('class="field-grid feedback-field-grid"', app_source)
        self.assertNotIn('<form v-if="authUser.is_active" class="feedback-form"', app_source)
        self.assertIn('@submit.prevent="submitFeedback"', app_source)
        self.assertIn('v-model.trim="feedbackForm.title"', app_source)
        self.assertIn('v-model.trim="feedbackForm.description"', app_source)
        self.assertIn('v-for="feedback in adminFeedback"', app_source)
        self.assertIn('@change="updateFeedbackStatus(feedback, feedback.status)"', app_source)
        self.assertIn('"pages.feedback": "Report a bug / feedback"', i18n_source)
        self.assertIn('"pages.feedback": "Сообщить об ошибке / отзыв"', i18n_source)
        self.assertIn('"pages.feedback": "报告问题 / 反馈"', i18n_source)
        self.assertIn('"feedback.status.open": "Open"', i18n_source)
        self.assertIn('"feedback.status.in_progress": "In progress"', i18n_source)
        self.assertIn('"feedback.status.resolved": "Resolved"', i18n_source)

    def test_frontend_hides_telegram_rsi_alert_settings(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("const telegramAlertForm = reactive({", app_source)
        self.assertNotIn("async function loadTelegramAlertSettings()", app_source)
        self.assertNotIn("/api/alerts/telegram", app_source)
        self.assertNotIn("telegram-alert-form", app_source)
        self.assertNotIn("telegramAlertForm", app_source)
        self.assertNotIn('"pages.telegramAlerts"', i18n_source)
        self.assertNotIn('"labels.telegramBotToken"', i18n_source)
        self.assertNotIn('"labels.telegramChatId"', i18n_source)
        self.assertNotIn('"actions.testTelegramAlert"', i18n_source)

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
        root = Path(__file__).resolve().parents[1]
        source = (root / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
        helper_source = (root / "frontend" / "src" / "liveUtils.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn('type SignalDisplayMode = "consensus" | "individual";', source)
        self.assertIn(
            'const liveSignalDisplayMode = ref<SignalDisplayMode>("consensus");',
            source,
        )
        self.assertIn("const liveConsensusMinConfirmations = ref(5);", source)
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
        self.assertIn("formatConsensusReason", helper_source)
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
        helper_source = (root / "frontend" / "src" / "liveUtils.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("const liveMaxSignals = ref(80);", source)
        self.assertIn("limitRecentSignals(consensusSignals.value, liveMaxSignals.value)", source)
        self.assertIn("limitRecentSignals(rawSignals, liveMaxSignals.value)", source)
        self.assertIn("export function limitRecentSignals(signals: Marker[], limit: number): Marker[]", helper_source)
        self.assertIn('v-model.number="liveMaxSignals"', source)
        self.assertIn('t("labels.maxMarkers")', source)
        self.assertIn('"labels.maxMarkers": "Max markers"', i18n_source)
        self.assertIn('"labels.maxMarkers": "Макс. меток"', i18n_source)

    def test_live_page_exposes_moex_stock_and_combined_index_futures_markets(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        config_source = (root / "frontend" / "src" / "liveConfig.ts").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("export const moexBluechipSymbolOptions = [", config_source)
        self.assertNotIn("export const moexIndexSymbolOptions = [", config_source)
        self.assertNotIn("export const moexFuturesSymbolOptions = [", config_source)
        self.assertNotIn("export const moexIndexFuturesSymbolOptions = [", config_source)
        self.assertNotIn('{ value: "russian_bluechips", label: t("options.moexBluechips") }', source)
        self.assertNotIn('{ value: "russian_indices_futures", label: t("options.moexIndicesFutures") }', source)
        self.assertNotIn('value: "russian_indices"', source)
        self.assertNotIn('value: "russian_futures"', source)
        self.assertIn('t("options.moexBluechips")', source)
        self.assertIn('t("options.moexIndicesFutures")', source)
        self.assertNotIn("russian_bluechips: moexBluechipSymbolOptions", source)
        self.assertNotIn("russian_indices_futures: moexIndexFuturesSymbolOptions", source)
        self.assertIn('"options.moexBluechips": "Russian Stocks"', i18n_source)
        self.assertIn('"options.moexIndicesFutures": "Russian Indices & Futures"', i18n_source)
        self.assertIn('"options.moexBluechips": "Акции РФ"', i18n_source)
        self.assertIn('"options.moexIndicesFutures": "Индексы и фьючерсы РФ"', i18n_source)
        self.assertIn('"options.moexIndicesFutures": "俄罗斯指数和期货"', i18n_source)

    def test_live_page_exposes_commodities_market(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn('value: "commodities"', source)
        self.assertIn('t("options.commodities")', source)
        self.assertNotIn("const commoditySymbolOptions = computed<SelectOption[]>(() => [", source)
        self.assertNotIn("commodities: commoditySymbolOptions.value", source)
        for symbol in ("GC=F", "SI=F", "NG=F", "BZ=F", "PL=F", "PA=F", "HG=F"):
            self.assertNotIn(f'value: "{symbol}"', source)
        self.assertIn('"options.commodities": "Commodities"', i18n_source)
        self.assertIn('"options.commodities": "Сырьевые товары"', i18n_source)

    def test_live_page_exposes_mag7_stocks_market(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn('value: "mag7_stocks"', app_source)
        self.assertIn('t("options.mag7Stocks")', app_source)
        self.assertNotIn("mag7_stocks: mag7StockSymbolOptions", app_source)
        self.assertIn('"options.mag7Stocks": "MAG 7 Stocks"', i18n_source)
        self.assertIn('"options.mag7Stocks": "Акции MAG 7"', i18n_source)

    def test_live_page_exposes_hong_kong_stocks_market(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn('value: "hong_kong_stocks"', app_source)
        self.assertIn('t("options.hongKongStocks")', app_source)
        self.assertNotIn("hong_kong_stocks: hongKongStockSymbolOptions", app_source)
        self.assertIn('"options.hongKongStocks": "Hong Kong Stocks"', i18n_source)
        self.assertIn('"options.hongKongStocks": "Акции Гонконга"', i18n_source)
        self.assertIn('"options.hongKongStocks": "港股"', i18n_source)

    def test_live_page_filters_symbol_picker_by_search_text_without_auto_select(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )
        style_source = (root / "frontend" / "src" / "styles" / "live.css").read_text(
            encoding="utf-8"
        )
        helper_source = (root / "frontend" / "src" / "liveUtils.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn('const liveSymbolSearch = ref("")', source)
        self.assertIn("const filteredLiveSymbolOptions = computed", source)
        self.assertIn("export function normalizeSearchText(value: string | number): string", helper_source)
        self.assertIn("toLowerCase()", helper_source)
        self.assertIn("export function optionMatchesSearch(option: SelectOption, query: string): boolean", helper_source)
        self.assertIn("optionMatchesSearch(option, query)", source)
        self.assertIn("const hasLiveSymbolSearch = computed", source)
        self.assertNotIn("let liveSymbolSearchTimer = 0", source)
        self.assertNotIn("function clearLiveSymbolSearchTimer()", source)
        self.assertNotIn("watch(liveSymbolSearch, () => {", source)
        self.assertNotIn("window.setTimeout(() => {", source)
        self.assertNotIn("const matchedSymbol = filteredLiveSymbolOptions.value[0]", source)
        self.assertNotIn("selectLiveSymbol(matchedSymbol.value)", source)
        self.assertIn("function selectLiveSymbol(value: string | number)", source)
        self.assertIn('v-model.trim="liveSymbolSearch"', source)
        self.assertIn('type="search"', source)
        self.assertIn("t('labels.symbolSearch')", source)
        self.assertIn("filteredLiveSymbolOptions", source)
        self.assertIn('class="symbol-results"', source)
        self.assertIn('class="symbol-result"', source)
        self.assertIn('v-if="hasLiveSymbolSearch"', source)
        self.assertIn('@click="selectLiveSymbol(option.value)"', source)
        self.assertIn(":class=\"{ 'is-active': String(option.value) === liveSymbol }\"", source)
        self.assertIn('t("empty.noMatchingSymbols")', source)
        self.assertIn(".symbol-results", style_source)
        self.assertIn(".symbol-result.is-active", style_source)
        self.assertIn('"labels.symbolSearch": "Search symbol"', i18n_source)
        self.assertIn('"empty.noMatchingSymbols": "No symbols match that search"', i18n_source)

    def test_live_page_syncs_market_symbol_indicators_and_strategy_to_url(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
        ).read_text(encoding="utf-8")

        self.assertIn("function applyLiveSettingsFromLocation()", source)
        self.assertIn("function syncLiveUrl()", source)
        self.assertIn("new URLSearchParams(window.location.search)", source)
        self.assertIn('params.set("market", liveMarket.value)', source)
        self.assertIn('params.set("symbol", liveSymbol.value)', source)
        self.assertIn('params.set("indicators", liveVisibleIndicators.value.join(","))', source)
        self.assertIn('params.set("strategy", liveStrategyRequest.value)', source)
        self.assertIn('parseLiveStrategyRequest(params.get("strategy"))', source)
        self.assertIn("function parseLiveStrategyRequest(value: string | null, allowEmpty = false): string[]", source)
        self.assertIn('window.history.replaceState({ mode: "live" }, "", nextUrl)', source)
        self.assertIn("watch([liveMarket, liveSymbol, liveVisibleIndicators, liveStrategyRequest],", source)
        self.assertIn(
            "applyLiveSettingsFromLocation();\n  applyRussianLiveSettingsFromLocation();\n  enforceLocaleAvailability();\n  setMode(modeFromLocation(), false);",
            source,
        )
        popstate_body = source.split("function handlePopState()", 1)[1].split(
            "\nfunction ",
            1,
        )[0]
        self.assertIn("const nextMode = modeFromLocation();", popstate_body)
        self.assertIn('if (nextMode === "live")', popstate_body)
        self.assertIn("applyLiveSettingsFromLocation();", popstate_body)
        self.assertIn("setMode(nextMode, false);", popstate_body)

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
        live_section = app_source.split(
            '<section v-if="activeMode === \'live\'" class="panel live-panel">',
            1,
        )[1].split(
            "<section v-else-if='activeMode === \"breadth\"' class=\"panel breadth-panel\">",
            1,
        )[0]

        self.assertIn('class="live-market-strip"', app_source)
        self.assertIn('class="ticker-pill"', app_source)
        self.assertNotIn('t("labels.source")', live_section)
        self.assertNotIn("livePayload?.data_source", app_source)
        self.assertIn("--bg: #0f1318;", style_source)
        self.assertIn("--chart-bg: #131722;", style_source)
        self.assertIn(".live-market-strip", style_source)
        self.assertIn('textColor: "#d1d4dc"', chart_source)
        self.assertIn('color: "#131722"', chart_source)

    def test_frontend_routes_allow_direct_view_urls(self):
        self.assertTrue(is_frontend_route("/"))
        self.assertTrue(is_frontend_route("/markets"))
        self.assertTrue(is_frontend_route("/live"))
        self.assertTrue(is_frontend_route("/chart"))
        self.assertTrue(is_frontend_route("/moex-live"))
        self.assertTrue(is_frontend_route("/russian-live"))
        self.assertTrue(is_frontend_route("/breadth"))
        self.assertTrue(is_frontend_route("/futoi"))
        self.assertFalse(is_frontend_route("/lab"))
        self.assertTrue(is_frontend_route("/feedback"))
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

    def test_breadth_scalar_charts_render_as_derived_candles_instead_of_lines(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )
        chart_source = (
            root / "frontend" / "src" / "components" / "TradingViewChart.vue"
        ).read_text(encoding="utf-8")

        self.assertIn("deriveCandlesFromClose?: boolean;", chart_source)
        self.assertIn("deriveCandlesFromClose: false", chart_source)
        self.assertIn("function toDerivedCandleData(candles: Candle[]): CandlestickData[]", chart_source)
        self.assertIn("const open = previousClose ?? close;", chart_source)
        self.assertIn("derive-candles-from-close", app_source)
        self.assertNotIn('series-type="line"', app_source)

    def test_breadth_page_uses_overview_and_large_detail_layout(self):
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

        self.assertIn("const breadthGroupSummaries = computed<BreadthGroupSummary[]>(() =>", app_source)
        self.assertIn('class="breadth-overview-grid"', app_source)
        self.assertIn('class="breadth-detail-stack"', app_source)
        self.assertIn('class="breadth-detail-section"', app_source)
        self.assertIn('class="breadth-metric-card"', app_source)
        self.assertLess(
            breadth_loaded_source.index('class="breadth-put-call"'),
            breadth_loaded_source.index('class="breadth-overview-grid"'),
        )
        self.assertLess(
            breadth_loaded_source.index('class="breadth-overview-grid"'),
            breadth_loaded_source.index('class="breadth-detail-stack"'),
        )
        self.assertIn(".breadth-overview-grid {\n  display: grid;", style_source)
        self.assertIn(".breadth-detail-section {\n  display: grid;", style_source)
        self.assertIn("grid-auto-flow: column;", style_source)
        self.assertIn("grid-auto-columns: minmax(420px, 1fr);", style_source)
        self.assertIn("overflow-x: auto;", style_source)
        self.assertNotIn("grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));", style_source)
        self.assertIn(".breadth-metric-chart .tv-chart {\n  height: 390px;", style_source)
        self.assertIn(".breadth-put-call .tv-chart {\n  height: 440px;", style_source)
        self.assertIn(".breadth-metric-chart .tv-chart {\n    height: 320px;", style_source)
        self.assertNotIn('class="breadth-card"', breadth_loaded_source)

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
        self.assertIsNone(payload["rsi_alert_signal"])

    def test_live_chart_payload_accepts_empty_strategy_without_markers(self):
        client = FakeClient()
        client.candles = trending_candles()

        payload = live_chart_payload(
            {
                "symbol": "BTCUSDT",
                "interval": "1h",
                "limit": 12,
                "strategy": "",
                "fast_ema": 1,
                "slow_ema": 3,
                "rsi_period": 2,
                "rsi_overbought": 100,
                "rsi_oversold": 0,
            },
            client=client,
        )

        self.assertIsNone(payload["strategy"])
        self.assertEqual(payload["signals"], [])
        self.assertIsNone(payload["rsi_alert_signal"])
        self.assertIn("indicators", payload)

    def test_live_chart_payload_adds_volume_spike_events(self):
        client = FakeClient()
        client.candles = [
            Candle(index, 10.0, 11.0, 9.0, 10.0, volume)
            for index, volume in enumerate([100.0, 120.0, 80.0, 360.0])
        ]

        payload = live_chart_payload(
            {
                "symbol": "BTCUSDT",
                "interval": "1h",
                "limit": 4,
                "strategy": "",
            },
            client=client,
        )

        volume_events = [
            event for event in payload["events"] if event["type"] == "volume_spike"
        ]
        self.assertEqual(len(volume_events), 1)
        self.assertEqual(volume_events[0]["symbol"], "BTCUSDT")
        self.assertEqual(volume_events[0]["metrics"]["volume_ratio"], 3.6)

    def test_live_chart_payload_exposes_latest_rsi_alert_signal(self):
        client = FakeClient()
        client.candles = [
            candle(index, price)
            for index, price in enumerate([10, 9, 8, 7, 8])
        ]

        payload = live_chart_payload(
            {
                "symbol": "BTCUSDT",
                "interval": "5m",
                "limit": 5,
                "strategy": "ema-rsi",
                "rsi_period": 2,
                "rsi_overbought": 100,
                "rsi_oversold": 0,
            },
            client=client,
        )

        self.assertEqual(payload["rsi_alert_signal"]["reason"], "rsi_reversal_long")
        self.assertEqual(payload["rsi_alert_signal"]["time"], 4)

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
        volume_points = indicator_by_id["volume"]["series"][0]["points"]
        self.assertEqual(volume_points[0]["color"], "#22ab94")
        self.assertEqual(volume_points[8]["color"], "#f23645")
        self.assertEqual(indicator_by_id["rsi"]["pane"], "oscillator")
        self.assertEqual(indicator_by_id["macd"]["series"][2]["type"], "histogram")
        for indicator in indicators:
            self.assertTrue(indicator["label"])
            self.assertTrue(indicator["series"])
            for series in indicator["series"]:
                self.assertEqual(len(series["points"]), 40)
                self.assertEqual(series["points"][0]["time"], 0)
                self.assertIsInstance(series["points"][0]["value"], float)

    def test_live_chart_payload_adds_algopack_indicators_for_russian_stocks(self):
        first_time = int(datetime(2024, 4, 8, 7, 5, tzinfo=timezone.utc).timestamp() * 1000)
        second_time = int(datetime(2024, 4, 8, 7, 10, tzinfo=timezone.utc).timestamp() * 1000)
        client = FakeClient()
        client.candles = [
            Candle(open_time=first_time, open=300, high=301, low=299, close=300, volume=10),
            Candle(open_time=second_time, open=301, high=302, low=300, close=301, volume=11),
        ]
        store = InMemoryHistoricalDataStore()
        store.upsert_algopack_records(
            [
                AlgoPackRecord(
                    dataset="tradestats",
                    market="russian_bluechips",
                    ticker="SBER",
                    trade_date=date(2024, 4, 8),
                    trade_time="10:05:00",
                    metrics={"vol": 100, "disb": 0.25},
                ),
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
                    metrics={"spread_bbo": 0.1, "imbalance_val_bbo": -0.2},
                ),
                AlgoPackRecord(
                    dataset="alerts",
                    market="russian_bluechips",
                    ticker="SBER",
                    trade_date=date(2024, 4, 8),
                    trade_time="10:05:00",
                    metrics={"alert_type": "pr_high_max", "threshold": 307.77, "value": 308.04},
                ),
                AlgoPackRecord(
                    dataset="alerts",
                    market="russian_bluechips",
                    ticker="SBER",
                    trade_date=date(2024, 4, 8),
                    trade_time="10:05:00",
                    metrics={"alert_type": "vol_b_99_9_pctl", "threshold": 61475, "value": 78552},
                ),
            ],
            source="unit-test",
        )

        payload = live_chart_payload(
            {
                "market": "russian_bluechips",
                "symbol": "SBER",
                "interval": "5m",
                "limit": 2,
                "algopack": "tradestats,orderstats,obstats,alerts",
            },
            client=client,
            historical_store=store,
        )

        algopack_indicators = {
            indicator["id"]: indicator
            for indicator in payload["indicators"]
            if str(indicator["id"]).startswith("algopack-")
        }
        self.assertEqual(
            set(algopack_indicators),
            {"algopack-tradestats", "algopack-orderstats", "algopack-obstats", "algopack-alerts"},
        )
        self.assertEqual(algopack_indicators["algopack-tradestats"]["pane"], "volume")
        self.assertEqual(
            algopack_indicators["algopack-tradestats"]["series"][0]["points"][0],
            {"time": first_time, "value": 100.0},
        )
        self.assertEqual(
            algopack_indicators["algopack-orderstats"]["series"][0]["points"][0]["value"],
            12.0,
        )
        self.assertEqual(
            algopack_indicators["algopack-obstats"]["series"][1]["points"][0]["value"],
            -0.2,
        )
        self.assertEqual(
            algopack_indicators["algopack-alerts"]["series"][0]["points"][0],
            {"time": first_time, "value": 2.0},
        )
        event_types = {event["type"] for event in payload["events"]}
        self.assertIn("mega_alert", event_types)
        self.assertNotIn("order_stats", event_types)
        self.assertNotIn("open_interest_stats", event_types)

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
        self.assertEqual(payload["data_source"], "MOEX shares")
        self.assertEqual(payload["symbol"], "SBER")

    def test_live_chart_payload_labels_combined_moex_indices_futures_source(self):
        client = FakeClient()
        client.candles = [candle(index, price) for index, price in enumerate([300, 301, 302, 303, 304])]

        payload = live_chart_payload(
            {
                "market": "russian_indices_futures",
                "symbol": "IMOEX",
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

        self.assertEqual(client.kline_symbols, ["IMOEX"])
        self.assertEqual(payload["market"], "russian_indices_futures")
        self.assertEqual(payload["data_source"], "MOEX APIM indices and futures")
        self.assertEqual(payload["symbol"], "IMOEX")

    def test_live_chart_payload_keeps_old_moex_futures_alias_working(self):
        client = FakeClient()
        client.candles = [candle(index, price) for index, price in enumerate([300, 301, 302, 303, 304])]

        payload = live_chart_payload(
            {
                "market": "russian_futures",
                "symbol": "RIM6",
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

        self.assertEqual(client.kline_symbols, ["RIM6"])
        self.assertEqual(payload["market"], "russian_indices_futures")
        self.assertEqual(payload["data_source"], "MOEX APIM indices and futures")
        self.assertEqual(payload["symbol"], "RIM6")

    def test_live_chart_payload_accepts_commodities_market(self):
        client = FakeClient()
        client.candles = [candle(index, price) for index, price in enumerate([2000, 2001, 2002, 2003, 2004])]

        payload = live_chart_payload(
            {
                "market": "commodities",
                "symbol": "GC=F",
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

        self.assertEqual(client.kline_symbols, ["GC=F"])
        self.assertEqual(payload["market"], "commodities")
        self.assertEqual(payload["data_source"], "Yahoo Finance delayed commodity futures")
        self.assertEqual(payload["symbol"], "GC=F")

    def test_live_chart_payload_accepts_mag7_stock_market(self):
        client = FakeClient()
        client.candles = [candle(index, price) for index, price in enumerate([200, 201, 202, 203, 204])]

        payload = live_chart_payload(
            {
                "market": "mag7_stocks",
                "symbol": "nvda",
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

        self.assertEqual(client.kline_symbols, ["NVDA"])
        self.assertEqual(payload["market"], "mag7_stocks")
        self.assertEqual(payload["data_source"], "Yahoo Finance delayed US equities")
        self.assertEqual(payload["symbol"], "NVDA")

    def test_live_chart_payload_accepts_hong_kong_stock_market(self):
        client = FakeClient()
        client.candles = [candle(index, price) for index, price in enumerate([100, 101, 102, 103, 104])]

        payload = live_chart_payload(
            {
                "market": "hong_kong_stocks",
                "symbol": "9988.hk",
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

        self.assertEqual(client.kline_symbols, ["9988.HK"])
        self.assertEqual(payload["market"], "hong_kong_stocks")
        self.assertEqual(payload["data_source"], "Yahoo Finance delayed Hong Kong stocks")
        self.assertEqual(payload["symbol"], "9988.HK")

    def test_market_data_client_from_payload_selects_futures_provider(self):
        self.assertIsInstance(
            market_data_client_from_payload({"market": "cme_futures"}),
            YahooFuturesMarketDataClient,
        )
        self.assertIsInstance(
            market_data_client_from_payload({"market": "commodities"}),
            YahooFuturesMarketDataClient,
        )
        self.assertIsInstance(
            market_data_client_from_payload({"market": "mag7_stocks"}),
            YahooFuturesMarketDataClient,
        )
        self.assertIsInstance(
            market_data_client_from_payload({"market": "hong_kong_stocks"}),
            YahooFuturesMarketDataClient,
        )
        self.assertIsInstance(
            market_data_client_from_payload({"market": "russian_bluechips"}),
            MoexSharesMarketDataClient,
        )
        self.assertIsInstance(
            market_data_client_from_payload({"market": "russian_indices"}),
            MoexSharesMarketDataClient,
        )
        self.assertIsInstance(
            market_data_client_from_payload({"market": "russian_indices_futures"}),
            MoexSharesMarketDataClient,
        )
        self.assertIsInstance(
            market_data_client_from_payload({"market": "russian_futures"}),
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

    def test_live_chart_payload_persists_and_returns_db_candles(self):
        client = FakeClient()
        client.candles = [candle(2000, 12), candle(3000, 13)]
        store = InMemoryHistoricalDataStore()
        store.upsert_candles(
            "crypto_spot",
            "BTCUSDT",
            "5m",
            [candle(1000, 11)],
            source="seed",
        )

        payload = live_chart_payload(
            {
                "market": "crypto_spot",
                "symbol": "BTCUSDT",
                "interval": "5m",
                "limit": 3,
                "fast_ema": 1,
                "slow_ema": 2,
                "rsi_period": 2,
                "rsi_overbought": 100,
                "rsi_oversold": 0,
            },
            client=client,
            historical_store=store,
        )

        self.assertEqual(
            [item["time"] for item in payload["candles"]],
            [1000, 2000, 3000],
        )
        self.assertEqual(
            [
                stored.open_time
                for stored in store.load_candles("crypto_spot", "BTCUSDT", "5m")
            ],
            [1000, 2000, 3000],
        )

    def test_live_chart_payload_uses_fresh_stored_candles_without_provider_call(self):
        client = FakeClient()
        store = InMemoryHistoricalDataStore()
        latest_open_time = int(time.time() * 1000) - (60 * 1000)
        store.upsert_candles(
            "crypto_spot",
            "BTCUSDT",
            "5m",
            [
                candle(latest_open_time - (5 * 60 * 1000), 11),
                candle(latest_open_time, 12),
            ],
            source="seed",
        )

        payload = live_chart_payload(
            {
                "market": "crypto_spot",
                "symbol": "BTCUSDT",
                "interval": "5m",
                "limit": 2,
                "fast_ema": 1,
                "slow_ema": 2,
                "rsi_period": 2,
                "rsi_overbought": 100,
                "rsi_oversold": 0,
            },
            client=client,
            historical_store=store,
        )

        self.assertEqual(client.kline_symbols, [])
        self.assertEqual(
            [item["time"] for item in payload["candles"]],
            [latest_open_time - (5 * 60 * 1000), latest_open_time],
        )

    def test_live_chart_payload_can_return_stale_cache_without_provider_call(self):
        client = FakeClient()
        client.candles = [candle(3000, 13), candle(4000, 14)]
        store = InMemoryHistoricalDataStore()
        store.upsert_candles(
            "crypto_spot",
            "BTCUSDT",
            "5m",
            [candle(1000, 11), candle(2000, 12)],
            source="seed",
        )
        cache_state: dict[str, bool] = {}

        payload = live_chart_payload(
            {
                "market": "crypto_spot",
                "symbol": "BTCUSDT",
                "interval": "5m",
                "limit": 2,
                "fast_ema": 1,
                "slow_ema": 2,
                "rsi_period": 2,
                "rsi_overbought": 100,
                "rsi_oversold": 0,
            },
            client=client,
            historical_store=store,
            allow_stale_cache=True,
            cache_state=cache_state,
        )

        self.assertEqual(client.kline_symbols, [])
        self.assertEqual([item["time"] for item in payload["candles"]], [1000, 2000])
        self.assertEqual(cache_state, {"cache_hit": True, "cache_stale": True})

if __name__ == "__main__":
    unittest.main()
