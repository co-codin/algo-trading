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
  AdminUsersPayload,
  AuthMePayload,
  AuthPayload,
  AuthUser,
  LiveChartPayload,
  MarketBreadthBar,
  MarketBreadthPayload,
  Mode,
  Marker,
  StrategyInfo,
  StrategyLabPayload,
  StrategyLabRow,
  StrategyPayload,
} from "./types";

type StatusType = "" | "busy" | "error";
type SelectOption = {
  label: string;
  value: string | number;
};
type SignalDisplayMode = "consensus" | "individual";

const routeModes: Record<string, Mode> = {
  "/": "lab",
  "/live": "live",
  "/chart": "live",
  "/breadth": "breadth",
  "/lab": "lab",
  "/profile": "profile",
  "/admin": "admin",
};

const modeRoutes: Record<Mode, string> = {
  live: "/live",
  breadth: "/breadth",
  lab: "/lab",
  profile: "/profile",
  admin: "/admin",
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
  stop_loss_pct: "0.03",
  take_profit_pct: "0.06",
  trailing_stop_pct: "0",
  walk_forward_windows: "3",
  walk_forward_min_candles: "30",
});

const locale = ref<Locale>(normalizeLocale(window.localStorage.getItem(LOCALE_STORAGE_KEY)));
const authChecked = ref(false);
const authUser = ref<AuthUser | null>(null);
const authMode = ref<"login" | "register">("login");
const authForm = reactive({
  username: "",
  password: "",
});
const profileForm = reactive({
  first_name: "",
  last_name: "",
  middle_name: "",
});
const authStatus = ref("");
const authStatusType = ref<StatusType>("");
const profileStatus = ref(t("status.ready"));
const profileStatusType = ref<StatusType>("");
const adminUsers = ref<AuthUser[]>([]);
const adminSearch = ref("");
const adminStatus = ref(t("status.ready"));
const adminStatusType = ref<StatusType>("");

function t(key: MessageKey): string {
  return translate(locale.value, key);
}

function setLocale(nextLocale: Locale) {
  locale.value = nextLocale;
  localStorage.setItem(LOCALE_STORAGE_KEY, nextLocale);
}

const activeMode = ref<Mode>(modeFromLocation());
const strategies = ref<StrategyInfo[]>([]);
const livePayload = ref<LiveChartPayload | null>(null);
const breadthPayload = ref<MarketBreadthPayload | null>(null);
const labRows = ref<StrategyLabRow[]>([]);
const liveStatus = ref(t("status.ready"));
const liveStatusType = ref<StatusType>("");
const breadthStatus = ref(t("status.ready"));
const breadthStatusType = ref<StatusType>("");
const labStatus = ref(t("status.ready"));
const labStatusType = ref<StatusType>("");
const liveMarket = ref("crypto_spot");
const liveSymbol = ref("BTCUSDT");
const liveInterval = ref("5m");
const liveLimit = ref<string | number>(180);
const liveRefresh = ref("10");
const liveSignalDisplayMode = ref<SignalDisplayMode>("consensus");
const liveConsensusMinConfirmations = ref(2);
const showSignals = ref(true);
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

const canUseFeatures = computed(() => Boolean(authUser.value?.is_active));
const isAdminUser = computed(() =>
  authUser.value?.username === "cuiyeqing960904@gmail.com",
);
const featureTabs = computed(() => [
  { mode: "lab" as const, label: t("tabs.lab") },
  { mode: "live" as const, label: t("tabs.live") },
  { mode: "breadth" as const, label: t("tabs.breadth") },
]);
const accountTabs = computed(() => [
  { mode: "profile" as const, label: t("tabs.profile") },
  ...(isAdminUser.value ? [{ mode: "admin" as const, label: t("tabs.admin") }] : []),
]);
const tabs = computed(() => [
  ...(canUseFeatures.value ? featureTabs.value : []),
  ...accountTabs.value,
]);
const filteredAdminUsers = computed(() => {
  const query = adminSearch.value.trim().toLowerCase();
  if (!query) {
    return adminUsers.value;
  }
  return adminUsers.value.filter((user) => user.username.toLowerCase().includes(query));
});
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
  if (!liveStatusType.value) {
    liveStatus.value = t("status.ready");
  }
  if (!breadthStatusType.value) {
    breadthStatus.value = t("status.ready");
  }
  if (!labStatusType.value) {
    labStatus.value = t("status.ready");
  }
  if (!adminStatusType.value) {
    adminStatus.value = t("status.ready");
  }
  if (!profileStatusType.value) {
    profileStatus.value = t("status.ready");
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
  return routeModes[window.location.pathname] ?? "lab";
}

function isFeatureMode(mode: Mode): boolean {
  return mode === "lab" || mode === "live" || mode === "breadth";
}

function permittedMode(mode: Mode): Mode {
  if (mode === "admin" && !isAdminUser.value) {
    return "profile";
  }
  if (isFeatureMode(mode) && !canUseFeatures.value) {
    return "profile";
  }
  return mode;
}

