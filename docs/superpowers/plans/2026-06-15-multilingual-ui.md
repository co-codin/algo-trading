# Multilingual UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent English/Russian UI switching with flag buttons while keeping API behavior unchanged.

**Architecture:** Add a focused `frontend/src/i18n.ts` module for locale metadata, message lookup, and strategy-description lookup. Wire `frontend/src/App.vue` to own locale state and render translated UI, then pass translated chart labels into `TradingViewChart.vue`.

**Tech Stack:** Vue 3 Composition API, TypeScript, Vite, Python `unittest` source assertions, existing `make check` validation.

---

## File Structure

- Create: `frontend/src/i18n.ts`
  - Owns locale types, supported locale metadata, message dictionaries, strategy description dictionaries, and lookup helpers.
- Modify: `frontend/src/App.vue`
  - Imports i18n helpers, stores active locale in `localStorage`, renders translated text, creates translated option arrays, and renders the flag switcher.
- Modify: `frontend/src/components/TradingViewChart.vue`
  - Adds optional label props for chart aria text, empty state, and marker prefixes.
- Modify: `frontend/src/style.css`
  - Adds compact topbar language switcher styles and mobile-safe wrapping.
- Modify: `tests/test_ui.py`
  - Adds source-level tests for the i18n contract, switcher, localStorage persistence, strategy-description mapping, and chart label props.

## Task 1: Lock The Localization Contract With Failing Tests

**Files:**
- Modify: `tests/test_ui.py`
- Test: `tests/test_ui.py`

- [ ] **Step 1: Add source tests for i18n and language switcher**

Add these test methods to `UiTests` after `test_frontend_exposes_combination_signals_page`:

```python
    def test_frontend_defines_bilingual_i18n_contract(self):
        root = Path(__file__).resolve().parents[1]
        i18n_source = (root / "frontend" / "src" / "i18n.ts").read_text(
            encoding="utf-8"
        )
        app_source = (root / "frontend" / "src" / "App.vue").read_text(
            encoding="utf-8"
        )

        self.assertIn('export type Locale = "en" | "ru";', i18n_source)
        self.assertIn("SUPPORTED_LOCALES", i18n_source)
        self.assertIn('flag: "🇺🇸"', i18n_source)
        self.assertIn('flag: "🇷🇺"', i18n_source)
        self.assertIn("algoTradingLocale", i18n_source)
        self.assertIn("messages.en", i18n_source)
        self.assertIn("messages.ru", i18n_source)
        self.assertIn("strategyDescriptions", i18n_source)
        self.assertIn("translateStrategyDescription", i18n_source)
        self.assertIn("setLocale", app_source)
        self.assertIn("localStorage.setItem(LOCALE_STORAGE_KEY", app_source)
        self.assertIn('class="language-switcher"', app_source)
        self.assertIn("SUPPORTED_LOCALES", app_source)

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
```

- [ ] **Step 2: Run the new focused tests and verify they fail**

Run:

```bash
python -m pytest tests/test_ui.py::UiTests::test_frontend_defines_bilingual_i18n_contract tests/test_ui.py::UiTests::test_chart_accepts_translated_labels_from_parent -q
```

Expected: both tests fail because `frontend/src/i18n.ts` does not exist and chart label props are not defined.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_ui.py
git commit -m "Specify bilingual frontend UI contract" -m "Constraint: Tests define the approved frontend-only localization scope before production edits.
Rejected: Backend localization tests | backend translation is outside approved scope.
Confidence: high
Scope-risk: narrow
Directive: Keep API payload fields and backend error text unchanged.
Tested: Focused pytest command fails before implementation as expected.
Not-tested: Full suite deferred until implementation."
```

## Task 2: Add The Frontend I18n Module

**Files:**
- Create: `frontend/src/i18n.ts`
- Test: `tests/test_ui.py`

- [ ] **Step 1: Implement locale metadata and lookup helpers**

Create `frontend/src/i18n.ts` with:

```ts
export type Locale = "en" | "ru";

