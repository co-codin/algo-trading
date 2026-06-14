<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { requestJson, toQuery } from "./api";
import TradingViewChart from "./components/TradingViewChart.vue";
import type {
  LiveChartPayload,
  Mode,
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

const routeModes: Record<string, Mode> = {
  "/": "backtest",
  "/backtest": "backtest",
  "/paper": "paper",
  "/live": "live",
  "/chart": "live",
  "/runs": "runs",
  "/history": "runs",
  "/lab": "lab",
};

const modeRoutes: Record<Mode, string> = {
  backtest: "/backtest",
  paper: "/paper",
  live: "/live",
  runs: "/runs",
  lab: "/lab",
};

const tabs: { mode: Mode; label: string }[] = [
  { mode: "backtest", label: "Backtest" },
  { mode: "paper", label: "Paper" },
  { mode: "live", label: "Live" },
  { mode: "runs", label: "Runs" },
  { mode: "lab", label: "Strategy Lab" },
];

const liveSymbolOptions = [
  { value: "BTCUSDT", label: "BTCUSDT" },
  { value: "ETHUSDT", label: "ETHUSDT" },
  { value: "SOLUSDT", label: "SOLUSDT" },
  { value: "BNBUSDT", label: "BNBUSDT" },
  { value: "XRPUSDT", label: "XRPUSDT" },
  { value: "DOGEUSDT", label: "DOGEUSDT" },
  { value: "ADAUSDT", label: "ADAUSDT" },
  { value: "AVAXUSDT", label: "AVAXUSDT" },
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
  stop_loss_pct: "0.03",
  take_profit_pct: "0.06",
  trailing_stop_pct: "0",
  market_data_retries: "2",
  retry_delay: "0.5",
  iterations: "3",
  poll_seconds: "30",
});

const activeMode = ref<Mode>(modeFromLocation());
const strategies = ref<StrategyInfo[]>([]);
const presets = ref<string[]>(["custom", "conservative", "balanced", "aggressive"]);
const symbols = ref<SymbolInfo[]>([]);
const runs = ref<RunCard[]>([]);
const runDetails = ref<RunDetails | null>(null);
const outputRuns = ref<RunCard[]>([]);
const livePayload = ref<LiveChartPayload | null>(null);
const labRows = ref<StrategyLabRow[]>([]);
const status = ref("Ready");
const statusType = ref<StatusType>("");
const liveStatus = ref("Ready");
const liveStatusType = ref<StatusType>("");
const labStatus = ref("Ready");
const labStatusType = ref<StatusType>("");
const liveSymbol = ref("BTCUSDT");
const liveInterval = ref("1m");
const liveLimit = ref<string | number>(180);
const liveRefresh = ref("10");
const showSignals = ref(true);
const showPaper = ref(true);
const labSymbols = ref("BTCUSDT,ETHUSDT,SOLUSDT");
const labStrategies = ref("all");
const labPresets = ref("custom,balanced,aggressive");
let liveTimer = 0;

const strategyName = computed(() => strategyLabel(settings.strategy));
const filteredSignals = computed(() => livePayload.value?.signals ?? []);
const filteredPaperMarkers = computed(() => livePayload.value?.paper_markers ?? []);

watch([liveSymbol, liveInterval, liveLimit], () => {
  if (activeMode.value === "live") {
    refreshLiveChart();
  }
});

