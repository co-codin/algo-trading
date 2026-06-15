<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { requestJson, toQuery } from "./api";
import TradingViewChart from "./components/TradingViewChart.vue";
import {
  LOCALE_STORAGE_KEY,
  SUPPORTED_LOCALES,
  normalizeLocale,
  translate,
  translateStrategyDescription,
  type Locale,
  type MessageKey,
} from "./i18n";
import type {
  AuthMePayload,
  AuthPayload,
  AuthUser,
  CombinationSignalsPayload,
  LiveChartPayload,
  MarketBreadthBar,
  MarketBreadthPayload,
  Mode,
  Marker,
  RunCard,
  RunDetails,
  StrategyInfo,
  StrategyLabPayload,
  StrategyLabRow,
  StrategyPayload,
  SymbolInfo,
} from "./types";

type StatusType = "" | "busy" | "error";
type SelectOption = {
  label: string;
  value: string | number;
};
type SignalDisplayMode = "consensus" | "individual";

const routeModes: Record<string, Mode> = {
  "/": "backtest",
  "/backtest": "backtest",
  "/paper": "paper",
  "/live": "live",
  "/chart": "live",
  "/breadth": "breadth",
  "/runs": "runs",
  "/history": "runs",
  "/lab": "lab",
  "/combos": "combos",
};

const modeRoutes: Record<Mode, string> = {
  backtest: "/backtest",
  paper: "/paper",
  live: "/live",
  breadth: "/breadth",
  runs: "/runs",
  lab: "/lab",
  combos: "/combos",
};

const liveSymbolOptions = [
  { value: "BTCUSDT", label: "BTCUSDT" },
  { value: "ETHUSDT", label: "ETHUSDT" },
] satisfies SelectOption[];

const liveIntervalOptions = [
  { value: "1m", label: "1m" },
  { value: "3m", label: "3m" },
  { value: "5m", label: "5m" },
  { value: "15m", label: "15m" },
  { value: "30m", label: "30m" },
  { value: "1h", label: "1h" },
  { value: "4h", label: "4h" },
  { value: "1d", label: "1d" },
] satisfies SelectOption[];

const liveCandleOptions = [
  { value: 80, label: "80" },
  { value: 180, label: "180" },
  { value: 300, label: "300" },
  { value: 500, label: "500" },
  { value: 1000, label: "1000" },
] satisfies SelectOption[];

const settings = reactive<Record<string, string>>({
  symbols: "BTCUSDT",
  top: "5",
  interval: "1h",
  limit: "300",
  allowed_side: "both",
  strategy: "ema-rsi",
  preset: "custom",
  starting_balance: "10000",
  position_fraction: "1",
  fee_rate: "0.001",
  slippage_rate: "0.0005",
  fast_ema: "12",
  slow_ema: "26",
  rsi_period: "14",
  rsi_overbought: "70",
  rsi_oversold: "30",
  rsi_midline: "50",
  macd_signal: "9",
  bollinger_period: "20",
  bollinger_stddev: "2",
  donchian_period: "20",
  atr_period: "14",
  supertrend_multiplier: "3",
  vwap_period: "20",
  vwap_threshold_pct: "0.01",
  stoch_rsi_period: "14",
  stoch_rsi_oversold: "20",
  stoch_rsi_overbought: "80",
  ema_ribbon_fast: "8",
  ema_ribbon_mid: "21",
  ema_ribbon_slow: "55",
  momentum_period: "10",
  keltner_multiplier: "2",
  cci_period: "20",
  cci_oversold: "-100",
  cci_overbought: "100",
  williams_period: "14",
  williams_oversold: "-80",
  williams_overbought: "-20",
  volume_period: "20",
  volume_multiplier: "1.5",
  squeeze_threshold_pct: "0.05",
  combo_strategies: "ema-rsi,macd,supertrend,sma-crossover",
  combo_entry_confirmations: "2",
  combo_exit_confirmations: "2",
  combo_lookback: "3",
  stop_loss_pct: "0.03",
  take_profit_pct: "0.06",
  trailing_stop_pct: "0",
  market_data_retries: "2",
  retry_delay: "0.5",
  walk_forward_windows: "3",
  walk_forward_min_candles: "30",
  iterations: "3",
  poll_seconds: "30",
});

const locale = ref<Locale>(normalizeLocale(window.localStorage.getItem(LOCALE_STORAGE_KEY)));
const authChecked = ref(false);
const authUser = ref<AuthUser | null>(null);
const authMode = ref<"login" | "register">("login");
const authForm = reactive({
  username: "",
  password: "",
});
const authStatus = ref("");
const authStatusType = ref<StatusType>("");

function t(key: MessageKey): string {
  return translate(locale.value, key);
}

function setLocale(nextLocale: Locale) {
  locale.value = nextLocale;
  localStorage.setItem(LOCALE_STORAGE_KEY, nextLocale);
}

const activeMode = ref<Mode>(modeFromLocation());
const strategies = ref<StrategyInfo[]>([]);
const presets = ref<string[]>(["custom", "conservative", "balanced", "aggressive"]);
const symbols = ref<SymbolInfo[]>([]);
const runs = ref<RunCard[]>([]);
const runDetails = ref<RunDetails | null>(null);
const outputRuns = ref<RunCard[]>([]);
const livePayload = ref<LiveChartPayload | null>(null);
const breadthPayload = ref<MarketBreadthPayload | null>(null);
const comboPayload = ref<CombinationSignalsPayload | null>(null);
const labRows = ref<StrategyLabRow[]>([]);
const status = ref(t("status.ready"));
const statusType = ref<StatusType>("");
const liveStatus = ref(t("status.ready"));
const liveStatusType = ref<StatusType>("");
const breadthStatus = ref(t("status.ready"));
const breadthStatusType = ref<StatusType>("");
const comboStatus = ref(t("status.ready"));
const comboStatusType = ref<StatusType>("");
const labStatus = ref(t("status.ready"));
const labStatusType = ref<StatusType>("");
const liveMarket = ref("crypto_spot");
const liveSymbol = ref("BTCUSDT");
const liveInterval = ref("1m");
const liveLimit = ref<string | number>(180);
const liveRefresh = ref("10");
const liveSignalDisplayMode = ref<SignalDisplayMode>("consensus");
const liveConsensusMinConfirmations = ref(2);
const showSignals = ref(true);
const comboSymbol = ref("BTCUSDT");
const comboInterval = ref("1h");
const comboLimit = ref<string | number>(300);
const labSymbols = ref("BTCUSDT,ETHUSDT,SOLUSDT");
const labStrategies = ref("all");
const labPresets = ref("custom,balanced,aggressive");
const labBenchmarkSymbols = ref("BTCUSDT,ES=F,NQ=F");
let liveTimer = 0;