export type LocaleMeta = {
  code: Locale;
  label: string;
  flag: string;
};

export const LOCALE_STORAGE_KEY = "algoTradingLocale";

export const SUPPORTED_LOCALES: LocaleMeta[] = [
  { code: "en", label: "EN", flag: "🇺🇸" },
  { code: "ru", label: "RU", flag: "🇷🇺" },
];

type MessageKey =
  | "app.title"
  | "app.subtitle"
  | "app.safety"
  | "tabs.backtest"
  | "tabs.paper"
  | "tabs.live"
  | "tabs.combos"
  | "tabs.runs"
  | "tabs.lab"
  | "status.ready"
  | "status.loadingSymbols"
  | "status.loadedSymbols"
  | "status.paperRunning"
  | "status.backtestRunning"
  | "status.loadingChart"
  | "status.updated"
  | "status.comboRunning"
  | "status.updatedSignals"
  | "status.labRunning"
  | "status.rankedResults"
  | "pages.paperTrading"
  | "pages.backtest"
  | "pages.output"
  | "pages.liveMarket"
  | "pages.combinationSignals"
  | "pages.comboResult"
  | "pages.runs"
  | "pages.strategyLab"
  | "pages.strategyLabSubtitle"
  | "pages.ranking"
  | "actions.runPaper"
  | "actions.runBacktest"
  | "actions.loadTop"
  | "actions.refreshChart"
  | "actions.runCombo"
  | "actions.refresh"
  | "actions.open"
  | "actions.runLab"
  | "actions.exportCsv"
  | "labels.symbol"
  | "labels.symbols"
  | "labels.top"
  | "labels.interval"
  | "labels.candles"
  | "labels.side"
  | "labels.strategy"
  | "labels.preset"
  | "labels.startingUsdt"
  | "labels.positionFraction"
  | "labels.feeRate"
  | "labels.slippage"
  | "labels.fastEma"
  | "labels.slowEma"
  | "labels.rsiPeriod"
  | "labels.rsiOverbought"
  | "labels.rsiOversold"
  | "labels.rsiMidline"
  | "labels.macdSignal"
  | "labels.bollingerPeriod"
  | "labels.bollingerStddev"
  | "labels.donchianPeriod"
  | "labels.atrPeriod"
  | "labels.supertrendMultiplier"
  | "labels.vwapPeriod"
  | "labels.vwapThreshold"
  | "labels.stochRsiPeriod"
  | "labels.emaRibbonFast"
  | "labels.emaRibbonMid"
  | "labels.emaRibbonSlow"
  | "labels.momentumPeriod"
  | "labels.keltnerMultiplier"
  | "labels.cciPeriod"
  | "labels.cciOversold"
  | "labels.cciOverbought"
  | "labels.williamsPeriod"
  | "labels.williamsOversold"
  | "labels.williamsOverbought"
  | "labels.volumePeriod"
  | "labels.volumeMultiplier"
  | "labels.squeezeThreshold"
  | "labels.stopLoss"
  | "labels.takeProfit"
  | "labels.trailingStop"
  | "labels.retries"
  | "labels.retryDelay"
  | "labels.iterations"
  | "labels.pollSeconds"
  | "labels.source"
  | "labels.market"
  | "labels.signals"
  | "labels.paper"
  | "labels.refreshSec"
  | "labels.strategyMarkers"
  | "labels.paperMarkers"
  | "labels.memberStrategies"
  | "labels.entryConfirms"
  | "labels.exitConfirms"
  | "labels.lookback"
  | "labels.fastPeriod"
  | "labels.slowPeriod"
  | "labels.strategies"
  | "labels.presets"
  | "labels.benchmarks"
  | "labels.walkWindows"
  | "labels.walkMinCandles"
  | "options.both"
  | "options.longOnly"
  | "options.shortOnly"
  | "options.cryptoSpot"
  | "options.usIndexFutures"
  | "options.sp500Future"
  | "options.allStrategies"
  | "empty.noRunOutput"
  | "empty.loadChart"
  | "empty.runCombo"
  | "empty.noRuns"
  | "empty.selectRun"
  | "empty.runLab"
  | "empty.noCandles"
  | "metrics.final"
  | "metrics.trades"
  | "metrics.return"
  | "metrics.winRate"
  | "metrics.maxDd"
  | "metrics.profitFactor"
  | "table.rank"
  | "table.symbol"
  | "table.strategy"
  | "table.preset"
  | "table.return"
  | "table.maxDd"
  | "table.trades"
  | "table.pf"
  | "table.sharpe"
  | "table.sortino"
  | "table.exposure"
  | "table.worst"
  | "table.wfAvg"
  | "table.wfWin"
  | "table.side"
  | "table.entry"
  | "table.exit"
  | "table.pnl"
  | "chart.aria"
  | "chart.longSignal"
  | "chart.shortSignal"
  | "chart.paperEntry"
  | "chart.paperExit"
  | "chart.tradingView";

