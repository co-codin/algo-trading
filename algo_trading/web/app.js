const state = {
  mode: "backtest",
};

const form = document.querySelector("#run-form");
const statusEl = document.querySelector("#status");
const resultEl = document.querySelector("#result");
const symbolListEl = document.querySelector("#symbol-list");
const runsListEl = document.querySelector("#runs-list");
const runDetailEl = document.querySelector("#run-detail");

function setStatus(message, type = "") {
  statusEl.textContent = message;
  statusEl.className = `status${type ? ` is-${type}` : ""}`;
}

function setMode(mode) {
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

async function loadRunDetails(path) {
  runDetailEl.innerHTML = `<div class="empty">Loading run</div>`;
  try {
    const payload = await requestJson(`/api/run?path=${encodeURIComponent(path)}`);
    renderRunDetails(payload);
  } catch (error) {
    runDetailEl.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
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
