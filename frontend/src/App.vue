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
  translateStrategyTitle,
  type Locale,
  type MessageKey,
} from "./i18n";
import type {
  AdminUsersPayload,
  AuthMePayload,
  AuthPayload,
  AuthUser,
  IndicatorDefinition,
  LiveChartPayload,
  MarketBreadthBar,
  MarketBreadthPayload,
  Mode,
  Marker,
  StrategyInfo,
  StrategyPayload,
} from "./types";

type StatusType = "" | "busy" | "error";
type SelectOption = {
  label: string;
  value: string | number;
};
type SignalDisplayMode = "consensus" | "individual";
type StrategyOption = StrategyInfo & {
  title: string;
  description: string;
};
type StrategyGroup = {
  id: string;
  label: string;
  strategyNames: string[];
  strategies: StrategyOption[];
};
type StrategyGroupDefinition = {
  id: string;
  labelKey: MessageKey;
  strategyNames: string[];
};

const routeModes: Record<string, Mode> = {
  "/": "live",
  "/live": "live",
  "/chart": "live",
  "/breadth": "breadth",
  "/profile": "profile",
  "/admin": "admin",
};

const modeRoutes: Record<Mode, string> = {
  live: "/live",
  breadth: "/breadth",
  profile: "/profile",
  admin: "/admin",
};

const liveSymbolOptions = [
  { value: "BTCUSDT", label: "BTCUSDT" },
  { value: "ETHUSDT", label: "ETHUSDT" },
] satisfies SelectOption[];

