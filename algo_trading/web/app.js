const state = {
  mode: "backtest",
  liveTimer: null,
};

const form = document.querySelector("#run-form");
const statusEl = document.querySelector("#status");
const resultEl = document.querySelector("#result");
const symbolListEl = document.querySelector("#symbol-list");
const runsListEl = document.querySelector("#runs-list");
const runDetailEl = document.querySelector("#run-detail");
const liveStatusEl = document.querySelector("#live-status");
const liveChartEl = document.querySelector("#live-chart");

function setStatus(message, type = "") {
  statusEl.textContent = message;
  statusEl.className = `status${type ? ` is-${type}` : ""}`;
}

function setLiveStatus(message, type = "") {
  liveStatusEl.textContent = message;
  liveStatusEl.className = `status${type ? ` is-${type}` : ""}`;
}

function setMode(mode) {
  stopLivePolling();
  state.mode = mode;
  document.body.dataset.mode = mode;
  document.querySelectorAll("[data-mode-tab]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.modeTab === mode);
  });

  const formTitle = document.querySelector("#form-title");
  const runButton = document.querySelector("#run-button");
  const symbolLabel = document.querySelector("#symbol-label");
  const symbolInput = document.querySelector("#symbols-input");

  if (mode === "paper") {
    formTitle.textContent = "Paper";
    runButton.textContent = "Run Paper";
    symbolLabel.textContent = "Symbol";
    symbolInput.placeholder = "BTCUSDT";
    symbolInput.value = symbolInput.value.includes(",") ? "BTCUSDT" : symbolInput.value;
  } else if (mode === "runs") {
    loadRuns();
  } else if (mode === "live") {
    startLivePolling();
  } else {
    formTitle.textContent = "Backtest";
    runButton.textContent = "Run Backtest";
    symbolLabel.textContent = "Symbols";
    symbolInput.placeholder = "BTCUSDT,ETHUSDT or top 5";
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

function serializeForm() {
  const data = Object.fromEntries(new FormData(form).entries());
  if (state.mode === "paper") {
    data.symbol = data.symbols || "BTCUSDT";
    delete data.symbols;
  }
  return data;
}

async function loadSymbols() {
  setStatus("Loading symbols", "busy");
  symbolListEl.innerHTML = "";
  try {
    const top = document.querySelector("#top-input").value || "10";
    const payload = await requestJson(`/api/symbols?top=${encodeURIComponent(top)}`);
    symbolListEl.innerHTML = payload.symbols
      .map(
        (item) =>
          `<button class="symbol-chip" type="button" data-symbol="${item.symbol}">${item.symbol}</button>`,
      )
      .join("");
    setStatus(`Loaded ${payload.symbols.length} symbols`);
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function runCurrentMode(event) {
  event.preventDefault();
  const endpoint = state.mode === "paper" ? "/api/paper" : "/api/backtest";
  setStatus(state.mode === "paper" ? "Paper session running" : "Backtest running", "busy");
  resultEl.innerHTML = "";
  try {
    const payload = await requestJson(endpoint, {
      method: "POST",
      body: JSON.stringify(serializeForm()),
    });
    renderRunPayload(payload);
    await loadRuns();
    setStatus("Ready");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function loadRuns() {
  try {
    const payload = await requestJson("/api/runs");
    renderRuns(payload.runs);
  } catch (error) {
    runsListEl.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

async function loadLiveChart() {
  setLiveStatus("Loading chart", "busy");
  try {
    const payload = await requestJson(`/api/live-chart?${liveQueryString()}`);
    renderLiveChart(payload);
    setLiveStatus(`Updated ${new Date().toLocaleTimeString()}`);
  } catch (error) {
    setLiveStatus(error.message, "error");
  }
}

function startLivePolling() {
  loadLiveChart();
  const seconds = Math.max(2, Number(document.querySelector("#live-refresh").value || 10));
  state.liveTimer = window.setInterval(loadLiveChart, seconds * 1000);
}

function stopLivePolling() {
  if (state.liveTimer) {
    window.clearInterval(state.liveTimer);
    state.liveTimer = null;
  }
}

function liveQueryString() {
  const formData = new FormData(form);
  const params = new URLSearchParams();
  const fields = [
    "allowed_side",
    "strategy",
    "preset",
    "fast_ema",
    "slow_ema",
    "rsi_period",
    "rsi_overbought",
    "rsi_oversold",
    "rsi_midline",
    "macd_signal",
    "bollinger_period",
    "bollinger_stddev",
    "donchian_period",
    "stop_loss_pct",
    "take_profit_pct",
    "trailing_stop_pct",
  ];
  params.set("symbol", document.querySelector("#live-symbol").value || "BTCUSDT");
  params.set("interval", document.querySelector("#live-interval").value || "1m");
  params.set("limit", document.querySelector("#live-limit").value || "180");
  fields.forEach((field) => {
    const value = formData.get(field);
    if (value !== null && value !== "") {
      params.set(field, value);
    }
  });
  return params.toString();
}

async function loadRunDetails(path) {
  runDetailEl.innerHTML = `<div class="empty">Loading run</div>`;
  try {
    const payload = await requestJson(`/api/run?path=${encodeURIComponent(path)}`);
    renderRunDetails(payload);
  } catch (error) {
    runDetailEl.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

function renderLiveChart(payload) {
  const candles = payload.candles || [];
  if (!candles.length) {
    liveChartEl.innerHTML = `<div class="empty">No candles returned</div>`;
    return;
  }

  const showSignals = document.querySelector("#show-signals").checked;
  const showPaper = document.querySelector("#show-paper").checked;
  const signals = showSignals ? payload.signals || [] : [];
  const paperMarkers = showPaper ? payload.paper_markers || [] : [];
  liveChartEl.innerHTML = drawChart(candles, signals, paperMarkers, payload);
}

function drawChart(candles, signals, paperMarkers, payload) {
  const width = 1000;
  const height = 420;
  const pad = { left: 58, right: 24, top: 24, bottom: 38 };
  const times = candles.map((candle) => Number(candle.time));
  const prices = [
    ...candles.flatMap((candle) => [Number(candle.high), Number(candle.low), Number(candle.close)]),
    ...signals.map((marker) => Number(marker.price)),
    ...paperMarkers.map((marker) => Number(marker.price)),
  ].filter((value) => Number.isFinite(value));
  const minTime = Math.min(...times);
  const maxTime = Math.max(...times);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const padding = Math.max((maxPrice - minPrice) * 0.08, maxPrice * 0.001);
  const low = minPrice - padding;
  const high = maxPrice + padding;
  const x = (time) => {
    if (maxTime === minTime) {
      return width / 2;
    }
    return pad.left + ((Number(time) - minTime) / (maxTime - minTime)) * (width - pad.left - pad.right);
  };
  const y = (price) => pad.top + ((high - Number(price)) / (high - low)) * (height - pad.top - pad.bottom);
  const points = candles.map((candle) => `${x(candle.time).toFixed(2)},${y(candle.close).toFixed(2)}`).join(" ");
  const grid = [0, 1, 2, 3, 4]
    .map((index) => {
      const yy = pad.top + (index / 4) * (height - pad.top - pad.bottom);
      const price = high - (index / 4) * (high - low);
      return `
        <line class="chart-grid" x1="${pad.left}" y1="${yy}" x2="${width - pad.right}" y2="${yy}"></line>
        <text class="chart-axis" x="8" y="${yy + 4}">${formatNumber(price)}</text>
      `;
    })
    .join("");
  const markerSvg = [...signals, ...paperMarkers]
    .map((marker) => markerShape(marker, x(marker.time), y(marker.price)))
    .join("");

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(payload.symbol)} live price chart">
      <rect x="0" y="0" width="${width}" height="${height}" fill="#fbfcfc"></rect>
      ${grid}
      <polyline class="price-line" points="${points}"></polyline>
      ${markerSvg}
      <text class="chart-axis" x="${pad.left}" y="${height - 10}">${escapeHtml(formatTime(candles[0].time))}</text>
      <text class="chart-axis" x="${width - 220}" y="${height - 10}">${escapeHtml(formatTime(candles[candles.length - 1].time))}</text>
    </svg>
  `;
}

function markerShape(marker, x, y) {
  const label = escapeHtml(marker.reason || marker.type);
  if (marker.type === "long_signal") {
    return `<path d="M ${x} ${y - 10} L ${x - 7} ${y + 6} L ${x + 7} ${y + 6} Z" fill="#2f8f5b"><title>${label}</title></path>`;
  }
  if (marker.type === "short_signal") {
    return `<path d="M ${x} ${y + 10} L ${x - 7} ${y - 6} L ${x + 7} ${y - 6} Z" fill="#b35c2e"><title>${label}</title></path>`;
  }
  if (marker.type.startsWith("paper_entry")) {
    return `<rect x="${x - 6}" y="${y - 6}" width="12" height="12" fill="#246aa8" transform="rotate(45 ${x} ${y})"><title>${label}</title></rect>`;
  }
  return `<circle cx="${x}" cy="${y}" r="6" fill="#6d5cae"><title>${label}</title></circle>`;
}

function renderRunPayload(payload) {
  if (!payload.runs.length) {
    resultEl.innerHTML = `<div class="empty">No runs returned</div>`;
    return;
  }
  resultEl.innerHTML = payload.runs.map(renderRunCard).join("");
}

function renderRunCard(run) {
  const summary = run.summary || {};
  return `
    <article class="detail-section">
      <h3>${escapeHtml(run.symbol || "Run")}</h3>
      <div class="metric-row">
        ${metric("Final", formatNumber(summary.final_balance))}
        ${metric("Trades", summary.trades ?? 0)}
        ${metric("Return", formatNumber(summary.total_return_pct))}
        ${metric("Win Rate", formatNumber(summary.win_rate))}
      </div>
      <p>${escapeHtml(run.path || "")}</p>
    </article>
  `;
}

function renderRuns(runs) {
  if (!runs.length) {
    runsListEl.innerHTML = `<div class="empty">No local runs yet</div>`;
    return;
  }
  runsListEl.innerHTML = runs
    .map(
      (run) => `
        <div class="run-row">
          <div>
            <h3>${escapeHtml(run.symbol || "Run")} · ${escapeHtml(run.mode)}</h3>
            <p>${escapeHtml(run.timestamp)} · Final ${formatNumber(run.final_balance)}</p>
          </div>
          <button class="secondary" type="button" data-run-path="${escapeHtml(run.path)}">Open</button>
        </div>
      `,
    )
    .join("");
}

function renderRunDetails(payload) {
  const summary = payload.summary || {};
  runDetailEl.innerHTML = `
    <div class="detail-section">
      <h3>${escapeHtml(summary.symbol || payload.path)}</h3>
      <div class="metric-row">
        ${metric("Final", formatNumber(summary.final_balance))}
        ${metric("Trades", summary.trades ?? 0)}
        ${metric("Max DD", formatNumber(summary.max_drawdown_pct))}
        ${metric("Profit Factor", formatNumber(summary.profit_factor))}
      </div>
    </div>
    <div class="detail-section">
      <h3>Trades</h3>
      ${renderTable(payload.trades, ["side", "entry_price", "exit_price", "realized_pnl"])}
    </div>
    <div class="detail-section">
      <h3>Equity</h3>
      ${renderTable(payload.equity.slice(-12), ["time", "equity", "cash", "position_side"])}
    </div>
  `;
}

function renderTable(rows, columns) {
  if (!rows || !rows.length) {
    return `<div class="empty">No rows</div>`;
  }
  return `
    <table>
      <thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows
          .map(
            (row) =>
              `<tr>${columns.map((column) => `<td>${escapeHtml(row[column] ?? "")}</td>`).join("")}</tr>`,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function metric(label, value) {
  return `<div class="metric"><b>${escapeHtml(label)}</b><span>${escapeHtml(value)}</span></div>`;
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") {
    return "0";
  }
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return String(value);
  }
  return number.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function formatTime(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return String(value);
  }
  return new Date(number).toLocaleString();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

document.querySelectorAll("[data-mode-tab]").forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.modeTab));
});

document.querySelector("#load-symbols").addEventListener("click", loadSymbols);
document.querySelector("#refresh-runs").addEventListener("click", loadRuns);
document.querySelector("#refresh-live").addEventListener("click", () => {
  if (state.mode === "live") {
    stopLivePolling();
    startLivePolling();
  } else {
    loadLiveChart();
  }
});
form.addEventListener("submit", runCurrentMode);

symbolListEl.addEventListener("click", (event) => {
  const target = event.target.closest("[data-symbol]");
  if (!target) {
    return;
  }
  const input = document.querySelector("#symbols-input");
  if (state.mode === "paper") {
    input.value = target.dataset.symbol;
    return;
  }
  const values = input.value
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  if (!values.includes(target.dataset.symbol)) {
    values.push(target.dataset.symbol);
  }
  input.value = values.join(",");
});

runsListEl.addEventListener("click", (event) => {
  const target = event.target.closest("[data-run-path]");
  if (target) {
    loadRunDetails(target.dataset.runPath);
  }
});

setMode("backtest");
loadRuns();