export const messages: Record<Locale, Record<MessageKey, string>> = {
  en: {
    "app.title": "Algo Trading",
    "app.subtitle": "Vue control panel for read-only backtesting, paper trading, live charts, and strategy ranking.",
    "app.safety": "Simulated only: no real orders"
  },
  ru: {
    "app.title": "Algo Trading",
    "app.subtitle": "Панель Vue для безопасного бэктеста, бумажной торговли, живых графиков и рейтинга стратегий.",
    "app.safety": "Только симуляция: реальных заявок нет"
  }
};

export function normalizeLocale(value: string | null | undefined): Locale {
  return value === "ru" ? "ru" : "en";
}

export function translate(locale: Locale, key: MessageKey): string {
  return messages[locale][key] ?? messages.en[key] ?? key;
}
```

Then complete the `messages.en` and `messages.ru` objects for every `MessageKey` in the union, preserving short trading-terminal labels where possible.

- [ ] **Step 2: Add strategy descriptions to the module**

Append:

```ts
export const strategyDescriptions: Record<Locale, Record<string, string>> = {
  en: {
    "ema-rsi": "EMA crossover filtered by RSI",
    macd: "MACD line crossing its signal line",
    "bollinger-reversion": "Mean reversion after reclaiming Bollinger bands",
    "donchian-breakout": "Breakout above or below the previous Donchian channel",
    "rsi-reversal": "RSI leaving extreme levels and reverting toward the midpoint",
    supertrend: "ATR SuperTrend-style trend flip",
    "vwap-reversion": "Mean reversion after reclaiming rolling VWAP",
    "stoch-rsi-reversal": "Stochastic RSI leaving extreme levels",
    "ema-ribbon": "EMA ribbon alignment trend following",
    "momentum-scalping": "Short-term momentum with RSI and MACD confirmation",
    "keltner-breakout": "Keltner channel breakout using ATR width",
    "ema-pullback": "Trend continuation when price reclaims the fast EMA",
    "atr-trailing-trend": "ATR trailing trend following on direction flips",
    "cci-reversal": "CCI reversal after leaving extreme levels",
    "williams-r-reversal": "Williams %R reversal after leaving extreme levels",
    "bollinger-squeeze-release": "Bollinger squeeze expansion breakout",
    "obv-trend": "OBV trend confirmation with price trend",
    "volume-breakout": "Donchian breakout confirmed by above-average volume",
    "vwap-trend-continuation": "VWAP trend continuation with EMA confirmation",
    "sma-crossover": "Simple moving average crossover baseline",
    "combined-signals": "Configurable strategy confirmation ensemble"
  },
  ru: {
    "ema-rsi": "Пересечение EMA с фильтром RSI",
    macd: "Пересечение линии MACD и сигнальной линии",
    "bollinger-reversion": "Возврат к среднему после восстановления в полосах Боллинджера",
    "donchian-breakout": "Пробой выше или ниже предыдущего канала Дончиана",
    "rsi-reversal": "Выход RSI из экстремумов с возвратом к середине",
    supertrend: "Разворот тренда по ATR SuperTrend",
    "vwap-reversion": "Возврат к среднему после восстановления к скользящему VWAP",
    "stoch-rsi-reversal": "Выход Stochastic RSI из экстремальных зон",
    "ema-ribbon": "Следование тренду по выравниванию ленты EMA",
    "momentum-scalping": "Краткосрочный импульс с подтверждением RSI и MACD",
    "keltner-breakout": "Пробой канала Кельтнера с шириной по ATR",
    "ema-pullback": "Продолжение тренда после возврата цены к быстрой EMA",
    "atr-trailing-trend": "Следование тренду по ATR-трейлингу при смене направления",
    "cci-reversal": "Разворот CCI после выхода из экстремальных зон",
    "williams-r-reversal": "Разворот Williams %R после выхода из экстремальных зон",
    "bollinger-squeeze-release": "Пробой после расширения сжатия Боллинджера",
    "obv-trend": "Подтверждение ценового тренда индикатором OBV",
    "volume-breakout": "Пробой Дончиана с подтверждением повышенным объемом",
    "vwap-trend-continuation": "Продолжение VWAP-тренда с подтверждением EMA",
    "sma-crossover": "Базовая стратегия пересечения простых скользящих средних",
    "combined-signals": "Настраиваемый ансамбль подтверждающих стратегий"
  }
};