function setMode(mode: Mode, updateUrl = true) {
  stopLivePolling();
  const nextMode = permittedMode(mode);
  activeMode.value = nextMode;
  if (nextMode !== "live" && settings.strategy === "all") {
    settings.strategy = "ema-rsi";
  }
  if (updateUrl && window.location.pathname !== modeRoutes[nextMode]) {
    window.history.pushState({ mode: nextMode }, "", modeRoutes[nextMode]);
  }
  if (nextMode === "live") {
    startLivePolling();
  }
  if (nextMode === "breadth") {
    void loadMarketBreadth();
  }
  if (nextMode === "profile") {
    void loadProfile();
  }
  if (nextMode === "admin") {
    void loadAdminUsers();
  }
}

function setLiveStatus(message: string, type: StatusType = "") {
  liveStatus.value = message;
  liveStatusType.value = type;
}

function setBreadthStatus(message: string, type: StatusType = "") {
  breadthStatus.value = message;
  breadthStatusType.value = type;
}

function setLabStatus(message: string, type: StatusType = "") {
  labStatus.value = message;
  labStatusType.value = type;
}

function setAdminStatus(message: string, type: StatusType = "") {
  adminStatus.value = message;
  adminStatusType.value = type;
}

function setProfileStatus(message: string, type: StatusType = "") {
  profileStatus.value = message;
  profileStatusType.value = type;
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
  await loadProfile();
  if (canUseFeatures.value) {
    await loadStrategies();
  } else {
    strategies.value = [];
  }
  setMode(modeFromLocation(), false);
}

async function loadProfile() {
  const payload = await requestJson<AuthMePayload>("/api/profile");
  authUser.value = payload.user;
  setProfileForm(payload.user);
}

async function loadAdminUsers() {
  setAdminStatus(t("status.loadingUsers"), "busy");
  try {
    const payload = await requestJson<AdminUsersPayload>("/api/admin/users");
    adminUsers.value = payload.users;
    setAdminStatus(`${t("status.loadedUsers")} ${payload.users.length}`);
  } catch (error) {
    adminUsers.value = [];
    setAdminStatus(errorMessage(error), "error");
  }
}

async function saveProfile() {
  setProfileStatus(t("status.savingProfile"), "busy");
  try {
    const payload = await requestJson<AuthPayload>("/api/profile", {
      method: "PATCH",
      body: JSON.stringify(profileForm),
    });
    authUser.value = payload.user;
    setProfileForm(payload.user);
    setProfileStatus(t("status.profileSaved"));
  } catch (error) {
    setProfileStatus(errorMessage(error), "error");
  }
}

async function updateUserAccess(user: AuthUser, isActive: boolean) {
  setAdminStatus(t("status.updatingAccess"), "busy");
  try {
    const payload = await requestJson<AuthPayload>(`/api/admin/users/${user.id}/access`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: isActive }),
    });
    adminUsers.value = adminUsers.value.map((existingUser) =>
      existingUser.id === payload.user.id ? payload.user : existingUser,
    );
    if (authUser.value?.id === payload.user.id) {
      authUser.value = payload.user;
      setProfileForm(payload.user);
      if (payload.user.is_active && !strategies.value.length) {
        await loadStrategies();
      }
    }
    setAdminStatus(t("status.accessUpdated"));
  } catch (error) {
    setAdminStatus(errorMessage(error), "error");
  }
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

function setProfileForm(user: AuthUser | null) {
  profileForm.first_name = user?.first_name ?? "";
  profileForm.last_name = user?.last_name ?? "";
  profileForm.middle_name = user?.middle_name ?? "";
}

async function logout() {
  await requestJson<{ ok: true }>("/api/auth/logout", { method: "POST" });
  authUser.value = null;
  stopLivePolling();
  livePayload.value = null;
  breadthPayload.value = null;
  labRows.value = [];
  adminUsers.value = [];
}

async function loadStrategies() {
  if (!canUseFeatures.value) {
    strategies.value = [];
    return;
  }
  const payload = await requestJson<StrategyPayload>("/api/strategies");
  strategies.value = payload.strategies;
}

async function loadLiveChart() {
  if (!canUseFeatures.value) {
    setLiveStatus(t("auth.inactive"), "error");
    return;
  }
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
  if (!canUseFeatures.value) {
    setBreadthStatus(t("auth.inactive"), "error");
    return;
  }
  setBreadthStatus(t("status.loadingBreadth"), "busy");
  try {
    breadthPayload.value = await requestJson<MarketBreadthPayload>("/api/market-breadth");
    setBreadthStatus(`${t("status.updated")} ${breadthUpdatedAt.value}`);
  } catch (error) {
    breadthPayload.value = null;
    setBreadthStatus(errorMessage(error), "error");
  }
}