onMounted(async () => {
  window.addEventListener("popstate", handlePopState);
  await Promise.all([loadStrategies(), loadRuns()]);
  setMode(modeFromLocation(), false);
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
  if (updateUrl && window.location.pathname !== modeRoutes[mode]) {
    window.history.pushState({ mode }, "", modeRoutes[mode]);
  }
  if (mode === "live") {
    startLivePolling();
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

function setLabStatus(message: string, type: StatusType = "") {
  labStatus.value = message;
  labStatusType.value = type;
}

async function loadStrategies() {
  const payload = await requestJson<StrategyPayload>("/api/strategies");
  strategies.value = payload.strategies;
  presets.value = payload.presets;
}

async function loadSymbols() {
  setStatus("Loading symbols", "busy");
  symbols.value = [];
  try {
    const payload = await requestJson<{ ok: true; symbols: SymbolInfo[] }>(
      `/api/symbols?top=${encodeURIComponent(settings.top)}`,
    );
    symbols.value = payload.symbols;
    setStatus(`Loaded ${payload.symbols.length} symbols`);
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
  setStatus(mode === "paper" ? "Paper session running" : "Backtest running", "busy");
  outputRuns.value = [];
  try {
    const result = await requestJson<{ ok: true; runs: RunCard[] }>(endpoint, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    outputRuns.value = result.runs;
    await loadRuns();
    setStatus("Ready");
  } catch (error) {
    setStatus(errorMessage(error), "error");
  }
}

async function loadLiveChart() {
  setLiveStatus("Loading chart", "busy");
  try {
    const query = toQuery({
      ...settings,
      symbol: liveSymbol.value,
      interval: liveInterval.value,
      limit: liveLimit.value,
    });
    livePayload.value = await requestJson<LiveChartPayload>(`/api/live-chart?${query}`);
    setLiveStatus(`Updated ${new Date().toLocaleTimeString()}`);
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
  setLabStatus("Running strategy lab", "busy");
  labRows.value = [];
  try {
    const payload = await requestJson<StrategyLabPayload>("/api/strategy-lab", {
      method: "POST",
      body: JSON.stringify({
        ...settings,
        symbols: labSymbols.value,
        strategies: labStrategies.value,
        presets: labPresets.value,
      }),
    });
    labRows.value = payload.rows;
    setLabStatus(`Ranked ${payload.rows.length} results`);
  } catch (error) {
    setLabStatus(errorMessage(error), "error");
  }
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
  return strategies.value.find((strategy) => strategy.name === name)?.description ?? name;
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

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
</script>

<template>
  <header class="topbar">
    <div>
      <h1>Algo Trading</h1>
      <p>Vue control panel for read-only backtesting, paper trading, live charts, and strategy ranking.</p>
    </div>
    <div class="safety">Simulated only: no real orders</div>
  </header>

  <nav class="tabs" aria-label="Modes">
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
            <h2>{{ activeMode === "paper" ? "Paper Trading" : "Backtest" }}</h2>
            <p>{{ strategyName }}</p>
          </div>
          <button class="primary" type="submit">
            {{ activeMode === "paper" ? "Run Paper" : "Run Backtest" }}
          </button>
        </div>

        <div class="symbols-row">
          <label>
            <span>{{ activeMode === "paper" ? "Symbol" : "Symbols" }}</span>
            <input v-model="settings.symbols" autocomplete="off">
          </label>
          <label class="small-field">
            <span>Top</span>
            <input v-model="settings.top" type="number" min="1" max="25">
          </label>
          <button class="secondary" type="button" @click="loadSymbols">Load Top</button>
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
            <span>Interval</span>
            <input v-model="settings.interval" autocomplete="off">
          </label>
          <label>
            <span>Candles</span>
            <input v-model="settings.limit" type="number" min="1">
          </label>
          <label>
            <span>Side</span>
            <select v-model="settings.allowed_side">
              <option value="both">Both</option>
              <option value="long-only">Long only</option>
              <option value="short-only">Short only</option>
            </select>
          </label>
          <label>
            <span>Strategy</span>
            <select v-model="settings.strategy">
              <option v-for="strategy in strategies" :key="strategy.name" :value="strategy.name">
                {{ strategy.name }}
              </option>
            </select>
          </label>
          <label>
            <span>Preset</span>
            <select v-model="settings.preset">
              <option v-for="preset in presets" :key="preset" :value="preset">{{ preset }}</option>
            </select>
          </label>
          <label><span>Starting USDT</span><input v-model="settings.starting_balance" type="number" min="1" step="0.01"></label>
          <label><span>Position Fraction</span><input v-model="settings.position_fraction" type="number" min="0.01" max="1" step="0.01"></label>
          <label><span>Fee Rate</span><input v-model="settings.fee_rate" type="number" min="0" step="0.0001"></label>
          <label><span>Slippage</span><input v-model="settings.slippage_rate" type="number" min="0" step="0.0001"></label>
          <label><span>Fast EMA</span><input v-model="settings.fast_ema" type="number" min="1"></label>
          <label><span>Slow EMA</span><input v-model="settings.slow_ema" type="number" min="1"></label>
          <label><span>RSI Period</span><input v-model="settings.rsi_period" type="number" min="1"></label>
          <label><span>RSI Overbought</span><input v-model="settings.rsi_overbought" type="number" min="1" max="100" step="0.1"></label>
          <label><span>RSI Oversold</span><input v-model="settings.rsi_oversold" type="number" min="0" max="99" step="0.1"></label>
          <label><span>RSI Midline</span><input v-model="settings.rsi_midline" type="number" min="0" max="100" step="0.1"></label>
          <label><span>MACD Signal</span><input v-model="settings.macd_signal" type="number" min="1"></label>
          <label><span>Bollinger Period</span><input v-model="settings.bollinger_period" type="number" min="1"></label>
          <label><span>Bollinger Stddev</span><input v-model="settings.bollinger_stddev" type="number" min="0.1" step="0.1"></label>
          <label><span>Donchian Period</span><input v-model="settings.donchian_period" type="number" min="1"></label>
          <label><span>ATR Period</span><input v-model="settings.atr_period" type="number" min="1"></label>
          <label><span>SuperTrend Mult</span><input v-model="settings.supertrend_multiplier" type="number" min="0.1" step="0.1"></label>
          <label><span>VWAP Period</span><input v-model="settings.vwap_period" type="number" min="1"></label>
          <label><span>VWAP Threshold</span><input v-model="settings.vwap_threshold_pct" type="number" min="0" step="0.001"></label>
          <label><span>Stoch RSI Period</span><input v-model="settings.stoch_rsi_period" type="number" min="1"></label>
          <label><span>EMA Ribbon Fast</span><input v-model="settings.ema_ribbon_fast" type="number" min="1"></label>
          <label><span>EMA Ribbon Mid</span><input v-model="settings.ema_ribbon_mid" type="number" min="1"></label>
          <label><span>EMA Ribbon Slow</span><input v-model="settings.ema_ribbon_slow" type="number" min="1"></label>
          <label><span>Momentum Period</span><input v-model="settings.momentum_period" type="number" min="1"></label>
          <label><span>Stop Loss</span><input v-model="settings.stop_loss_pct" type="number" min="0" step="0.001"></label>
          <label><span>Take Profit</span><input v-model="settings.take_profit_pct" type="number" min="0" step="0.001"></label>
          <label><span>Trailing Stop</span><input v-model="settings.trailing_stop_pct" type="number" min="0" step="0.001"></label>
          <label v-if="activeMode === 'backtest'"><span>Retries</span><input v-model="settings.market_data_retries" type="number" min="0"></label>
          <label v-if="activeMode === 'backtest'"><span>Retry Delay</span><input v-model="settings.retry_delay" type="number" min="0" step="0.1"></label>
          <label v-if="activeMode === 'paper'"><span>Iterations</span><input v-model="settings.iterations" type="number" min="1"></label>
          <label v-if="activeMode === 'paper'"><span>Poll Seconds</span><input v-model="settings.poll_seconds" type="number" min="0" step="0.5"></label>
        </div>
      </form>

      <section class="panel output">
        <div class="panel-heading">
          <h2>Output</h2>
          <div class="status" :class="statusType ? `is-${statusType}` : ''">{{ status }}</div>
        </div>
        <div v-if="!outputRuns.length" class="empty">No run output yet</div>
        <article v-for="run in outputRuns" :key="run.path" class="detail-section">
          <h3>{{ run.symbol || "Run" }}</h3>
          <div class="metric-row">
            <div class="metric"><b>Final</b><span>{{ formatNumber(run.summary.final_balance) }}</span></div>
            <div class="metric"><b>Trades</b><span>{{ formatNumber(run.summary.trades) }}</span></div>
            <div class="metric"><b>Return</b><span>{{ formatNumber(run.summary.total_return_pct) }}</span></div>
            <div class="metric"><b>Win Rate</b><span>{{ formatNumber(run.summary.win_rate) }}</span></div>
          </div>
          <p>{{ run.path }}</p>
        </article>
      </section>
    </section>

    <section v-else-if="activeMode === 'live'" class="panel live-panel">
      <div class="panel-heading">
        <h2>Live Market</h2>
        <div class="status" :class="liveStatusType ? `is-${liveStatusType}` : ''">{{ liveStatus }}</div>
      </div>
      <div class="live-controls">
        <label>
          <span>Symbol</span>
          <select v-model="liveSymbol">
            <option
              v-for="option in liveSymbolOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
        </label>
        <label>
          <span>Interval</span>
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
          <span>Candles</span>
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
        <label><span>Refresh Sec</span><input v-model="liveRefresh" type="number" min="2" max="300"></label>
        <label class="toggle-row"><input v-model="showSignals" type="checkbox"><span>Strategy markers</span></label>
        <label class="toggle-row"><input v-model="showPaper" type="checkbox"><span>Paper markers</span></label>
        <button class="primary" type="button" @click="refreshLiveChart">Refresh Chart</button>
      </div>
      <div class="chart-shell">
        <div class="chart-legend">
          <span><i class="legend-dot long"></i>Long signal</span>
          <span><i class="legend-dot short"></i>Short signal</span>
          <span><i class="legend-dot paper-entry"></i>Paper entry</span>
          <span><i class="legend-dot paper-exit"></i>Paper exit</span>
          <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView</a>
        </div>
        <TradingViewChart
          v-if="livePayload"
          :candles="livePayload.candles"
          :signals="filteredSignals"
          :paper-markers="filteredPaperMarkers"
          :show-signals="showSignals"
          :show-paper="showPaper"
        />
        <div v-else class="empty">Load a chart to start</div>
      </div>
    </section>

    <section v-else-if="activeMode === 'runs'" class="panel runs-panel">
      <div class="panel-heading">
        <h2>Runs</h2>
        <button class="secondary" type="button" @click="loadRuns">Refresh</button>
      </div>
      <div class="runs-layout">
        <div class="runs-list">
          <div v-if="!runs.length" class="empty">No local runs yet</div>
          <div v-for="run in runs" :key="run.path" class="run-row">
            <div>
              <h3>{{ run.symbol || "Run" }} · {{ run.mode }}</h3>
              <p>{{ run.timestamp }} · Final {{ formatNumber(run.final_balance) }}</p>
            </div>
            <button class="secondary" type="button" @click="loadRunDetails(run.path)">Open</button>
          </div>
        </div>
        <div class="run-detail">
          <div v-if="!runDetails" class="empty">Select a run</div>
          <template v-else>
            <div class="detail-section">
              <h3>{{ runDetails.summary.symbol || runDetails.path }}</h3>
              <div class="metric-row">
                <div class="metric"><b>Final</b><span>{{ formatNumber(runDetails.summary.final_balance) }}</span></div>
                <div class="metric"><b>Trades</b><span>{{ formatNumber(runDetails.summary.trades) }}</span></div>
                <div class="metric"><b>Max DD</b><span>{{ formatNumber(runDetails.summary.max_drawdown_pct) }}</span></div>
                <div class="metric"><b>Profit Factor</b><span>{{ formatNumber(runDetails.summary.profit_factor) }}</span></div>
              </div>
            </div>
            <div class="detail-section">
              <h3>Recent Trades</h3>
              <table>
                <thead><tr><th>Side</th><th>Entry</th><th>Exit</th><th>PNL</th></tr></thead>
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
            <h2>Strategy Lab</h2>
            <p>Rank strategies by simulated return and drawdown.</p>
          </div>
          <button class="primary" type="submit">Run Lab</button>
        </div>
        <div class="field-grid">
          <label><span>Symbols</span><input v-model="labSymbols" autocomplete="off"></label>
          <label><span>Strategies</span><input v-model="labStrategies" autocomplete="off"></label>
          <label><span>Presets</span><input v-model="labPresets" autocomplete="off"></label>
          <label><span>Interval</span><input v-model="settings.interval" autocomplete="off"></label>
          <label><span>Candles</span><input v-model="settings.limit" type="number" min="30"></label>
          <label><span>Side</span>
            <select v-model="settings.allowed_side">
              <option value="both">Both</option>
              <option value="long-only">Long only</option>
              <option value="short-only">Short only</option>
            </select>
          </label>
        </div>
      </form>
      <section class="panel output">
        <div class="panel-heading">
          <h2>Ranking</h2>
          <div class="status" :class="labStatusType ? `is-${labStatusType}` : ''">{{ labStatus }}</div>
        </div>
        <div v-if="!labRows.length" class="empty">Run the lab to rank strategy/preset combinations</div>
        <table v-else>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Symbol</th>
              <th>Strategy</th>
              <th>Preset</th>
              <th>Return</th>
              <th>Max DD</th>
              <th>Trades</th>
              <th>PF</th>
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
            </tr>
          </tbody>
        </table>
      </section>
    </section>
  </main>
</template>