export function translateStrategyDescription(
  locale: Locale,
  name: string,
  fallback: string,
): string {
  return strategyDescriptions[locale][name] ?? strategyDescriptions.en[name] ?? fallback;
}
```

- [ ] **Step 3: Run focused contract test**

Run:

```bash
python -m pytest tests/test_ui.py::UiTests::test_frontend_defines_bilingual_i18n_contract -q
```

Expected: still fails until `App.vue` imports and uses the i18n module.

## Task 3: Wire Locale State And Translated UI In App.vue

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`
- Test: `tests/test_ui.py`

- [ ] **Step 1: Import i18n helpers and add locale state**

Update the script imports in `frontend/src/App.vue`:

```ts
import {
  LOCALE_STORAGE_KEY,
  SUPPORTED_LOCALES,
  normalizeLocale,
  translate,
  translateStrategyDescription,
  type Locale,
} from "./i18n";
```

Add after `let liveTimer = 0;`:

```ts
const locale = ref<Locale>(normalizeLocale(window.localStorage.getItem(LOCALE_STORAGE_KEY)));

function t(key: Parameters<typeof translate>[1]): string {
  return translate(locale.value, key);
}

function setLocale(nextLocale: Locale) {
  locale.value = nextLocale;
  localStorage.setItem(LOCALE_STORAGE_KEY, nextLocale);
}
```

- [ ] **Step 2: Convert static option arrays to computed translated arrays**

Replace static tab and option labels with computed values:

```ts
const tabs = computed(() => [
  { mode: "backtest" as const, label: t("tabs.backtest") },
  { mode: "paper" as const, label: t("tabs.paper") },
  { mode: "live" as const, label: t("tabs.live") },
  { mode: "combos" as const, label: t("tabs.combos") },
  { mode: "runs" as const, label: t("tabs.runs") },
  { mode: "lab" as const, label: t("tabs.lab") },
]);

const liveMarketOptions = computed<SelectOption[]>(() => [
  { value: "crypto_spot", label: t("options.cryptoSpot") },
  { value: "cme_futures", label: t("options.usIndexFutures") },
]);

const liveFuturesSymbolOptions = computed<SelectOption[]>(() => [
  { value: "ES=F", label: t("options.sp500Future") },
]);
```

Keep symbol and numeric interval/candle options stable. Update users of computed arrays to read `.value` inside script:

```ts
const liveSymbolsByMarket = computed<Record<string, SelectOption[]>>(() => ({
  crypto_spot: liveSymbolOptions,
  cme_futures: liveFuturesSymbolOptions.value,
}));

const activeLiveSymbolOptions = computed(
  () => liveSymbolsByMarket.value[liveMarket.value] ?? liveSymbolOptions,
);
```