const moexBluechipSymbolOptions = [
  { value: "SBER", label: "SBER" },
  { value: "GAZP", label: "GAZP" },
  { value: "LKOH", label: "LKOH" },
  { value: "YNDX", label: "YNDX" },
  { value: "ROSN", label: "ROSN" },
  { value: "NVTK", label: "NVTK" },
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

const defaultLiveIndicators = ["ema", "vwap", "volume", "rsi", "macd"];
const strategyGroupCatalog: StrategyGroupDefinition[] = [
  {
    id: "recommended",
    labelKey: "strategyGroups.recommended",
    strategyNames: ["ema-rsi", "macd", "supertrend", "vwap-trend-continuation"],
  },
  {
    id: "trend",
    labelKey: "strategyGroups.trend",
    strategyNames: [
      "ema-ribbon",
      "ema-pullback",
      "atr-trailing-trend",
      "sma-crossover",
    ],
  },
  {
    id: "reversal",
    labelKey: "strategyGroups.reversal",
    strategyNames: [
      "bollinger-reversion",
      "rsi-reversal",
      "vwap-reversion",
      "stoch-rsi-reversal",
      "cci-reversal",
      "williams-r-reversal",
    ],
  },
  {
    id: "breakout",
    labelKey: "strategyGroups.breakout",
    strategyNames: [
      "donchian-breakout",
      "keltner-breakout",
      "bollinger-squeeze-release",
      "momentum-scalping",
    ],
  },
  {
    id: "volume",
    labelKey: "strategyGroups.volume",
    strategyNames: ["obv-trend", "volume-breakout"],
  },
  {
    id: "ensemble",
    labelKey: "strategyGroups.ensemble",
    strategyNames: ["combined-signals"],
  },
];

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
const liveStatus = ref(t("status.ready"));
const liveStatusType = ref<StatusType>("");
const breadthStatus = ref(t("status.ready"));
const breadthStatusType = ref<StatusType>("");
const liveMarket = ref("crypto_spot");
const liveSymbol = ref("BTCUSDT");
const liveInterval = ref("5m");
const liveLimit = ref<string | number>(180);
const liveRefresh = ref("10");
const liveSignalDisplayMode = ref<SignalDisplayMode>("consensus");
const liveConsensusMinConfirmations = ref(2);
const liveMaxSignals = ref(80);
const liveSelectedStrategies = ref<string[]>(["ema-rsi"]);
const liveVisibleIndicators = ref<string[]>([...defaultLiveIndicators]);
const showSignals = ref(true);
let liveTimer = 0;

const canUseFeatures = computed(() => Boolean(authUser.value?.is_active));
const isAdminUser = computed(() =>
  authUser.value?.is_admin === true,
);
const featureTabs = computed(() => [
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
  { value: "russian_bluechips", label: t("options.moexBluechips") },
]);
const liveFuturesSymbolOptions = computed<SelectOption[]>(() => [
  { value: "ES=F", label: t("options.sp500Future") },
]);
const liveSymbolsByMarket = computed<Record<string, SelectOption[]>>(() => ({
  crypto_spot: liveSymbolOptions,
  cme_futures: liveFuturesSymbolOptions.value,
  russian_bluechips: moexBluechipSymbolOptions,
}));
const liveSignalDisplayOptions = computed<SelectOption[]>(() => [
  { value: "consensus", label: t("options.consensusSignals") },
  { value: "individual", label: t("options.individualSignals") },
]);
const popularIndicatorOptions = computed<SelectOption[]>(() => [
  { value: "sma", label: t("indicators.sma") },
  { value: "ema", label: t("indicators.ema") },
  { value: "bollinger", label: t("indicators.bollinger") },
  { value: "vwap", label: t("indicators.vwap") },
  { value: "donchian", label: t("indicators.donchian") },
  { value: "volume", label: t("indicators.volume") },
  { value: "rsi", label: t("indicators.rsi") },
  { value: "macd", label: t("indicators.macd") },
  { value: "atr", label: t("indicators.atr") },
  { value: "stoch-rsi", label: t("indicators.stochRsi") },
]);
const liveStrategyOptions = computed<StrategyOption[]>(() =>
  strategies.value.map((strategy) => ({
    ...strategy,
    title: translateStrategyTitle(locale.value, strategy.name, strategy.name),
    description: translateStrategyDescription(locale.value, strategy.name, strategy.description),
  })),
);
const liveStrategyGroups = computed<StrategyGroup[]>(() => {
  const optionsByName = new Map(
    liveStrategyOptions.value.map((strategy) => [strategy.name, strategy]),
  );
  const groupedNames = new Set<string>();
  const groups = strategyGroupCatalog
    .map((definition) => {
      const groupedStrategies = definition.strategyNames
        .map((strategyName) => optionsByName.get(strategyName))
        .filter((strategy): strategy is StrategyOption => Boolean(strategy));

      groupedStrategies.forEach((strategy) => groupedNames.add(strategy.name));
      return {
        id: definition.id,
        label: t(definition.labelKey),
        strategyNames: groupedStrategies.map((strategy) => strategy.name),
        strategies: groupedStrategies,
      };
    })
    .filter((group) => group.strategies.length > 0);

  const ungroupedStrategies = liveStrategyOptions.value.filter(
    (strategy) => !groupedNames.has(strategy.name),
  );
  if (ungroupedStrategies.length) {
    groups.push({
      id: "other",
      label: t("strategyGroups.other"),
      strategyNames: ungroupedStrategies.map((strategy) => strategy.name),
      strategies: ungroupedStrategies,
    });
  }
  return groups;
});
const activeLiveSymbolOptions = computed(
  () => liveSymbolsByMarket.value[liveMarket.value] ?? liveSymbolOptions,
);
const selectedLiveStrategyNames = computed(() => {
  const availableNames = new Set(strategies.value.map((strategy) => strategy.name));
  const selectedNames = liveSelectedStrategies.value.filter((name) => availableNames.has(name));
  if (selectedNames.length) {
    return selectedNames;
  }
  const fallback = strategies.value[0]?.name ?? "ema-rsi";
  return [fallback];
});
const allLiveStrategiesSelected = computed(
  () =>
    strategies.value.length > 0 &&
    selectedLiveStrategyNames.value.length === strategies.value.length,
);
const liveStrategyRequest = computed(() =>
  allLiveStrategiesSelected.value ? "all" : selectedLiveStrategyNames.value.join(","),
);
const isMultiStrategyLive = computed(() => selectedLiveStrategyNames.value.length > 1);
const liveChartResetKey = computed(() =>
  [liveMarket.value, liveSymbol.value, liveInterval.value, liveLimit.value].join(":"),
);
const activeLiveStrategyLabel = computed(() => {
  if (allLiveStrategiesSelected.value) {
    return t("options.allStrategies");
  }
  const selectedNames = selectedLiveStrategyNames.value;
  if (selectedNames.length === 1) {
    return strategyTitle(selectedNames[0]);
  }
  return `${selectedNames.length} ${t("labels.strategiesSelected")}`;
});
const selectedLiveStrategyPreview = computed(() => {
  if (allLiveStrategiesSelected.value) {
    return `${strategies.value.length} ${t("labels.strategiesSelected")}`;
  }
  const selectedNames = selectedLiveStrategyNames.value;
  if (selectedNames.length === 1) {
    return (
      liveStrategyOptions.value.find((strategy) => strategy.name === selectedNames[0])?.description ??
      strategyTitle(selectedNames[0])
    );
  }
  const titles = selectedNames.map((name) => strategyTitle(name));
  if (titles.length <= 3) {
    return titles.join(", ");
  }
  return `${titles.slice(0, 3).join(", ")} +${titles.length - 3}`;
});
const liveSignalCount = computed(() => livePayload.value?.signals.length ?? 0);
const liveCandleCount = computed(() => livePayload.value?.candles.length ?? 0);
const visibleLiveIndicators = computed<IndicatorDefinition[]>(() => {
  const selectedIndicators = new Set(liveVisibleIndicators.value);
  return (livePayload.value?.indicators ?? []).filter((indicator) =>
    selectedIndicators.has(indicator.id),
  );
});
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
}));
const consensusSignals = computed(() =>
  groupSignalsByConsensus(livePayload.value?.signals ?? [], liveConsensusMinConfirmations.value),
);
const displayedSignals = computed(() => {
  const rawSignals = livePayload.value?.signals ?? [];
  if (!isMultiStrategyLive.value || liveSignalDisplayMode.value === "individual") {
    return isMultiStrategyLive.value
      ? limitRecentSignals(rawSignals, liveMaxSignals.value)
      : rawSignals;
  }
  return limitRecentSignals(consensusSignals.value, liveMaxSignals.value);
});