async function runStrategyLab() {
  if (!canUseFeatures.value) {
    setLabStatus(t("auth.inactive"), "error");
    return;
  }
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

function formatDateTime(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "—";
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
      <button class="user-pill" type="button" @click="setMode('profile')">
        <span>{{ authUser.username }}</span>
        <b>{{ authUser.is_active ? t("auth.active") : t("auth.inactive") }}</b>
      </button>
      <button class="secondary logout-button" type="button" @click="logout">
        {{ t("auth.logout") }}
      </button>
      <button class="secondary profile-button" type="button" @click="setMode('profile')">
        {{ t("tabs.profile") }}
      </button>
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
    <section v-if="activeMode === 'live'" class="panel live-panel">
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
      </template>
    </section>

    <section v-else-if='activeMode === "profile"' class="panel profile-panel">
      <div class="panel-heading">
        <div>
          <h2>{{ t("pages.profile") }}</h2>
          <p>{{ authUser.username }}</p>
        </div>
        <div class="status" :class="authUser.is_active ? '' : 'is-error'">
          {{ authUser.is_active ? t("auth.active") : t("auth.inactive") }}
        </div>
      </div>
      <div v-if="!authUser.is_active" class="account-notice">
        <h3>{{ t("auth.inactive") }}</h3>
        <p>{{ t("auth.inactiveHelp") }}</p>
      </div>
      <form class="profile-form" @submit.prevent="saveProfile">
        <div class="field-grid">
          <label>
            <span>{{ t("labels.firstName") }}</span>
            <input v-model="profileForm.first_name" autocomplete="given-name">
          </label>
          <label>
            <span>{{ t("labels.lastName") }}</span>
            <input v-model="profileForm.last_name" autocomplete="family-name">
          </label>
          <label>
            <span>{{ t("labels.middleName") }}</span>
            <input v-model="profileForm.middle_name" autocomplete="additional-name">
          </label>
          <div class="profile-form-actions">
            <button class="primary" type="submit">{{ t("actions.saveProfile") }}</button>
            <div class="status" :class="profileStatusType ? `is-${profileStatusType}` : ''">
              {{ profileStatus }}
            </div>
          </div>
        </div>
      </form>
      <div class="profile-grid">
        <div class="profile-field">
          <span>{{ t("labels.username") }}</span>
          <b>{{ authUser.username }}</b>
        </div>
        <div class="profile-field">
          <span>{{ t("labels.firstName") }}</span>
          <b>{{ authUser.first_name || "—" }}</b>
        </div>
        <div class="profile-field">
          <span>{{ t("labels.lastName") }}</span>
          <b>{{ authUser.last_name || "—" }}</b>
        </div>
        <div class="profile-field">
          <span>{{ t("labels.middleName") }}</span>
          <b>{{ authUser.middle_name || "—" }}</b>
        </div>
        <div class="profile-field">
          <span>{{ t("labels.status") }}</span>
          <b>{{ authUser.is_active ? t("auth.active") : t("auth.inactive") }}</b>
        </div>
        <div class="profile-field">
          <span>{{ t("labels.activatedAt") }}</span>
          <b>{{ formatDateTime(authUser.activated_at) }}</b>
        </div>
        <div class="profile-field">
          <span>{{ t("labels.expiredAt") }}</span>
          <b>{{ formatDateTime(authUser.expired_at) }}</b>
        </div>
      </div>
    </section>

    <section v-else-if='activeMode === "admin"' class="panel admin-panel">
      <div class="panel-heading">
        <div>
          <h2>{{ t("pages.admin") }}</h2>
          <p>{{ t("pages.adminSubtitle") }}</p>
        </div>
        <div class="actions">
          <button class="primary" type="button" @click="loadAdminUsers">
            {{ t("actions.refreshUsers") }}
          </button>
          <div class="status" :class="adminStatusType ? `is-${adminStatusType}` : ''">
            {{ adminStatus }}
          </div>
        </div>
      </div>
      <div class="admin-toolbar">
        <label>
          <span>{{ t("labels.searchEmail") }}</span>
          <input v-model.trim="adminSearch" autocomplete="off" type="search">
        </label>
      </div>
      <div v-if="!adminUsers.length" class="empty">{{ t("empty.noUsers") }}</div>
      <div v-else-if="!filteredAdminUsers.length" class="empty">{{ t("empty.noMatchingUsers") }}</div>
      <table v-else>
        <thead>
          <tr>
            <th>{{ t("table.username") }}</th>
            <th>{{ t("labels.firstName") }}</th>
            <th>{{ t("labels.lastName") }}</th>
            <th>{{ t("labels.middleName") }}</th>
            <th>{{ t("table.active") }}</th>
            <th>{{ t("table.activated") }}</th>
            <th>{{ t("table.expires") }}</th>
            <th>{{ t("table.actions") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in filteredAdminUsers" :key="user.id">
            <td>{{ user.username }}</td>
            <td>{{ user.first_name || "—" }}</td>
            <td>{{ user.last_name || "—" }}</td>
            <td>{{ user.middle_name || "—" }}</td>
            <td>{{ user.is_active ? t("auth.active") : t("auth.inactive") }}</td>
            <td>{{ formatDateTime(user.activated_at) }}</td>
            <td>{{ formatDateTime(user.expired_at) }}</td>
            <td>
              <button
                class="secondary"
                type="button"
                @click="updateUserAccess(user, !user.is_active)"
              >
                {{ user.is_active ? t("actions.deactivateUser") : t("actions.activateUser") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
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