- [ ] **Step 3: Translate status setters**

Replace status message calls with `t(...)`:

```ts
const status = ref(t("status.ready"));
const liveStatus = ref(t("status.ready"));
const comboStatus = ref(t("status.ready"));
const labStatus = ref(t("status.ready"));
```

Use interpolation for dynamic messages:

```ts
setStatus(`${t("status.loadedSymbols")} ${payload.symbols.length}`);
setLiveStatus(`${t("status.updated")} ${new Date().toLocaleTimeString()}`);
setComboStatus(`${t("status.updatedSignals")} ${comboPayload.value.signals.length}`);
setLabStatus(`${t("status.rankedResults")} ${payload.rows.length}`);
```

Add a locale watcher so idle statuses re-render:

```ts
watch(locale, () => {
  if (!statusType.value) status.value = t("status.ready");
  if (!liveStatusType.value) liveStatus.value = t("status.ready");
  if (!comboStatusType.value) comboStatus.value = t("status.ready");
  if (!labStatusType.value) labStatus.value = t("status.ready");
});
```

- [ ] **Step 4: Translate strategy descriptions**

Update strategy computed helpers:

```ts
const liveStrategyOptions = computed(() => [
  { name: "all", description: t("options.allStrategies") },
  ...strategies.value.map((strategy) => ({
    ...strategy,
    description: translateStrategyDescription(locale.value, strategy.name, strategy.description),
  })),
]);

const activeLiveStrategyLabel = computed(() =>
  settings.strategy === "all" ? t("options.allStrategies") : strategyLabel(settings.strategy),
);

function strategyLabel(name: string): string {
  const strategy = strategies.value.find((item) => item.name === name);
  return translateStrategyDescription(locale.value, name, strategy?.description ?? name);
}
```

- [ ] **Step 5: Add chart label computed values**

Add:

```ts
const chartLabels = computed(() => ({
  aria: t("chart.aria"),
  empty: t("empty.noCandles"),
  longSignal: t("chart.longSignal"),
  shortSignal: t("chart.shortSignal"),
  paperEntry: t("chart.paperEntry"),
  paperExit: t("chart.paperExit"),
}));
```

- [ ] **Step 6: Translate the template and add switcher markup**

Replace hardcoded browser UI strings with `t(...)`. Add this topbar action markup next to the safety badge:

```vue
    <div class="topbar-actions">
      <div class="language-switcher" aria-label="Language">
        <button
          v-for="item in SUPPORTED_LOCALES"
          :key="item.code"
          type="button"
          class="language-option"
          :class="{ 'is-active': locale === item.code }"
          @click="setLocale(item.code)"
        >
          <span aria-hidden="true">{{ item.flag }}</span>
          <span>{{ item.label }}</span>
        </button>
      </div>
      <div class="safety">{{ t("app.safety") }}</div>
    </div>
```

Pass chart label props into each `TradingViewChart` usage:

```vue
          :aria-label="chartLabels.aria"
          :empty-label="chartLabels.empty"
          :paper-entry-label="chartLabels.paperEntry"
          :paper-exit-label="chartLabels.paperExit"
          :long-signal-label="chartLabels.longSignal"
          :short-signal-label="chartLabels.shortSignal"
```

- [ ] **Step 7: Add topbar switcher CSS**

Append near the existing topbar styles in `frontend/src/style.css`:

```css
.topbar-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 10px;
}

.language-switcher {
  display: inline-flex;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: var(--field);
}

.language-option {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 32px;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}

.language-option.is-active {
  background: var(--primary);
  color: #fff;
}
```

In the existing `@media (max-width: 1060px)` block, add:

```css
  .topbar-actions {
    justify-content: space-between;
  }
```

In the existing `@media (max-width: 620px)` block, add:

```css
  .topbar-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .language-switcher {
    width: 100%;
  }

  .language-option {
    flex: 1 1 0;
    justify-content: center;
  }
```

- [ ] **Step 8: Run focused i18n test**