const labCsvHeaders: (keyof StrategyLabRow)[] = [
  "rank",
  "symbol",
  "strategy",
  "preset",
  "final_balance",
  "total_return_pct",
  "max_drawdown_pct",
  "trades",
  "win_rate",
  "profit_factor",
  "sharpe_ratio",
  "sortino_ratio",
  "max_drawdown_duration",
  "average_trade_duration",
  "exposure_pct",
  "worst_trade",
  "walk_forward_windows",
  "walk_forward_avg_return_pct",
  "walk_forward_worst_return_pct",
  "walk_forward_best_return_pct",
  "walk_forward_profitable_pct",
];

const tabs = computed(() => [
  { mode: "backtest" as const, label: t("tabs.backtest") },
  { mode: "paper" as const, label: t("tabs.paper") },
  { mode: "live" as const, label: t("tabs.live") },
  { mode: "breadth" as const, label: t("tabs.breadth") },
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
const liveSymbolsByMarket = computed<Record<string, SelectOption[]>>(() => ({
  crypto_spot: liveSymbolOptions,
  cme_futures: liveFuturesSymbolOptions.value,
}));
const sideOptions = computed<SelectOption[]>(() => [
  { value: "both", label: t("options.both") },
  { value: "long-only", label: t("options.longOnly") },
  { value: "short-only", label: t("options.shortOnly") },
]);
const liveSignalDisplayOptions = computed<SelectOption[]>(() => [
  { value: "consensus", label: t("options.consensusSignals") },
  { value: "individual", label: t("options.individualSignals") },
]);
const strategyName = computed(() => strategyLabel(settings.strategy));
const liveStrategyOptions = computed(() => [
  { name: "all", description: t("options.allStrategies") },
  ...strategies.value.map((strategy) => ({
    ...strategy,
    description: translateStrategyDescription(locale.value, strategy.name, strategy.description),
  })),
]);
const activeLiveSymbolOptions = computed(
  () => liveSymbolsByMarket.value[liveMarket.value] ?? liveSymbolOptions,
);
const liveChartResetKey = computed(() =>
  [liveMarket.value, liveSymbol.value, liveInterval.value, liveLimit.value].join(":"),
);
const activeLiveStrategyLabel = computed(() =>
  settings.strategy === "all" ? t("options.allStrategies") : strategyLabel(settings.strategy),
);
const liveSignalCount = computed(() => livePayload.value?.signals.length ?? 0);
const liveCandleCount = computed(() => livePayload.value?.candles.length ?? 0);
const breadthGroups = computed(() => breadthPayload.value?.groups ?? []);
const breadthSeriesCount = computed(() =>
  Object.keys(breadthPayload.value?.series ?? {}).length,
);
const breadthUpdatedAt = computed(() =>
  breadthPayload.value?.updated_at
    ? new Date(breadthPayload.value.updated_at).toLocaleTimeString()
    : "—",
);
const breadthPutCall = computed(() => {
  const symbol = breadthPayload.value?.put_call_symbol;
  return symbol ? breadthPayload.value?.series[symbol] ?? null : null;
});
const comboSignals = computed(() => comboPayload.value?.signals ?? []);
const comboSignalCount = computed(() => comboPayload.value?.signals.length ?? 0);
const comboCandleCount = computed(() => comboPayload.value?.candles.length ?? 0);
const comboChartResetKey = computed(() =>
  [comboSymbol.value, comboInterval.value, comboLimit.value, settings.combo_strategies].join(":"),
);
const chartLabels = computed(() => ({
  aria: t("chart.aria"),
  empty: t("empty.noCandles"),
  longSignal: t("chart.longSignal"),
  shortSignal: t("chart.shortSignal"),
  paperEntry: t("chart.paperEntry"),
  paperExit: t("chart.paperExit"),
}));
const consensusSignals = computed(() =>
  groupSignalsByConsensus(livePayload.value?.signals ?? [], liveConsensusMinConfirmations.value),
);
const displayedSignals = computed(() => {
  const rawSignals = livePayload.value?.signals ?? [];
  if (settings.strategy !== "all" || liveSignalDisplayMode.value === "individual") {
    return rawSignals;
  }
  return consensusSignals.value;
});

watch(liveMarket, () => {
  liveSymbol.value = String(activeLiveSymbolOptions.value[0]?.value ?? "BTCUSDT");
});

watch([liveMarket, liveSymbol, liveInterval, liveLimit, () => settings.strategy], () => {
  if (activeMode.value === "live") {
    refreshLiveChart();
  }
});

watch(locale, () => {
  if (!statusType.value) {
    status.value = t("status.ready");
  }
  if (!liveStatusType.value) {
    liveStatus.value = t("status.ready");
  }
  if (!breadthStatusType.value) {
    breadthStatus.value = t("status.ready");
  }
  if (!comboStatusType.value) {
    comboStatus.value = t("status.ready");
  }
  if (!labStatusType.value) {
    labStatus.value = t("status.ready");
  }
  if (!authStatusType.value && authStatus.value) {
    authStatus.value = t("auth.ready");
  }
});

onMounted(async () => {
  window.addEventListener("popstate", handlePopState);
  await loadCurrentUser();
  if (authUser.value) {
    try {
      await bootstrapAuthenticatedApp();
    } catch (error) {
      authUser.value = null;
      authStatus.value = errorMessage(error);
      authStatusType.value = "error";
    }
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("popstate", handlePopState);
  stopLivePolling();
});

function handlePopState() {
  setMode(modeFromLocation(), false);
}

function modeFromLocation(): Mode {
  return routeModes[window.location.pathname] ?? "backtest";
}

function setMode(mode: Mode, updateUrl = true) {
  stopLivePolling();
  activeMode.value = mode;
  if (mode !== "live" && settings.strategy === "all") {
    settings.strategy = "ema-rsi";
  }
  if (updateUrl && window.location.pathname !== modeRoutes[mode]) {
    window.history.pushState({ mode }, "", modeRoutes[mode]);
  }
  if (mode === "live") {
    startLivePolling();
  }
  if (mode === "breadth") {
    void loadMarketBreadth();
  }
  if (mode === "runs") {
    void loadRuns();
  }
}

function setStatus(message: string, type: StatusType = "") {
  status.value = message;
  statusType.value = type;
}

function setLiveStatus(message: string, type: StatusType = "") {
  liveStatus.value = message;
  liveStatusType.value = type;
}

function setBreadthStatus(message: string, type: StatusType = "") {
  breadthStatus.value = message;
  breadthStatusType.value = type;
}

function setComboStatus(message: string, type: StatusType = "") {
  comboStatus.value = message;
  comboStatusType.value = type;
}

function setLabStatus(message: string, type: StatusType = "") {
  labStatus.value = message;
  labStatusType.value = type;
}

async function loadCurrentUser() {
  authChecked.value = false;
  try {
    const payload = await requestJson<AuthMePayload>("/api/auth/me");
    authUser.value = payload.user;
  } catch {
    authUser.value = null;
  } finally {
    authChecked.value = true;
  }
}

async function bootstrapAuthenticatedApp() {
  await Promise.all([loadStrategies(), loadRuns()]);
  setMode(modeFromLocation(), false);
}

async function submitAuth() {
  authStatus.value = "";
  authStatusType.value = "busy";
  const endpoint = authMode.value === "login" ? "/api/auth/login" : "/api/auth/register";
  try {
    const payload = await requestJson<AuthPayload>(endpoint, {
      method: "POST",
      body: JSON.stringify({
        username: authForm.username,
        password: authForm.password,
      }),
    });
    authUser.value = payload.user;
    authForm.password = "";
    authStatus.value = t("auth.ready");
    authStatusType.value = "";
    await bootstrapAuthenticatedApp();
  } catch (error) {
    authStatus.value = errorMessage(error);
    authStatusType.value = "error";
  }
}

async function logout() {
  await requestJson<{ ok: true }>("/api/auth/logout", { method: "POST" });
  authUser.value = null;
  stopLivePolling();
  symbols.value = [];
  runs.value = [];
  outputRuns.value = [];
  runDetails.value = null;
  livePayload.value = null;
  breadthPayload.value = null;
  comboPayload.value = null;
  labRows.value = [];
}

async function loadStrategies() {
  const payload = await requestJson<StrategyPayload>("/api/strategies");
  strategies.value = payload.strategies;
  presets.value = payload.presets;
}

async function loadSymbols() {
  setStatus(t("status.loadingSymbols"), "busy");
  symbols.value = [];
  try {
    const payload = await requestJson<{ ok: true; symbols: SymbolInfo[] }>(
      `/api/symbols?top=${encodeURIComponent(settings.top)}`,
    );
    symbols.value = payload.symbols;
    setStatus(`${t("status.loadedSymbols")} ${payload.symbols.length}`);
  } catch (error) {
    setStatus(errorMessage(error), "error");
  }
}

async function runCurrentMode() {
  const mode = activeMode.value;
  const endpoint = mode === "paper" ? "/api/paper" : "/api/backtest";
  const payload = { ...settings };
  if (mode === "paper") {
    payload.symbol = payload.symbols || "BTCUSDT";
    delete payload.symbols;
  }
  setStatus(mode === "paper" ? t("status.paperRunning") : t("status.backtestRunning"), "busy");
  outputRuns.value = [];
  try {
    const result = await requestJson<{ ok: true; runs: RunCard[] }>(endpoint, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    outputRuns.value = result.runs;
    await loadRuns();
    setStatus(t("status.ready"));
  } catch (error) {
    setStatus(errorMessage(error), "error");
  }
}

async function loadLiveChart() {
  setLiveStatus(t("status.loadingChart"), "busy");
  try {
      const query = toQuery({
        ...settings,
        market: liveMarket.value,
        symbol: liveSymbol.value,
        interval: liveInterval.value,
        limit: liveLimit.value,
    });
    livePayload.value = await requestJson<LiveChartPayload>(`/api/live-chart?${query}`);
    setLiveStatus(`${t("status.updated")} ${new Date().toLocaleTimeString()}`);
  } catch (error) {
    livePayload.value = null;
    setLiveStatus(errorMessage(error), "error");
  }
}

function startLivePolling() {
  void loadLiveChart();
  const seconds = Math.max(2, Number(liveRefresh.value || 10));
  liveTimer = window.setInterval(loadLiveChart, seconds * 1000);
}

function stopLivePolling() {
  if (liveTimer) {
    window.clearInterval(liveTimer);
    liveTimer = 0;
  }
}

function refreshLiveChart() {
  stopLivePolling();
  if (activeMode.value === "live") {
    startLivePolling();
    return;
  }
  void loadLiveChart();
}

async function loadMarketBreadth() {
  setBreadthStatus(t("status.loadingBreadth"), "busy");
  try {
    breadthPayload.value = await requestJson<MarketBreadthPayload>("/api/market-breadth");
    setBreadthStatus(`${t("status.updated")} ${breadthUpdatedAt.value}`);
  } catch (error) {
    breadthPayload.value = null;
    setBreadthStatus(errorMessage(error), "error");
  }
}

async function runCombinationSignals() {
  setComboStatus(t("status.comboRunning"), "busy");
  comboPayload.value = null;
  try {
    comboPayload.value = await requestJson<CombinationSignalsPayload>("/api/combination-signals", {
      method: "POST",
      body: JSON.stringify({
        ...settings,
        strategy: "combined-signals",
        symbol: comboSymbol.value,
        interval: comboInterval.value,
        limit: comboLimit.value,
      }),
    });
    setComboStatus(`${t("status.updatedSignals")} ${comboPayload.value.signals.length}`);
  } catch (error) {
    setComboStatus(errorMessage(error), "error");
  }
}

async function loadRuns() {
  try {
    const payload = await requestJson<{ ok: true; runs: RunCard[] }>("/api/runs");
    runs.value = payload.runs;
  } catch {
    runs.value = [];
  }
}

async function loadRunDetails(path: string) {
  runDetails.value = null;
  try {
    runDetails.value = await requestJson<RunDetails>(`/api/run?path=${encodeURIComponent(path)}`);
  } catch (error) {
    setStatus(errorMessage(error), "error");
  }
}

async function runStrategyLab() {
  setLabStatus(t("status.labRunning"), "busy");
  labRows.value = [];
  try {
    const payload = await requestJson<StrategyLabPayload>("/api/strategy-lab", {
      method: "POST",
      body: JSON.stringify({
        ...settings,
        symbols: labSymbols.value,
        strategies: labStrategies.value,
        presets: labPresets.value,
        benchmark_symbols: labBenchmarkSymbols.value,
      }),
    });
    labRows.value = payload.rows;
    setLabStatus(`${t("status.rankedResults")} ${payload.rows.length}`);
  } catch (error) {
    setLabStatus(errorMessage(error), "error");
  }
}

function exportLabCsv() {
  if (!labRows.value.length) {
    return;
  }
  const lines = [
    labCsvHeaders.join(","),
    ...labRows.value.map((row) =>
      labCsvHeaders.map((field) => csvCell(row[field])).join(","),
    ),
  ];
  const blob = new Blob([`${lines.join("\n")}\n`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "strategy-lab.csv";
  link.click();
  URL.revokeObjectURL(url);
}

function csvCell(value: unknown) {
  const text = String(value ?? "");
  if (/[",\n]/.test(text)) {
    return `"${text.replaceAll('"', '""')}"`;
  }
  return text;
}

function appendSymbol(symbol: string) {
  if (activeMode.value === "paper") {
    settings.symbols = symbol;
    return;
  }
  const values = settings.symbols
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  if (!values.includes(symbol)) {
    values.push(symbol);
  }
  settings.symbols = values.join(",");
}

function strategyLabel(name: string): string {
  const strategy = strategies.value.find((item) => item.name === name);
  return translateStrategyDescription(locale.value, name, strategy?.description ?? name);
}

function groupSignalsByConsensus(signals: Marker[], minimumConfirmations: number): Marker[] {
  const minimum = Math.max(1, Math.floor(Number(minimumConfirmations) || 1));
  const groups = new Map<string, Marker[]>();
  for (const signal of signals) {
    const key = `${signal.time}:${signal.type}`;
    groups.set(key, [...(groups.get(key) ?? []), signal]);
  }
  return [...groups.values()]
    .filter((group) => group.length >= minimum)
    .map((group) => consensusMarkerFromGroup(group))
    .sort((left, right) => Number(left.time) - Number(right.time));
}

function consensusMarkerFromGroup(group: Marker[]): Marker {
  const first = group[0];
  return {
    time: first.time,
    price: first.price,
    type: first.type,
    reason: formatConsensusReason(group),
  };
}

function formatConsensusReason(group: Marker[]): string {
  const strategyNames = distinctStrategyNames(group).join(", ");
  return strategyNames ? `${group.length}: ${strategyNames}` : String(group.length);
}

function distinctStrategyNames(group: Marker[]): string[] {
  return [
    ...new Set(
      group
        .map((marker) => {
          const separator = marker.reason.indexOf(":");
          return separator > 0 ? marker.reason.slice(0, separator) : "";
        })
        .filter(Boolean),
    ),
  ];
}

function formatNumber(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "0";
  }
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return String(value);
  }
  return number.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function latestBreadthCandle(symbol: string): MarketBreadthBar | null {
  const candles = breadthPayload.value?.series[symbol]?.candles ?? [];
  return candles.length ? candles[candles.length - 1] : null;
}

function latestBreadthClose(symbol: string): string {
  const candle = latestBreadthCandle(symbol);
  return candle ? formatNumber(candle.close) : "—";
}

function latestBreadthDate(symbol: string): string {
  return latestBreadthCandle(symbol)?.date ?? "—";
}

function breadthToneClass(symbol: string): string {
  const candle = latestBreadthCandle(symbol);
  if (!candle) {
    return "";
  }
  return candle.close >= 50 ? "is-positive" : "is-negative";
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
</script>

<template>
  <section v-if="!authChecked" class="auth-shell">
    <div class="auth-card">
      <div>
        <h1>{{ t("auth.title") }}</h1>
        <p>{{ t("auth.loading") }}</p>
      </div>
      <div class="status is-busy">{{ t("auth.loading") }}</div>
    </div>
  </section>

  <section v-else-if="!authUser" class="auth-shell">
    <form class="auth-card" @submit.prevent="submitAuth">
      <div class="auth-card-heading">
        <div>
          <h1>{{ t("auth.title") }}</h1>
          <p>{{ t("auth.subtitle") }}</p>
        </div>
        <div class="language-switcher" :aria-label="t('aria.language')">
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
      </div>
      <div class="auth-tabs">
        <button
          type="button"
          :class="{ 'is-active': authMode === 'login' }"
          @click="authMode = 'login'"
        >
          {{ t("auth.login") }}
        </button>
        <button
          type="button"
          :class="{ 'is-active': authMode === 'register' }"
          @click="authMode = 'register'"
        >
          {{ t("auth.register") }}
        </button>
      </div>
      <label>
        <span>{{ t("auth.username") }}</span>
        <input v-model.trim="authForm.username" autocomplete="username" required minlength="3">
      </label>
      <label>
        <span>{{ t("auth.password") }}</span>
        <input
          v-model="authForm.password"
          autocomplete="current-password"
          required
          minlength="8"
          type="password"
        >
      </label>
      <button class="primary" type="submit">
        {{ authMode === "login" ? t("auth.submitLogin") : t("auth.submitRegister") }}
      </button>
      <button
        class="auth-link"
        type="button"
        @click="authMode = authMode === 'login' ? 'register' : 'login'"
      >
        {{ authMode === "login" ? t("auth.switchToRegister") : t("auth.switchToLogin") }}
      </button>
      <div v-if="authStatus" class="status auth-status" :class="authStatusType ? `is-${authStatusType}` : ''">
        {{ authStatus }}
      </div>
    </form>
  </section>

  <template v-else>
  <header class="topbar">
    <div>
      <h1>{{ t("app.title") }}</h1>
      <p>{{ t("app.subtitle") }}</p>
    </div>
    <div class="topbar-actions">
      <div class="language-switcher" :aria-label="t('aria.language')">
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
      <button class="secondary logout-button" type="button" @click="logout">
        {{ t("auth.logout") }}
      </button>
      <div class="safety">{{ t("app.safety") }}</div>
    </div>
  </header>

  <nav class="tabs" :aria-label="t('aria.modes')">
    <button
      v-for="tab in tabs"
      :key="tab.mode"
      type="button"
      class="tab"
      :class="{ 'is-active': activeMode === tab.mode }"
      @click="setMode(tab.mode)"
    >
      {{ tab.label }}
    </button>
  </nav>

  <main>
    <section v-if="activeMode === 'backtest' || activeMode === 'paper'" class="workspace">
      <form class="panel settings" @submit.prevent="runCurrentMode">
        <div class="panel-heading">
          <div>
            <h2>{{ activeMode === "paper" ? t("pages.paperTrading") : t("pages.backtest") }}</h2>
            <p>{{ strategyName }}</p>
          </div>
          <button class="primary" type="submit">
            {{ activeMode === "paper" ? t("actions.runPaper") : t("actions.runBacktest") }}
          </button>
        </div>

        <div class="symbols-row">
          <label>
            <span>{{ activeMode === "paper" ? t("labels.symbol") : t("labels.symbols") }}</span>
            <input v-model="settings.symbols" autocomplete="off">
          </label>
          <label class="small-field">
            <span>{{ t("labels.top") }}</span>
            <input v-model="settings.top" type="number" min="1" max="25">
          </label>
          <button class="secondary" type="button" @click="loadSymbols">{{ t("actions.loadTop") }}</button>
        </div>

        <div class="symbol-list">
          <button
            v-for="symbol in symbols"
            :key="symbol.symbol"
            class="symbol-chip"
            type="button"
            @click="appendSymbol(symbol.symbol)"
          >
            {{ symbol.symbol }}
          </button>
        </div>

        <div class="field-grid">
          <label>
            <span>{{ t("labels.interval") }}</span>
            <input v-model="settings.interval" autocomplete="off">
          </label>
          <label>
            <span>{{ t("labels.candles") }}</span>
            <input v-model="settings.limit" type="number" min="1">
          </label>
          <label>
            <span>{{ t("labels.side") }}</span>
            <select v-model="settings.allowed_side">
              <option v-for="option in sideOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>
          <label>
            <span>{{ t("labels.strategy") }}</span>
            <select v-model="settings.strategy">
              <option v-for="strategy in strategies" :key="strategy.name" :value="strategy.name">
                {{ strategy.name }}
              </option>
            </select>
          </label>
          <label>
            <span>{{ t("labels.preset") }}</span>
            <select v-model="settings.preset">
              <option v-for="preset in presets" :key="preset" :value="preset">{{ preset }}</option>
            </select>
          </label>
          <label><span>{{ t("labels.startingUsdt") }}</span><input v-model="settings.starting_balance" type="number" min="1" step="0.01"></label>
          <label><span>{{ t("labels.positionFraction") }}</span><input v-model="settings.position_fraction" type="number" min="0.01" max="1" step="0.01"></label>
          <label><span>{{ t("labels.feeRate") }}</span><input v-model="settings.fee_rate" type="number" min="0" step="0.0001"></label>
          <label><span>{{ t("labels.slippage") }}</span><input v-model="settings.slippage_rate" type="number" min="0" step="0.0001"></label>
          <label><span>{{ t("labels.fastEma") }}</span><input v-model="settings.fast_ema" type="number" min="1"></label>
          <label><span>{{ t("labels.slowEma") }}</span><input v-model="settings.slow_ema" type="number" min="1"></label>
          <label><span>{{ t("labels.rsiPeriod") }}</span><input v-model="settings.rsi_period" type="number" min="1"></label>
          <label><span>{{ t("labels.rsiOverbought") }}</span><input v-model="settings.rsi_overbought" type="number" min="1" max="100" step="0.1"></label>
          <label><span>{{ t("labels.rsiOversold") }}</span><input v-model="settings.rsi_oversold" type="number" min="0" max="99" step="0.1"></label>
          <label><span>{{ t("labels.rsiMidline") }}</span><input v-model="settings.rsi_midline" type="number" min="0" max="100" step="0.1"></label>
          <label><span>{{ t("labels.macdSignal") }}</span><input v-model="settings.macd_signal" type="number" min="1"></label>
          <label><span>{{ t("labels.bollingerPeriod") }}</span><input v-model="settings.bollinger_period" type="number" min="1"></label>
          <label><span>{{ t("labels.bollingerStddev") }}</span><input v-model="settings.bollinger_stddev" type="number" min="0.1" step="0.1"></label>
          <label><span>{{ t("labels.donchianPeriod") }}</span><input v-model="settings.donchian_period" type="number" min="1"></label>
          <label><span>{{ t("labels.atrPeriod") }}</span><input v-model="settings.atr_period" type="number" min="1"></label>
          <label><span>{{ t("labels.supertrendMultiplier") }}</span><input v-model="settings.supertrend_multiplier" type="number" min="0.1" step="0.1"></label>
          <label><span>{{ t("labels.vwapPeriod") }}</span><input v-model="settings.vwap_period" type="number" min="1"></label>
          <label><span>{{ t("labels.vwapThreshold") }}</span><input v-model="settings.vwap_threshold_pct" type="number" min="0" step="0.001"></label>
          <label><span>{{ t("labels.stochRsiPeriod") }}</span><input v-model="settings.stoch_rsi_period" type="number" min="1"></label>
          <label><span>{{ t("labels.emaRibbonFast") }}</span><input v-model="settings.ema_ribbon_fast" type="number" min="1"></label>
          <label><span>{{ t("labels.emaRibbonMid") }}</span><input v-model="settings.ema_ribbon_mid" type="number" min="1"></label>
          <label><span>{{ t("labels.emaRibbonSlow") }}</span><input v-model="settings.ema_ribbon_slow" type="number" min="1"></label>
          <label><span>{{ t("labels.momentumPeriod") }}</span><input v-model="settings.momentum_period" type="number" min="1"></label>
          <label><span>{{ t("labels.keltnerMultiplier") }}</span><input v-model="settings.keltner_multiplier" type="number" min="0.1" step="0.1"></label>
          <label><span>{{ t("labels.cciPeriod") }}</span><input v-model="settings.cci_period" type="number" min="1"></label>
          <label><span>{{ t("labels.cciOversold") }}</span><input v-model="settings.cci_oversold" type="number" step="1"></label>
          <label><span>{{ t("labels.cciOverbought") }}</span><input v-model="settings.cci_overbought" type="number" step="1"></label>
          <label><span>{{ t("labels.williamsPeriod") }}</span><input v-model="settings.williams_period" type="number" min="1"></label>
          <label><span>{{ t("labels.williamsOversold") }}</span><input v-model="settings.williams_oversold" type="number" min="-100" max="0" step="1"></label>
          <label><span>{{ t("labels.williamsOverbought") }}</span><input v-model="settings.williams_overbought" type="number" min="-100" max="0" step="1"></label>
          <label><span>{{ t("labels.volumePeriod") }}</span><input v-model="settings.volume_period" type="number" min="1"></label>
          <label><span>{{ t("labels.volumeMultiplier") }}</span><input v-model="settings.volume_multiplier" type="number" min="0.1" step="0.1"></label>
          <label><span>{{ t("labels.squeezeThreshold") }}</span><input v-model="settings.squeeze_threshold_pct" type="number" min="0" step="0.001"></label>
          <label><span>{{ t("labels.stopLoss") }}</span><input v-model="settings.stop_loss_pct" type="number" min="0" step="0.001"></label>
          <label><span>{{ t("labels.takeProfit") }}</span><input v-model="settings.take_profit_pct" type="number" min="0" step="0.001"></label>
          <label><span>{{ t("labels.trailingStop") }}</span><input v-model="settings.trailing_stop_pct" type="number" min="0" step="0.001"></label>
          <label v-if="activeMode === 'backtest'"><span>{{ t("labels.retries") }}</span><input v-model="settings.market_data_retries" type="number" min="0"></label>
          <label v-if="activeMode === 'backtest'"><span>{{ t("labels.retryDelay") }}</span><input v-model="settings.retry_delay" type="number" min="0" step="0.1"></label>
          <label v-if="activeMode === 'paper'"><span>{{ t("labels.iterations") }}</span><input v-model="settings.iterations" type="number" min="1"></label>
          <label v-if="activeMode === 'paper'"><span>{{ t("labels.pollSeconds") }}</span><input v-model="settings.poll_seconds" type="number" min="0" step="0.5"></label>
        </div>
      </form>

      <section class="panel output">
        <div class="panel-heading">
          <h2>{{ t("pages.output") }}</h2>
          <div class="status" :class="statusType ? `is-${statusType}` : ''">{{ status }}</div>
        </div>
        <div v-if="!outputRuns.length" class="empty">{{ t("empty.noRunOutput") }}</div>
        <article v-for="run in outputRuns" :key="run.path" class="detail-section">
          <h3>{{ run.symbol || t("fallback.run") }}</h3>
          <div class="metric-row">
            <div class="metric"><b>{{ t("metrics.final") }}</b><span>{{ formatNumber(run.summary.final_balance) }}</span></div>
            <div class="metric"><b>{{ t("metrics.trades") }}</b><span>{{ formatNumber(run.summary.trades) }}</span></div>
            <div class="metric"><b>{{ t("metrics.return") }}</b><span>{{ formatNumber(run.summary.total_return_pct) }}</span></div>
            <div class="metric"><b>{{ t("metrics.winRate") }}</b><span>{{ formatNumber(run.summary.win_rate) }}</span></div>
          </div>
          <p>{{ run.path }}</p>
        </article>
      </section>
    </section>

    <section v-else-if="activeMode === 'live'" class="panel live-panel">
      <div class="panel-heading">
        <div>
          <h2>{{ t("pages.liveMarket") }}</h2>
          <p>{{ activeLiveStrategyLabel }}</p>
        </div>
        <div class="status" :class="liveStatusType ? `is-${liveStatusType}` : ''">{{ liveStatus }}</div>
      </div>
      <div class="live-market-strip">
        <div class="ticker-pill">
          <span>{{ t("labels.source") }}</span>
          <b>{{ livePayload?.data_source ?? "Binance Spot public REST" }}</b>
        </div>
        <div class="ticker-pill">
          <span>{{ t("labels.market") }}</span>
          <b>{{ livePayload?.symbol ?? liveSymbol }}</b>
        </div>
        <div class="ticker-pill">
          <span>{{ t("labels.interval") }}</span>
          <b>{{ livePayload?.interval ?? liveInterval }}</b>
        </div>
        <div class="ticker-pill">
          <span>{{ t("labels.candles") }}</span>
          <b>{{ formatNumber(liveCandleCount) }}</b>
        </div>
        <div class="ticker-pill">
          <span>{{ t("labels.signals") }}</span>
          <b>{{ formatNumber(liveSignalCount) }}</b>
        </div>
      </div>
      <div class="live-controls">
        <label>
          <span>{{ t("labels.market") }}</span>
          <select v-model="liveMarket">
            <option
              v-for="option in liveMarketOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
        </label>
        <label>
          <span>{{ t("labels.symbol") }}</span>
          <select v-model="liveSymbol">
            <option
              v-for="option in activeLiveSymbolOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
        </label>
        <label>
          <span>{{ t("labels.interval") }}</span>
          <select v-model="liveInterval">
            <option
              v-for="option in liveIntervalOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
        </label>
        <label>
          <span>{{ t("labels.candles") }}</span>
          <select v-model="liveLimit">
            <option
              v-for="option in liveCandleOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
        </label>
        <label class="live-strategy-field">
          <span>{{ t("labels.strategy") }}</span>
          <select v-model="settings.strategy">
            <option v-for="strategy in liveStrategyOptions" :key="strategy.name" :value="strategy.name">
              {{ strategy.description }}
            </option>
          </select>
        </label>
        <label v-if="settings.strategy === 'all'">
          <span>{{ t("labels.signalView") }}</span>
          <select v-model="liveSignalDisplayMode">
            <option
              v-for="option in liveSignalDisplayOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
        </label>
        <label v-if="settings.strategy === 'all' && liveSignalDisplayMode === 'consensus'">
          <span>{{ t("labels.minConfirmations") }}</span>
          <input v-model.number="liveConsensusMinConfirmations" type="number" min="1" max="20">
        </label>
        <label><span>{{ t("labels.refreshSec") }}</span><input v-model="liveRefresh" type="number" min="2" max="300"></label>
        <label class="toggle-row"><input v-model="showSignals" type="checkbox"><span>{{ t("labels.strategyMarkers") }}</span></label>
        <button class="primary" type="button" @click="refreshLiveChart">{{ t("actions.refreshChart") }}</button>
      </div>
      <div class="chart-shell">
        <div class="chart-legend">
          <span><i class="legend-dot long"></i>{{ t("chart.longLegend") }}</span>
          <span><i class="legend-dot short"></i>{{ t("chart.shortLegend") }}</span>
          <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">{{ t("chart.tradingView") }}</a>
        </div>
        <TradingViewChart
          v-if="livePayload"
          :candles="livePayload.candles"
          :signals="displayedSignals"
          :paper-markers="[]"
          :show-signals="showSignals"
          :show-paper="false"
          :reset-key="liveChartResetKey"
          :aria-label="chartLabels.aria"
          :empty-label="chartLabels.empty"
          :long-signal-label="chartLabels.longSignal"
          :short-signal-label="chartLabels.shortSignal"
        />
        <div v-else class="empty">{{ t("empty.loadChart") }}</div>
      </div>
    </section>

    <section v-else-if='activeMode === "breadth"' class="panel breadth-panel">
      <div class="panel-heading">
        <div>
          <h2>{{ t("pages.marketBreadth") }}</h2>
          <p>{{ t("pages.marketBreadthSubtitle") }}</p>
        </div>
        <div class="actions">
          <button class="primary" type="button" @click="loadMarketBreadth">
            {{ t("actions.refresh") }}
          </button>
          <div class="status" :class="breadthStatusType ? `is-${breadthStatusType}` : ''">
            {{ breadthStatus }}
          </div>
        </div>
      </div>
      <div class="breadth-summary">
        <div class="ticker-pill">
          <span>{{ t("labels.source") }}</span>
          <b>{{ breadthPayload?.source ?? "Barchart" }}</b>
        </div>
        <div class="ticker-pill">
          <span>{{ t("labels.series") }}</span>
          <b>{{ formatNumber(breadthSeriesCount) }}</b>
        </div>
        <div class="ticker-pill">
          <span>{{ t("labels.updated") }}</span>
          <b>{{ breadthUpdatedAt }}</b>
        </div>
        <div class="ticker-pill">
          <span>{{ t("labels.latest") }}</span>
          <b>{{ breadthPutCall ? latestBreadthClose(breadthPutCall.symbol) : "—" }}</b>
        </div>
      </div>
      <div v-if="!breadthPayload" class="empty breadth-empty">{{ t("empty.loadBreadth") }}</div>
      <template v-else>
        <div class="breadth-grid">
          <section v-for="group in breadthGroups" :key="group.name" class="breadth-group">
            <div class="breadth-group-heading">
              <h3>{{ group.name }}</h3>
              <span>% above moving average</span>
            </div>
            <article
              v-for="item in group.items"
              :key="item.symbol"
              class="breadth-card"
              :class="breadthToneClass(item.symbol)"
            >
              <div class="breadth-card-heading">
                <div>
                  <h4>{{ item.period }}</h4>
                  <p>{{ item.symbol }}</p>
                </div>
                <div class="breadth-latest">
                  <b>{{ latestBreadthClose(item.symbol) }}</b>
                  <span>{{ latestBreadthDate(item.symbol) }}</span>
                </div>
              </div>
              <TradingViewChart
                v-if="breadthPayload?.series[item.symbol]"
                :candles="breadthPayload.series[item.symbol].candles"
                :signals="[]"
                :paper-markers="[]"
                :show-signals="false"
                :show-paper="false"
                :reset-key="`breadth:${item.symbol}`"
                :aria-label="`${chartLabels.aria} ${item.symbol}`"
                :empty-label="chartLabels.empty"
                :paper-entry-label="chartLabels.paperEntry"
                :paper-exit-label="chartLabels.paperExit"
                :long-signal-label="chartLabels.longSignal"
                :short-signal-label="chartLabels.shortSignal"
              />
            </article>
          </section>
        </div>
        <section v-if="breadthPutCall" class="breadth-put-call">
          <div class="breadth-group-heading">
            <h3>{{ t("pages.putCallRatio") }}</h3>
            <span>{{ breadthPutCall.symbol }} · {{ breadthPutCall.period }}</span>
          </div>
          <TradingViewChart
            :candles="breadthPutCall.candles"
            :signals="[]"
            :paper-markers="[]"
            :show-signals="false"
            :show-paper="false"
            :reset-key="`breadth:${breadthPutCall.symbol}`"
            :aria-label="`${chartLabels.aria} ${breadthPutCall.symbol}`"
            :empty-label="chartLabels.empty"
            :paper-entry-label="chartLabels.paperEntry"
            :paper-exit-label="chartLabels.paperExit"
            :long-signal-label="chartLabels.longSignal"
            :short-signal-label="chartLabels.shortSignal"
          />
        </section>
      </template>
    </section>

    <section v-else-if="activeMode === 'combos'" class="workspace combo-layout">
      <form class="panel settings" @submit.prevent="runCombinationSignals">
        <div class="panel-heading">
          <div>
            <h2>{{ t("pages.combinationSignals") }}</h2>
            <p>{{ settings.combo_strategies }}</p>
          </div>
          <button class="primary" type="submit">{{ t("actions.runCombo") }}</button>
        </div>
        <div class="field-grid">
          <label><span>{{ t("labels.symbol") }}</span><input v-model="comboSymbol" autocomplete="off"></label>
          <label><span>{{ t("labels.interval") }}</span><input v-model="comboInterval" autocomplete="off"></label>
          <label><span>{{ t("labels.candles") }}</span><input v-model="comboLimit" type="number" min="30"></label>
          <label><span>{{ t("labels.side") }}</span>
            <select v-model="settings.allowed_side">
              <option v-for="option in sideOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>
          <label><span>{{ t("labels.memberStrategies") }}</span><input v-model="settings.combo_strategies" autocomplete="off"></label>
          <label><span>{{ t("labels.entryConfirms") }}</span><input v-model="settings.combo_entry_confirmations" type="number" min="1"></label>
          <label><span>{{ t("labels.exitConfirms") }}</span><input v-model="settings.combo_exit_confirmations" type="number" min="1"></label>
          <label><span>{{ t("labels.lookback") }}</span><input v-model="settings.combo_lookback" type="number" min="1"></label>
          <label>
            <span>{{ t("labels.preset") }}</span>
            <select v-model="settings.preset">
              <option v-for="preset in presets" :key="preset" :value="preset">{{ preset }}</option>
            </select>
          </label>
          <label><span>{{ t("labels.startingUsdt") }}</span><input v-model="settings.starting_balance" type="number" min="1" step="0.01"></label>
          <label><span>{{ t("labels.positionFraction") }}</span><input v-model="settings.position_fraction" type="number" min="0.01" max="1" step="0.01"></label>
          <label><span>{{ t("labels.fastPeriod") }}</span><input v-model="settings.fast_ema" type="number" min="1"></label>
          <label><span>{{ t("labels.slowPeriod") }}</span><input v-model="settings.slow_ema" type="number" min="1"></label>
          <label><span>{{ t("labels.rsiPeriod") }}</span><input v-model="settings.rsi_period" type="number" min="1"></label>
          <label><span>{{ t("labels.rsiOverbought") }}</span><input v-model="settings.rsi_overbought" type="number" min="1" max="100" step="0.1"></label>
          <label><span>{{ t("labels.rsiOversold") }}</span><input v-model="settings.rsi_oversold" type="number" min="0" max="99" step="0.1"></label>
          <label><span>{{ t("labels.macdSignal") }}</span><input v-model="settings.macd_signal" type="number" min="1"></label>
          <label><span>{{ t("labels.feeRate") }}</span><input v-model="settings.fee_rate" type="number" min="0" step="0.0001"></label>
          <label><span>{{ t("labels.slippage") }}</span><input v-model="settings.slippage_rate" type="number" min="0" step="0.0001"></label>
          <label><span>{{ t("labels.stopLoss") }}</span><input v-model="settings.stop_loss_pct" type="number" min="0" step="0.001"></label>
          <label><span>{{ t("labels.takeProfit") }}</span><input v-model="settings.take_profit_pct" type="number" min="0" step="0.001"></label>
          <label><span>{{ t("labels.trailingStop") }}</span><input v-model="settings.trailing_stop_pct" type="number" min="0" step="0.001"></label>
        </div>
      </form>
      <section class="panel output">
        <div class="panel-heading">
          <h2>{{ t("pages.comboResult") }}</h2>
          <div class="status" :class="comboStatusType ? `is-${comboStatusType}` : ''">{{ comboStatus }}</div>
        </div>
        <div v-if="comboPayload" class="metric-row">
          <div class="metric"><b>{{ t("metrics.final") }}</b><span>{{ formatNumber(comboPayload.summary.final_balance) }}</span></div>
          <div class="metric"><b>{{ t("metrics.return") }}</b><span>{{ formatNumber(comboPayload.summary.total_return_pct) }}</span></div>
          <div class="metric"><b>{{ t("metrics.trades") }}</b><span>{{ formatNumber(comboPayload.summary.trades) }}</span></div>
          <div class="metric"><b>{{ t("labels.signals") }}</b><span>{{ formatNumber(comboSignalCount) }}</span></div>
          <div class="metric"><b>{{ t("labels.candles") }}</b><span>{{ formatNumber(comboCandleCount) }}</span></div>
        </div>
        <div class="chart-shell">
          <div class="chart-legend">
            <span><i class="legend-dot long"></i>{{ t("chart.longLegend") }}</span>
            <span><i class="legend-dot short"></i>{{ t("chart.shortLegend") }}</span>
            <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">{{ t("chart.tradingView") }}</a>
          </div>
          <TradingViewChart
            v-if="comboPayload"
            :candles="comboPayload.candles"
            :signals="comboSignals"
            :paper-markers="[]"
            :show-signals="true"
            :show-paper="false"
            :reset-key="comboChartResetKey"
            :aria-label="chartLabels.aria"
            :empty-label="chartLabels.empty"
            :paper-entry-label="chartLabels.paperEntry"
            :paper-exit-label="chartLabels.paperExit"
            :long-signal-label="chartLabels.longSignal"
            :short-signal-label="chartLabels.shortSignal"
          />
          <div v-else class="empty">{{ t("empty.runCombo") }}</div>
        </div>
      </section>
    </section>

    <section v-else-if="activeMode === 'runs'" class="panel runs-panel">
      <div class="panel-heading">
        <h2>{{ t("pages.runs") }}</h2>
        <button class="secondary" type="button" @click="loadRuns">{{ t("actions.refresh") }}</button>
      </div>
      <div class="runs-layout">
        <div class="runs-list">
          <div v-if="!runs.length" class="empty">{{ t("empty.noRuns") }}</div>
          <div v-for="run in runs" :key="run.path" class="run-row">
            <div>
              <h3>{{ run.symbol || t("fallback.run") }} · {{ run.mode }}</h3>
              <p>{{ run.timestamp }} · {{ t("metrics.final") }} {{ formatNumber(run.final_balance) }}</p>
            </div>
            <button class="secondary" type="button" @click="loadRunDetails(run.path)">{{ t("actions.open") }}</button>
          </div>
        </div>
        <div class="run-detail">
          <div v-if="!runDetails" class="empty">{{ t("empty.selectRun") }}</div>
          <template v-else>
            <div class="detail-section">
              <h3>{{ runDetails.summary.symbol || runDetails.path }}</h3>
              <div class="metric-row">
                <div class="metric"><b>{{ t("metrics.final") }}</b><span>{{ formatNumber(runDetails.summary.final_balance) }}</span></div>
                <div class="metric"><b>{{ t("metrics.trades") }}</b><span>{{ formatNumber(runDetails.summary.trades) }}</span></div>
                <div class="metric"><b>{{ t("metrics.maxDd") }}</b><span>{{ formatNumber(runDetails.summary.max_drawdown_pct) }}</span></div>
                <div class="metric"><b>{{ t("metrics.profitFactor") }}</b><span>{{ formatNumber(runDetails.summary.profit_factor) }}</span></div>
              </div>
            </div>
            <div class="detail-section">
              <h3>{{ t("pages.recentTrades") }}</h3>
              <table>
                <thead>
                  <tr>
                    <th>{{ t("table.side") }}</th>
                    <th>{{ t("table.entry") }}</th>
                    <th>{{ t("table.exit") }}</th>
                    <th>{{ t("table.pnl") }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="trade in runDetails.trades" :key="`${trade.entry_time}-${trade.exit_time}-${trade.side}`">
                    <td>{{ trade.side }}</td>
                    <td>{{ trade.entry_price }}</td>
                    <td>{{ trade.exit_price }}</td>
                    <td>{{ trade.realized_pnl }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </div>
      </div>
    </section>

    <section v-else class="workspace lab-layout">
      <form class="panel settings" @submit.prevent="runStrategyLab">
        <div class="panel-heading">
          <div>
            <h2>{{ t("pages.strategyLab") }}</h2>
            <p>{{ t("pages.strategyLabSubtitle") }}</p>
          </div>
          <button class="primary" type="submit">{{ t("actions.runLab") }}</button>
        </div>
        <div class="field-grid">
          <label><span>{{ t("labels.symbols") }}</span><input v-model="labSymbols" autocomplete="off"></label>
          <label><span>{{ t("labels.strategies") }}</span><input v-model="labStrategies" autocomplete="off"></label>
          <label><span>{{ t("labels.presets") }}</span><input v-model="labPresets" autocomplete="off"></label>
          <label><span>{{ t("labels.benchmarks") }}</span><input v-model="labBenchmarkSymbols" autocomplete="off"></label>
          <label><span>{{ t("labels.walkWindows") }}</span><input v-model="settings.walk_forward_windows" type="number" min="0"></label>
          <label><span>{{ t("labels.walkMinCandles") }}</span><input v-model="settings.walk_forward_min_candles" type="number" min="1"></label>
          <label><span>{{ t("labels.interval") }}</span><input v-model="settings.interval" autocomplete="off"></label>
          <label><span>{{ t("labels.candles") }}</span><input v-model="settings.limit" type="number" min="30"></label>
          <label><span>{{ t("labels.side") }}</span>
            <select v-model="settings.allowed_side">
              <option v-for="option in sideOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>
        </div>
      </form>
      <section class="panel output">
        <div class="panel-heading">
          <h2>{{ t("pages.ranking") }}</h2>
          <div class="actions">
            <button type="button" :disabled="!labRows.length" @click="exportLabCsv">{{ t("actions.exportCsv") }}</button>
            <div class="status" :class="labStatusType ? `is-${labStatusType}` : ''">{{ labStatus }}</div>
          </div>
        </div>
        <div v-if="!labRows.length" class="empty">{{ t("empty.runLab") }}</div>
        <table v-else>
          <thead>
            <tr>
              <th>{{ t("table.rank") }}</th>
              <th>{{ t("table.symbol") }}</th>
              <th>{{ t("table.strategy") }}</th>
              <th>{{ t("table.preset") }}</th>
              <th>{{ t("table.return") }}</th>
              <th>{{ t("table.maxDd") }}</th>
              <th>{{ t("table.trades") }}</th>
              <th>{{ t("table.pf") }}</th>
              <th>{{ t("table.sharpe") }}</th>
              <th>{{ t("table.sortino") }}</th>
              <th>{{ t("table.exposure") }}</th>
              <th>{{ t("table.worst") }}</th>
              <th>{{ t("table.wfAvg") }}</th>
              <th>{{ t("table.wfWin") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in labRows" :key="`${row.rank}-${row.symbol}-${row.strategy}-${row.preset}`">
              <td>{{ row.rank }}</td>
              <td>{{ row.symbol }}</td>
              <td>{{ row.strategy }}</td>
              <td>{{ row.preset }}</td>
              <td>{{ formatNumber(row.total_return_pct) }}</td>
              <td>{{ formatNumber(row.max_drawdown_pct) }}</td>
              <td>{{ row.trades }}</td>
              <td>{{ formatNumber(row.profit_factor) }}</td>
              <td>{{ formatNumber(row.sharpe_ratio) }}</td>
              <td>{{ formatNumber(row.sortino_ratio) }}</td>
              <td>{{ formatNumber(row.exposure_pct) }}</td>
              <td>{{ formatNumber(row.worst_trade) }}</td>
              <td>{{ formatNumber(row.walk_forward_avg_return_pct) }}</td>
              <td>{{ formatNumber(row.walk_forward_profitable_pct) }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </section>
  </main>
  </template>
</template>