watch(liveMarket, () => {
  liveSymbol.value = String(activeLiveSymbolOptions.value[0]?.value ?? "BTCUSDT");
});

watch(strategies, () => {
  liveSelectedStrategies.value = selectedLiveStrategyNames.value;
});

watch(liveStrategyRequest, (strategyValue) => {
  settings.strategy = strategyValue;
});

watch([liveMarket, liveSymbol, liveInterval, liveLimit, liveStrategyRequest], () => {
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
  return routeModes[window.location.pathname] ?? "live";
}

function isFeatureMode(mode: Mode): boolean {
  return mode === "live" || mode === "breadth";
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
  if (nextMode !== "live") {
    resetLiveStrategies();
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
        strategy: liveStrategyRequest.value,
    });
    livePayload.value = await requestJson<LiveChartPayload>(`/api/live-chart?${query}`);
    setLiveStatus(`${t("status.updated")} ${new Date().toLocaleTimeString()}`);
  } catch (error) {
    livePayload.value = null;
    setLiveStatus(errorMessage(error), "error");
  }
}

function toggleLiveStrategy(strategyName: string) {
  if (liveSelectedStrategies.value.includes(strategyName)) {
    if (liveSelectedStrategies.value.length > 1) {
      liveSelectedStrategies.value = liveSelectedStrategies.value.filter((name) => name !== strategyName);
    }
    return;
  }
  liveSelectedStrategies.value = [...liveSelectedStrategies.value, strategyName];
}

function setLiveStrategies(strategyNames: string[]) {
  const availableNames = new Set(strategies.value.map((strategy) => strategy.name));
  const nextNames = strategyNames.filter((strategyName) => availableNames.has(strategyName));
  liveSelectedStrategies.value = nextNames.length ? nextNames : [strategies.value[0]?.name ?? "ema-rsi"];
}

function selectLiveStrategyGroup(strategyNames: string[]) {
  setLiveStrategies(strategyNames);
}

function selectAllLiveStrategies() {
  setLiveStrategies(strategies.value.map((strategy) => strategy.name));
}

function clearLiveStrategies() {
  resetLiveStrategies();
}

function resetLiveStrategies() {
  liveSelectedStrategies.value = [strategies.value[0]?.name ?? "ema-rsi"];
}

