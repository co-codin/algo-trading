<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { requestJson, toQuery } from "./api";
import TradingViewChart from "./components/TradingViewChart.vue";
import {
  LIVE_WORKSPACE_STORAGE_KEY,
  defaultLiveIndicators,
  liveCandleOptions,
  liveIntervalOptions,
  liveSymbolOptions,
  mag7StockSymbolOptions,
  moexBluechipSymbolOptions,
  moexFuturesSymbolOptions,
  moexIndexSymbolOptions,
  strategyGroupCatalog,
  type SelectOption,
} from "./liveConfig";
import {
  groupSignalsByConsensus,
  limitRecentSignals,
  normalizeSearchText,
  optionMatchesSearch,
} from "./liveUtils";
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
  MarketBreadthGroup,
  MarketBreadthPayload,
  Mode,
  StrategyInfo,
  StrategyPayload,
} from "./types";

type StatusType = "" | "busy" | "error";
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
type LiveHealthTone = "good" | "warning" | "error";
type LiveDataHealth = {
  label: string;
  detail: string;
  tone: LiveHealthTone;
};
type BreadthGroupSummary = {
  name: string;
  average: number | null;
  strongCount: number;
  weakCount: number;
  total: number;
  latestDate: string;
};
type BreadthGroupView = {
  group: MarketBreadthGroup;
  summary: BreadthGroupSummary;
};
type LiveWorkspace = {
  id: string;
  name: string;
  market: string;
  symbol: string;
  interval: string;
  limit: string | number;
  indicators: string[];
  strategies: string[];
  signalDisplayMode: SignalDisplayMode;
  consensusMinConfirmations: number;
  maxSignals: number;
  showSignals: boolean;
  savedAt: string;
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
const adminExpiryEdits = reactive<Record<number, string>>({});
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
const liveSymbolSearch = ref("");
const liveInterval = ref("5m");
const liveLimit = ref<string | number>(180);
const liveRefresh = ref("10");
const liveSignalDisplayMode = ref<SignalDisplayMode>("consensus");
const liveConsensusMinConfirmations = ref(5);
const liveMaxSignals = ref(80);
const liveSelectedStrategies = ref<string[]>(["ema-rsi"]);
const liveStrategySearch = ref("");
const liveStrategyMenu = ref<HTMLDetailsElement | null>(null);
const liveVisibleIndicators = ref<string[]>([...defaultLiveIndicators]);
const liveWorkspaces = ref<LiveWorkspace[]>([]);
const liveWorkspaceName = ref("");
const liveAlertsEnabled = ref(false);
const lastAlertSignature = ref("");
const showSignals = ref(true);
const liveDataUpdatedAt = ref<string | null>(null);
let liveTimer = 0;
let isApplyingLiveSettingsFromUrl = false;

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
  { value: "commodities", label: t("options.commodities") },
  { value: "mag7_stocks", label: t("options.mag7Stocks") },
  { value: "russian_bluechips", label: t("options.moexBluechips") },
  { value: "russian_indices", label: t("options.moexIndices") },
  { value: "russian_futures", label: t("options.moexFutures") },
]);
const liveFuturesSymbolOptions = computed<SelectOption[]>(() => [
  { value: "ES=F", label: t("options.sp500Future") },
]);
const commoditySymbolOptions = computed<SelectOption[]>(() => [
  { value: "GC=F", label: t("options.commodityGold") },
  { value: "SI=F", label: t("options.commoditySilver") },
  { value: "NG=F", label: t("options.commodityNaturalGas") },
  { value: "BZ=F", label: t("options.commodityBrentOil") },
  { value: "PL=F", label: t("options.commodityPlatinum") },
  { value: "PA=F", label: t("options.commodityPalladium") },
  { value: "HG=F", label: t("options.commodityCopper") },
]);
const liveSymbolsByMarket = computed<Record<string, SelectOption[]>>(() => ({
  crypto_spot: liveSymbolOptions,
  cme_futures: liveFuturesSymbolOptions.value,
  commodities: commoditySymbolOptions.value,
  mag7_stocks: mag7StockSymbolOptions,
  russian_bluechips: moexBluechipSymbolOptions,
  russian_indices: moexIndexSymbolOptions,
  russian_futures: moexFuturesSymbolOptions,
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
const filteredLiveStrategyGroups = computed<StrategyGroup[]>(() => {
  const query = normalizeSearchText(liveStrategySearch.value);
  if (!query) {
    return liveStrategyGroups.value;
  }
  return liveStrategyGroups.value
    .map((group) => {
      const strategies = group.strategies.filter((strategy) =>
        strategyMatchesSearch(strategy, group, query),
      );
      return {
        ...group,
        strategyNames: strategies.map((strategy) => strategy.name),
        strategies,
      };
    })
    .filter((group) => group.strategies.length > 0);
});
const activeLiveSymbolOptions = computed(
  () => liveSymbolsByMarket.value[liveMarket.value] ?? liveSymbolOptions,
);
const filteredLiveSymbolOptions = computed(() => {
  const query = liveSymbolSearch.value;
  if (!query) {
    return activeLiveSymbolOptions.value;
  }
  return activeLiveSymbolOptions.value.filter((option) => optionMatchesSearch(option, query));
});
const hasLiveSymbolSearch = computed(() => normalizeSearchText(liveSymbolSearch.value).length > 0);
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
const liveDataUpdatedLabel = computed(() => formatDateTime(liveDataUpdatedAt.value));
const liveDataHealth = computed<LiveDataHealth>(() => {
  if (liveStatusType.value === "error") {
    return {
      label: t("health.error"),
      detail: liveStatus.value,
      tone: "error",
    };
  }
  if (!livePayload.value) {
    return {
      label: t("health.waiting"),
      detail: t("empty.loadChart"),
      tone: "warning",
    };
  }
  if (
    liveMarket.value === "russian_bluechips" ||
    liveMarket.value === "russian_indices" ||
    liveMarket.value === "russian_futures"
  ) {
    return {
      label: t("health.exchange"),
      detail: t("health.moexDetail"),
      tone: "warning",
    };
  }
  return {
    label: t("health.live"),
    detail: livePayload.value.data_source,
    tone: "good",
  };
});
const visibleLiveIndicators = computed<IndicatorDefinition[]>(() => {
  const selectedIndicators = new Set(liveVisibleIndicators.value);
  return (livePayload.value?.indicators ?? []).filter((indicator) =>
    selectedIndicators.has(indicator.id),
  );
});
const breadthGroups = computed<MarketBreadthGroup[]>(() => breadthPayload.value?.groups ?? []);
const breadthGroupSummaries = computed<BreadthGroupSummary[]>(() =>
  breadthGroups.value.map((group) => summarizeBreadthGroup(group)),
);
const breadthGroupViews = computed<BreadthGroupView[]>(() =>
  breadthGroups.value.map((group, index) => ({
    group,
    summary: breadthGroupSummaries.value[index],
  })),
);
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
  liveSymbolSearch.value = "";
  if (isApplyingLiveSettingsFromUrl) {
    return;
  }
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

watch([liveMarket, liveSymbol, liveVisibleIndicators, liveStrategyRequest], () => {
  if (activeMode.value === "live" && !isApplyingLiveSettingsFromUrl) {
    syncLiveUrl();
  }
}, { deep: true });

watch(displayedSignals, () => {
  maybeNotifyLiveAlert();
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
  loadLiveWorkspaces();
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
  const nextMode = modeFromLocation();
  if (nextMode === "live") {
    applyLiveSettingsFromLocation();
  }
  setMode(nextMode, false);
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
  const nextUrl = nextMode === "live" ? liveUrlPath() : modeRoutes[nextMode];
  const currentUrl = `${window.location.pathname}${window.location.search}`;
  if (updateUrl && currentUrl !== nextUrl) {
    window.history.pushState({ mode: nextMode }, "", nextUrl);
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
  applyLiveSettingsFromLocation();
  setMode(modeFromLocation(), false);
}

function applyLiveSettingsFromLocation() {
  if (modeFromLocation() !== "live") {
    return;
  }
  const params = new URLSearchParams(window.location.search);
  isApplyingLiveSettingsFromUrl = true;
  try {
    const market = params.get("market");
    if (market && liveSymbolsByMarket.value[market]) {
      liveMarket.value = market;
    }
    const symbolOptions = liveSymbolsByMarket.value[liveMarket.value] ?? liveSymbolOptions;
    const symbol = (params.get("symbol") ?? "").trim().toUpperCase();
    const matchedSymbol = symbolOptions.find(
      (option) => String(option.value).toUpperCase() === symbol,
    );
    if (matchedSymbol) {
      liveSymbol.value = String(matchedSymbol.value);
    } else if (!symbolOptions.some((option) => String(option.value) === liveSymbol.value)) {
      liveSymbol.value = String(symbolOptions[0]?.value ?? "BTCUSDT");
    }
    if (params.has("indicators")) {
      liveVisibleIndicators.value = parseLiveIndicators(params.get("indicators"));
    }
    if (params.has("strategy")) {
      liveSelectedStrategies.value = parseLiveStrategyRequest(params.get("strategy"));
    }
  } finally {
    queueMicrotask(() => {
      isApplyingLiveSettingsFromUrl = false;
    });
  }
}

function syncLiveUrl() {
  const nextUrl = liveUrlPath();
  const currentUrl = `${window.location.pathname}${window.location.search}`;
  if (currentUrl !== nextUrl) {
    window.history.replaceState({ mode: "live" }, "", nextUrl);
  }
}

function liveUrlPath() {
  const params = new URLSearchParams();
  params.set("market", liveMarket.value);
  params.set("symbol", liveSymbol.value);
  params.set("indicators", liveVisibleIndicators.value.join(","));
  params.set("strategy", liveStrategyRequest.value);
  return `${modeRoutes.live}?${params.toString()}`;
}

function parseLiveIndicators(value: string | null) {
  if (!value) {
    return [];
  }
  const availableIndicators = new Set(
    popularIndicatorOptions.value.map((option) => String(option.value)),
  );
  return [
    ...new Set(
      value
        .split(",")
        .map((indicator) => indicator.trim().toLowerCase())
        .filter((indicator) => availableIndicators.has(indicator)),
    ),
  ];
}

function parseLiveStrategyRequest(value: string | null): string[] {
  const fallback = strategies.value[0]?.name ?? "ema-rsi";
  if (!value) {
    return [fallback];
  }

  const availableByName = new Map(
    strategies.value.map((strategy) => [strategy.name.toLowerCase(), strategy.name]),
  );
  const normalizedValue = value.trim().toLowerCase();
  if (normalizedValue === "all") {
    const allStrategyNames = strategies.value.map((strategy) => strategy.name);
    return allStrategyNames.length ? allStrategyNames : [fallback];
  }

  const requestedNames = [
    ...new Set(
      value
        .split(",")
        .map((strategyName) => availableByName.get(strategyName.trim().toLowerCase()))
        .filter((strategyName): strategyName is string => Boolean(strategyName)),
    ),
  ];
  return requestedNames.length ? requestedNames : [fallback];
}

function loadLiveWorkspaces() {
  try {
    const parsed = JSON.parse(localStorage.getItem(LIVE_WORKSPACE_STORAGE_KEY) ?? "[]");
    liveWorkspaces.value = Array.isArray(parsed)
      ? parsed.filter(isLiveWorkspace).slice(0, 8)
      : [];
  } catch {
    liveWorkspaces.value = [];
  }
}

function persistLiveWorkspaces() {
  localStorage.setItem(LIVE_WORKSPACE_STORAGE_KEY, JSON.stringify(liveWorkspaces.value));
}

function saveLiveWorkspace() {
  const now = new Date();
  const workspace: LiveWorkspace = {
    id: `${now.getTime()}`,
    name: liveWorkspaceName.value.trim() || `${liveSymbol.value} ${liveInterval.value}`,
    market: liveMarket.value,
    symbol: liveSymbol.value,
    interval: liveInterval.value,
    limit: liveLimit.value,
    indicators: [...liveVisibleIndicators.value],
    strategies: [...selectedLiveStrategyNames.value],
    signalDisplayMode: liveSignalDisplayMode.value,
    consensusMinConfirmations: liveConsensusMinConfirmations.value,
    maxSignals: liveMaxSignals.value,
    showSignals: showSignals.value,
    savedAt: now.toISOString(),
  };
  liveWorkspaces.value = [
    workspace,
    ...liveWorkspaces.value.filter((existing) => existing.name !== workspace.name),
  ].slice(0, 8);
  liveWorkspaceName.value = "";
  persistLiveWorkspaces();
  setLiveStatus(t("status.workspaceSaved"));
}

function applyLiveWorkspace(workspace: LiveWorkspace) {
  liveMarket.value = workspace.market;
  const symbolOptions = liveSymbolsByMarket.value[workspace.market] ?? liveSymbolOptions;
  const symbolExists = symbolOptions.some(
    (option) => String(option.value) === workspace.symbol,
  );
  liveSymbol.value = symbolExists
    ? workspace.symbol
    : String(symbolOptions[0]?.value ?? "BTCUSDT");
  liveInterval.value = workspace.interval;
  liveLimit.value = workspace.limit;
  liveVisibleIndicators.value = [...workspace.indicators];
  liveSignalDisplayMode.value = workspace.signalDisplayMode;
  liveConsensusMinConfirmations.value = workspace.consensusMinConfirmations;
  liveMaxSignals.value = workspace.maxSignals;
  showSignals.value = workspace.showSignals;
  setLiveStrategies(workspace.strategies);
  syncLiveUrl();
  setLiveStatus(`${t("status.workspaceLoaded")} ${workspace.name}`);
}

function deleteLiveWorkspace(workspaceId: string) {
  liveWorkspaces.value = liveWorkspaces.value.filter(
    (workspace) => workspace.id !== workspaceId,
  );
  persistLiveWorkspaces();
}

function isLiveWorkspace(value: unknown): value is LiveWorkspace {
  if (!value || typeof value !== "object") {
    return false;
  }
  const workspace = value as Partial<LiveWorkspace>;
  return (
    typeof workspace.id === "string" &&
    typeof workspace.name === "string" &&
    typeof workspace.market === "string" &&
    typeof workspace.symbol === "string" &&
    typeof workspace.interval === "string" &&
    Array.isArray(workspace.indicators) &&
    Array.isArray(workspace.strategies)
  );
}

async function toggleLiveAlerts() {
  if (!liveAlertsEnabled.value) {
    return;
  }
  if (!("Notification" in window)) {
    liveAlertsEnabled.value = false;
    setLiveStatus(t("status.alertsUnavailable"), "error");
    return;
  }
  if (Notification.permission === "default") {
    await Notification.requestPermission();
  }
  if (Notification.permission !== "granted") {
    liveAlertsEnabled.value = false;
    setLiveStatus(t("status.alertsBlocked"), "error");
    return;
  }
  setLiveStatus(t("status.alertsEnabled"));
  maybeNotifyLiveAlert();
}

function maybeNotifyLiveAlert() {
  if (
    !liveAlertsEnabled.value ||
    !("Notification" in window) ||
    Notification.permission !== "granted"
  ) {
    return;
  }
  const latestSignal = displayedSignals.value.at(-1);
  if (!latestSignal) {
    return;
  }
  const signature = `${liveSymbol.value}:${latestSignal.time}:${latestSignal.type}:${latestSignal.reason}`;
  if (signature === lastAlertSignature.value) {
    return;
  }
  lastAlertSignature.value = signature;
  new Notification(`${liveSymbol.value} ${latestSignal.type}`, {
    body: latestSignal.reason,
  });
}

function exportLiveSnapshot() {
  const snapshot = {
    exported_at: new Date().toISOString(),
    workspace: {
      market: liveMarket.value,
      symbol: liveSymbol.value,
      interval: liveInterval.value,
      limit: liveLimit.value,
      indicators: liveVisibleIndicators.value,
      strategies: selectedLiveStrategyNames.value,
      signal_display_mode: liveSignalDisplayMode.value,
      consensus_min_confirmations: liveConsensusMinConfirmations.value,
      max_signals: liveMaxSignals.value,
      show_signals: showSignals.value,
    },
    data_health: liveDataHealth.value,
    payload: livePayload.value,
  };
  const blob = new Blob([JSON.stringify(snapshot, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `algo-live-snapshot-${liveSymbol.value}-${Date.now()}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
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
    syncAdminExpiryEdits(payload.users);
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
      body: JSON.stringify({
        is_active: isActive,
        expired_at: isoDateTimeFromDateInput(adminExpiryEdits[user.id]),
      }),
    });
    adminUsers.value = adminUsers.value.map((existingUser) =>
      existingUser.id === payload.user.id ? payload.user : existingUser,
    );
    syncAdminExpiryEdits([payload.user]);
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

async function updateUserExpiry(user: AuthUser) {
  setAdminStatus(t("status.updatingAccess"), "busy");
  try {
    const payload = await requestJson<AuthPayload>(`/api/admin/users/${user.id}/access`, {
      method: "PATCH",
      body: JSON.stringify({
        is_active: user.is_active,
        expired_at: isoDateTimeFromDateInput(adminExpiryEdits[user.id]),
      }),
    });
    adminUsers.value = adminUsers.value.map((existingUser) =>
      existingUser.id === payload.user.id ? payload.user : existingUser,
    );
    syncAdminExpiryEdits([payload.user]);
    if (authUser.value?.id === payload.user.id) {
      authUser.value = payload.user;
      setProfileForm(payload.user);
    }
    setAdminStatus(t("status.expirationUpdated"));
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

function syncAdminExpiryEdits(users: AuthUser[]) {
  for (const user of users) {
    adminExpiryEdits[user.id] = dateInputValue(user.expired_at);
  }
}

function dateInputValue(value: string | null | undefined): string {
  return value ? value.slice(0, 10) : "";
}

function isoDateTimeFromDateInput(value: string): string | null {
  return value ? `${value}T23:59:59Z` : null;
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
    liveDataUpdatedAt.value = new Date().toISOString();
    setLiveStatus(`${t("status.updated")} ${new Date().toLocaleTimeString()}`);
  } catch (error) {
    livePayload.value = null;
    liveDataUpdatedAt.value = null;
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
  if (liveSelectedStrategies.value.length > 1) {
    liveSignalDisplayMode.value = "consensus";
  }
}

function selectLiveStrategyGroup(strategyNames: string[]) {
  setLiveStrategies(strategyNames);
}

function selectAllLiveStrategies() {
  setLiveStrategies(strategies.value.map((strategy) => strategy.name));
  closeLiveStrategyMenu();
}

function clearLiveStrategies() {
  resetLiveStrategies();
}

function closeLiveStrategyMenu() {
  liveStrategyMenu.value?.removeAttribute("open");
}

function resetLiveStrategies() {
  liveSelectedStrategies.value = [strategies.value[0]?.name ?? "ema-rsi"];
}

function selectLiveSymbol(value: string | number) {
  liveSymbol.value = String(value);
  liveSymbolSearch.value = "";
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
  liveTimer = window.setInterval(() => void loadLiveChart(), seconds * 1000);
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

function strategyMatchesSearch(
  strategy: StrategyOption,
  group: StrategyGroup,
  normalizedQuery: string,
): boolean {
  const searchableText = normalizeSearchText(
    `${strategy.title} ${strategy.description} ${strategy.name} ${group.label}`,
  );
  return searchableText.includes(normalizedQuery);
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

function formatBreadthPercent(value: number | null): string {
  return value === null ? "—" : `${formatNumber(value)}%`;
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

function breadthSummaryToneClass(summary: BreadthGroupSummary): string {
  if (summary.average === null) {
    return "";
  }
  return summary.average >= 50 ? "is-positive" : "is-negative";
}

function summarizeBreadthGroup(group: MarketBreadthGroup): BreadthGroupSummary {
  const candles = group.items
    .map((item) => latestBreadthCandle(item.symbol))
    .filter((candle): candle is MarketBreadthBar => Boolean(candle));
  const values = candles.map((candle) => candle.close);
  const average = values.length
    ? values.reduce((total, value) => total + value, 0) / values.length
    : null;
  const strongCount = values.filter((value) => value >= 50).length;
  const latestDate = candles.reduce(
    (latest, candle) => (candle.date > latest ? candle.date : latest),
    "",
  );
  return {
    name: group.name,
    average,
    strongCount,
    weakCount: values.length - strongCount,
    total: group.items.length,
    latestDate: latestDate || "—",
  };
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
      <div class="health-strip">
        <div class="health-badge" :class="`is-${liveDataHealth.tone}`">
          <span>{{ t("labels.dataHealth") }}</span>
          <b>{{ liveDataHealth.label }}</b>
          <small>{{ liveDataHealth.detail }}</small>
        </div>
        <div class="health-badge">
          <span>{{ t("labels.updated") }}</span>
          <b>{{ liveDataUpdatedLabel }}</b>
          <small>{{ livePayload?.data_source ?? t("health.waiting") }}</small>
        </div>
      </div>
      <div class="live-controls">
        <div class="live-control-section market-controls">
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
          <label class="symbol-picker">
            <span>{{ t("labels.symbol") }}</span>
            <input
              v-model.trim="liveSymbolSearch"
              autocomplete="off"
              type="search"
              :placeholder="t('labels.symbolSearch')"
            >
            <div
              v-if="hasLiveSymbolSearch"
              class="symbol-results"
              role="listbox"
              :aria-label="t('labels.symbolSearch')"
            >
              <button
                v-for="option in filteredLiveSymbolOptions"
                :key="`symbol-search-${option.value}`"
                class="symbol-result"
                :class="{ 'is-active': String(option.value) === liveSymbol }"
                type="button"
                @click="selectLiveSymbol(option.value)"
              >
                <b>{{ option.value }}</b>
                <small v-if="String(option.label) !== String(option.value)">
                  {{ option.label }}
                </small>
              </button>
              <div v-if="!filteredLiveSymbolOptions.length" class="symbol-result-empty">
                {{ t("empty.noMatchingSymbols") }}
              </div>
            </div>
            <select v-model="liveSymbol">
              <option v-if="!filteredLiveSymbolOptions.length" disabled value="">
                {{ t("empty.noMatchingSymbols") }}
              </option>
              <option
                v-for="option in filteredLiveSymbolOptions"
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
        </div>
        <div class="live-control-section signal-controls">
          <div class="strategy-picker live-strategy-field">
            <strong class="strategy-picker-label">{{ t("labels.strategy") }}</strong>
            <details ref="liveStrategyMenu" class="strategy-menu" :aria-label="t('labels.strategyPickerHint')">
              <summary class="strategy-summary">
                <span>
                  <b>{{ activeLiveStrategyLabel }}</b>
                  <small>{{ selectedLiveStrategyPreview }}</small>
                </span>
              </summary>
              <div class="strategy-menu-body">
                <input
                  v-model.trim="liveStrategySearch"
                  class="strategy-search"
                  autocomplete="off"
                  type="search"
                  :placeholder="t('labels.strategySearch')"
                >
                <div class="strategy-actions">
                  <button class="secondary" type="button" @click="selectAllLiveStrategies">
                    {{ t("actions.selectAll") }}
                  </button>
                  <button class="secondary" type="button" @click="clearLiveStrategies">
                    {{ t("actions.clear") }}
                  </button>
                </div>
                <section
                  v-for="group in filteredLiveStrategyGroups"
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
          <label class="toggle-row">
            <input v-model="showSignals" type="checkbox">
            <span>{{ t("labels.strategyMarkers") }}</span>
          </label>
        </div>
        <div class="live-control-section refresh-controls">
          <label>
            <span>{{ t("labels.refreshSec") }}</span>
            <input v-model="liveRefresh" type="number" min="2" max="300">
          </label>
          <button class="primary" type="button" @click="refreshLiveChart">
            {{ t("actions.refreshChart") }}
          </button>
        </div>
      </div>
      <div class="workspace-controls">
        <label>
          <span>{{ t("labels.workspace") }}</span>
          <input
            v-model.trim="liveWorkspaceName"
            autocomplete="off"
            :placeholder="`${liveSymbol} ${liveInterval}`"
          >
        </label>
        <button class="secondary" type="button" @click="saveLiveWorkspace">
          {{ t("actions.saveWorkspace") }}
        </button>
        <button class="secondary" type="button" @click="exportLiveSnapshot">
          {{ t("actions.exportSnapshot") }}
        </button>
        <label class="alert-controls">
          <input v-model="liveAlertsEnabled" type="checkbox" @change="toggleLiveAlerts">
          <span>{{ t("labels.alerts") }}</span>
        </label>
        <div v-if="liveWorkspaces.length" class="workspace-list">
          <div
            v-for="workspace in liveWorkspaces"
            :key="workspace.id"
            class="workspace-chip"
          >
            <button class="secondary" type="button" @click="applyLiveWorkspace(workspace)">
              {{ workspace.name }}
            </button>
            <button
              class="secondary workspace-delete"
              type="button"
              :aria-label="`${t('actions.deleteWorkspace')} ${workspace.name}`"
              @click="deleteLiveWorkspace(workspace.id)"
            >
              x
            </button>
          </div>
        </div>
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
        <div class="chart-stage">
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
          <div v-else class="empty chart-empty">{{ t("empty.loadChart") }}</div>
        </div>
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
            derive-candles-from-close
            :reset-key="`breadth:${breadthPutCall.symbol}`"
            :aria-label="`${chartLabels.aria} ${breadthPutCall.symbol}`"
            :empty-label="chartLabels.empty"
            :long-signal-label="chartLabels.longSignal"
            :short-signal-label="chartLabels.shortSignal"
          />
        </section>
        <div class="breadth-overview-grid">
          <article
            v-for="summary in breadthGroupSummaries"
            :key="`summary-${summary.name}`"
            class="breadth-overview-card"
            :class="breadthSummaryToneClass(summary)"
          >
            <div class="breadth-overview-title">
              <span>{{ t("labels.marketBreadthGroup") }}</span>
              <h3>{{ summary.name }}</h3>
            </div>
            <div class="breadth-overview-value">
              <b>{{ formatBreadthPercent(summary.average) }}</b>
              <span>{{ t("labels.averageBreadth") }}</span>
            </div>
            <dl class="breadth-overview-stats">
              <div>
                <dt>{{ t("labels.bullish") }}</dt>
                <dd>{{ summary.strongCount }}</dd>
              </div>
              <div>
                <dt>{{ t("labels.weak") }}</dt>
                <dd>{{ summary.weakCount }}</dd>
              </div>
              <div>
                <dt>{{ t("labels.series") }}</dt>
                <dd>{{ summary.total }}</dd>
              </div>
            </dl>
          </article>
        </div>

        <div class="breadth-detail-stack">
          <section
            v-for="view in breadthGroupViews"
            :key="view.group.name"
            class="breadth-detail-section"
          >
            <header class="breadth-detail-header">
              <div>
                <span>{{ t("labels.marketBreadthGroup") }}</span>
                <h3>{{ view.group.name }}</h3>
              </div>
              <div class="breadth-detail-meta" :class="breadthSummaryToneClass(view.summary)">
                <span>
                  {{ t("labels.averageBreadth") }}
                  <b>{{ formatBreadthPercent(view.summary.average) }}</b>
                </span>
                <span>
                  {{ t("labels.bullish") }}
                  <b>{{ view.summary.strongCount }}</b>
                </span>
                <span>
                  {{ t("labels.updated") }}
                  <b>{{ view.summary.latestDate }}</b>
                </span>
              </div>
            </header>
            <div class="breadth-detail-grid">
              <article
                v-for="item in view.group.items"
                :key="item.symbol"
                class="breadth-metric-card"
                :class="breadthToneClass(item.symbol)"
              >
                <header class="breadth-metric-heading">
                  <div class="breadth-metric-title">
                    <span>{{ item.symbol }}</span>
                    <h4>{{ item.period }}</h4>
                    <p>{{ item.label }}</p>
                  </div>
                  <div class="breadth-metric-value">
                    <b>{{ latestBreadthClose(item.symbol) }}</b>
                    <span>{{ latestBreadthDate(item.symbol) }}</span>
                  </div>
                </header>
                <div class="breadth-metric-chart">
                  <TradingViewChart
                    v-if="breadthPayload?.series[item.symbol]"
                    :candles="breadthPayload.series[item.symbol].candles"
                    :signals="[]"
                    :show-signals="false"
                    derive-candles-from-close
                    :reset-key="`breadth:${item.symbol}`"
                    :aria-label="`${chartLabels.aria} ${item.symbol}`"
                    :empty-label="chartLabels.empty"
                    :long-signal-label="chartLabels.longSignal"
                    :short-signal-label="chartLabels.shortSignal"
                  />
                  <div v-else class="empty">{{ t("empty.noCandles") }}</div>
                </div>
              </article>
            </div>
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
            <td>
              <div class="admin-expiry-field">
                <input v-model="adminExpiryEdits[user.id]" type="date">
                <button class="secondary" type="button" @click="updateUserExpiry(user)">
                  {{ t("actions.saveExpiration") }}
                </button>
              </div>
            </td>
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