Run:

```bash
python -m pytest tests/test_ui.py::UiTests::test_frontend_defines_bilingual_i18n_contract -q
```

Expected: pass after App.vue and style wiring.

## Task 4: Add Chart Label Props And Complete Validation

**Files:**
- Modify: `frontend/src/components/TradingViewChart.vue`
- Modify: `tests/test_ui.py`
- Test: `tests/test_ui.py`, `frontend/src/components/TradingViewChart.vue`

- [ ] **Step 1: Add defaults-backed chart label props**

Replace the current `defineProps` call in `TradingViewChart.vue` with:

```ts
const props = withDefaults(defineProps<{
  candles: Candle[];
  signals: Marker[];
  paperMarkers: Marker[];
  showSignals: boolean;
  showPaper: boolean;
  resetKey: string;
  ariaLabel?: string;
  emptyLabel?: string;
  paperEntryLabel?: string;
  paperExitLabel?: string;
  longSignalLabel?: string;
  shortSignalLabel?: string;
}>(), {
  ariaLabel: "TradingView live market chart",
  emptyLabel: "No candles returned",
  paperEntryLabel: "Paper",
  paperExitLabel: "Exit",
  longSignalLabel: "Long",
  shortSignalLabel: "Short",
});
```

Use the props in marker builders and template:

```ts
text: markerLabel(props.longSignalLabel, marker.reason),
text: markerLabel(props.shortSignalLabel, marker.reason),
text: markerLabel(isEntry ? props.paperEntryLabel : props.paperExitLabel, marker.reason),
```

```vue
  <div v-if="candles.length" ref="chartEl" class="tv-chart" :aria-label="ariaLabel" />
  <div v-else class="empty">{{ emptyLabel }}</div>
```

- [ ] **Step 2: Run focused chart test**

Run:

```bash
python -m pytest tests/test_ui.py::UiTests::test_chart_accepts_translated_labels_from_parent -q
```

Expected: pass.

- [ ] **Step 3: Update existing source assertions affected by translated tabs**

Adjust tests that assert fixed English source literals so they assert translation keys or i18n use instead:

```python
self.assertIn('label: t("tabs.combos")', source)
self.assertIn('t("pages.combinationSignals")', source)
self.assertIn('t("actions.exportCsv")', source)
self.assertIn('t("options.allStrategies")', source)
self.assertIn('t("options.sp500Future")', source)
```

- [ ] **Step 4: Run Python UI tests**

Run:

```bash
python -m pytest tests/test_ui.py -q
```

Expected: pass.

- [ ] **Step 5: Run frontend typecheck/build**

Run:

```bash
npm run frontend:build
```

Expected: `vue-tsc --noEmit` and `vite build` complete with exit code 0.

- [ ] **Step 6: Run full project check**

Run:

```bash
make check
```

Expected: Python tests, mypy, compileall, and frontend build complete with exit code 0.

- [ ] **Step 7: Commit implementation**

```bash
git add frontend/src/i18n.ts frontend/src/App.vue frontend/src/components/TradingViewChart.vue frontend/src/style.css tests/test_ui.py algo_trading/web/dist
git commit -m "Add bilingual trading UI controls" -m "Constraint: User requested English/Russian UI with flag switching on main.
Rejected: Backend/API localization | outside approved scope and would alter server contracts.
Confidence: high
Scope-risk: moderate
Directive: Keep strategy IDs, symbols, routes, and API payload fields stable across locales.
Tested: python -m pytest tests/test_ui.py -q; npm run frontend:build; make check
Not-tested: Manual browser language toggle smoke test if no dev server is running."
```

## Self-Review Checklist

- Spec coverage: all approved requirements map to tasks 2 through 4.
- Placeholder scan: no unresolved placeholder markers or unnamed edge handling is allowed in this plan.
- Type consistency: `Locale`, `MessageKey`, `translate`, `translateStrategyDescription`, `chartLabels`, and chart prop names are consistent across tasks.
- Scope control: backend/API localization remains excluded.