function toggleLiveIndicator(indicatorId: string) {
  if (liveVisibleIndicators.value.includes(indicatorId)) {
    liveVisibleIndicators.value = liveVisibleIndicators.value.filter((id) => id !== indicatorId);
    return;
  }
  liveVisibleIndicators.value = [...liveVisibleIndicators.value, indicatorId];
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

function strategyTitle(name: string): string {
  return translateStrategyTitle(locale.value, name, name);
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

function limitRecentSignals(signals: Marker[], limit: number): Marker[] {
  const normalizedLimit = Math.max(0, Math.floor(Number(limit) || 0));
  if (!normalizedLimit || signals.length <= normalizedLimit) {
    return signals;
  }
  return signals.slice(-normalizedLimit);
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
        <div class="strategy-picker live-strategy-field">
          <strong class="strategy-picker-label">{{ t("labels.strategy") }}</strong>
          <details class="strategy-menu" :aria-label="t('labels.strategyPickerHint')">
            <summary class="strategy-summary">
              <span>
                <b>{{ activeLiveStrategyLabel }}</b>
                <small>{{ selectedLiveStrategyPreview }}</small>
              </span>
            </summary>
            <div class="strategy-menu-body">
              <div class="strategy-actions">
                <button class="secondary" type="button" @click="selectAllLiveStrategies">
                  {{ t("actions.selectAll") }}
                </button>
                <button class="secondary" type="button" @click="clearLiveStrategies">
                  {{ t("actions.clear") }}
                </button>
              </div>
              <section
                v-for="group in liveStrategyGroups"
                :key="group.id"
                class="strategy-group"
              >
                <div class="strategy-group-heading">
                  <strong>{{ group.label }}</strong>
                  <button
                    class="secondary"
                    type="button"
                    @click="selectLiveStrategyGroup(group.strategyNames)"
                  >
                    {{ t("actions.selectAll") }}
                  </button>
                </div>
                <label
                  v-for="strategy in group.strategies"
                  :key="strategy.name"
                  class="strategy-row"
                  :class="{ 'is-active': liveSelectedStrategies.includes(strategy.name) }"
                >
                  <input
                    type="checkbox"
                    :checked="liveSelectedStrategies.includes(strategy.name)"
                    @change="toggleLiveStrategy(strategy.name)"
                  >
                  <span class="strategy-row-copy">
                    <b>{{ strategyTitle(strategy.name) }}</b>
                    <small>{{ strategy.description }}</small>
                  </span>
                </label>
              </section>
            </div>
          </details>
        </div>
        <label v-if="isMultiStrategyLive">
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
        <label v-if="isMultiStrategyLive && liveSignalDisplayMode === 'consensus'">
          <span>{{ t("labels.minConfirmations") }}</span>
          <input v-model.number="liveConsensusMinConfirmations" type="number" min="1" max="20">
        </label>
        <label v-if="isMultiStrategyLive">
          <span>{{ t("labels.maxMarkers") }}</span>
          <input v-model.number="liveMaxSignals" type="number" min="10" max="500">
        </label>
        <label><span>{{ t("labels.refreshSec") }}</span><input v-model="liveRefresh" type="number" min="2" max="300"></label>
        <label class="toggle-row"><input v-model="showSignals" type="checkbox"><span>{{ t("labels.strategyMarkers") }}</span></label>
        <button class="primary" type="button" @click="refreshLiveChart">{{ t("actions.refreshChart") }}</button>
      </div>
      <div class="indicator-picker">
        <span>{{ t("labels.indicators") }}</span>
        <label
          v-for="option in popularIndicatorOptions"
          :key="option.value"
          class="check-chip"
          :class="{ 'is-active': liveVisibleIndicators.includes(String(option.value)) }"
        >
          <input
            type="checkbox"
            :checked="liveVisibleIndicators.includes(String(option.value))"
            @change="toggleLiveIndicator(String(option.value))"
          >
          <span>{{ option.label }}</span>
        </label>
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
          :indicators="visibleLiveIndicators"
          :show-signals="showSignals"
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
            :show-signals="false"
            :reset-key="`breadth:${breadthPutCall.symbol}`"
            :aria-label="`${chartLabels.aria} ${breadthPutCall.symbol}`"
            :empty-label="chartLabels.empty"
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
                :show-signals="false"
                :reset-key="`breadth:${item.symbol}`"
                :aria-label="`${chartLabels.aria} ${item.symbol}`"
                :empty-label="chartLabels.empty"
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

  </main>
  </template>
</template>
