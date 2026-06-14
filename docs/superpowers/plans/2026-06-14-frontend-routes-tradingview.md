# Frontend Routes TradingView Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add direct frontend URLs and render the live/chart view with TradingView Lightweight Charts plus long/short strategy markers.

**Architecture:** Keep the Python UI server explicit: known frontend routes serve `index.html`, static and API routes stay exact, unknown paths stay 404. Keep the browser app as one static module with a small route map and a chart wrapper that converts the existing `/api/live-chart` payload into TradingView candle and marker data.

**Tech Stack:** Python `http.server`, `unittest`, static HTML/CSS/JavaScript, TradingView Lightweight Charts browser build.

---

## File Structure

- `algo_trading/ui.py`: owns the frontend route allowlist and HTTP serving behavior.
- `tests/test_ui.py`: covers route classification and keeps API paths out of the frontend allowlist.
- `algo_trading/web/app.js`: owns tab mode state, browser history, live chart loading, and marker conversion.
- `algo_trading/web/index.html`: loads TradingView Lightweight Charts before the local app script.
- `algo_trading/web/styles.css`: sizes the TradingView chart container and removes obsolete SVG-only styling.
- `README.md`: documents direct UI URLs and TradingView chart behavior.

### Task 1: Route Allowlist

**Files:**
- Modify: `tests/test_ui.py`
- Modify: `algo_trading/ui.py`

- [ ] **Step 1: Write the failing route allowlist test**

Add `is_frontend_route` to the imports in `tests/test_ui.py`, then add:

```python
    def test_frontend_routes_allow_direct_view_urls(self):
        self.assertTrue(is_frontend_route("/"))
        self.assertTrue(is_frontend_route("/backtest"))
        self.assertTrue(is_frontend_route("/paper"))
        self.assertTrue(is_frontend_route("/live"))
        self.assertTrue(is_frontend_route("/chart"))
        self.assertTrue(is_frontend_route("/runs"))
        self.assertTrue(is_frontend_route("/history"))

    def test_frontend_routes_do_not_capture_api_or_unknown_paths(self):
        self.assertFalse(is_frontend_route("/api/runs"))
        self.assertFalse(is_frontend_route("/styles.css"))
        self.assertFalse(is_frontend_route("/unknown"))
```

- [ ] **Step 2: Run the route tests and verify RED**

Run: `python3 -m unittest tests.test_ui.UiTests.test_frontend_routes_allow_direct_view_urls tests.test_ui.UiTests.test_frontend_routes_do_not_capture_api_or_unknown_paths -v`

Expected: fail with an import error for `is_frontend_route`.

- [ ] **Step 3: Implement the minimal route allowlist**

In `algo_trading/ui.py`, add:

```python
FRONTEND_ROUTES = frozenset(
    {
        "",
        "/",
        "/index.html",
        "/backtest",
        "/paper",
        "/live",
        "/chart",
        "/runs",
        "/history",
    }
)


def is_frontend_route(path: str) -> bool:
    return path in FRONTEND_ROUTES
```

Change `_handle_get` to call `is_frontend_route(parsed.path)` before static/API route checks and serve `index.html` for those paths.

- [ ] **Step 4: Run the route tests and verify GREEN**

Run: `python3 -m unittest tests.test_ui.UiTests.test_frontend_routes_allow_direct_view_urls tests.test_ui.UiTests.test_frontend_routes_do_not_capture_api_or_unknown_paths -v`

Expected: both tests pass.

### Task 2: Browser Route State

**Files:**
- Modify: `algo_trading/web/app.js`

- [ ] **Step 1: Add route maps and history-aware mode switching**

Add:

```javascript
const ROUTE_MODES = {
  "/": "backtest",
  "/backtest": "backtest",
  "/paper": "paper",
  "/live": "live",
  "/chart": "live",
  "/runs": "runs",
  "/history": "runs",
};

const MODE_ROUTES = {
  backtest: "/backtest",
  paper: "/paper",
  live: "/live",
  runs: "/runs",
};
```

Change `setMode(mode)` to accept `{ updateUrl = true } = {}` and push the canonical route when `updateUrl` is true. Add `modeFromLocation()` and a `popstate` listener. Initialize with `setMode(modeFromLocation(), { updateUrl: false })`.

- [ ] **Step 2: Verify JavaScript syntax**

Run: `node --check algo_trading/web/app.js`

Expected: no syntax errors.

### Task 3: TradingView Live Chart

**Files:**
- Modify: `algo_trading/web/index.html`
- Modify: `algo_trading/web/app.js`
- Modify: `algo_trading/web/styles.css`

- [ ] **Step 1: Load the TradingView Lightweight Charts browser build**

Add before `/app.js`:

```html
    <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
```

- [ ] **Step 2: Replace SVG rendering with a chart lifecycle**

Add chart state fields:

```javascript
  liveChart: null,
  candleSeries: null,
```

Replace `drawChart` and SVG marker helpers with functions that:

- Check `window.LightweightCharts`.
- Create the chart once inside `#live-chart`.
- Map candle times from milliseconds to seconds.
- Call `setData` with candlestick data.
- Call `setMarkers` with long, short, paper-entry, and paper-exit markers.
- Resize with a `ResizeObserver` when available.

- [ ] **Step 3: Verify JavaScript syntax**

Run: `node --check algo_trading/web/app.js`

Expected: no syntax errors.

### Task 4: Docs And End-To-End Checks

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document routes and chart behavior**

Add a short UI URL list and note that the live view uses TradingView Lightweight Charts loaded from the public CDN.

- [ ] **Step 2: Run local checks**

Run: `make check`

Expected: all unit tests, typecheck, compile, and JS syntax checks pass.

- [ ] **Step 3: Smoke direct URLs**

Start the UI on port 8765, then run:

```bash
curl -fsS http://127.0.0.1:8765/backtest >/dev/null
curl -fsS http://127.0.0.1:8765/paper >/dev/null
curl -fsS http://127.0.0.1:8765/live >/dev/null
curl -fsS http://127.0.0.1:8765/chart >/dev/null
curl -fsS http://127.0.0.1:8765/runs >/dev/null
curl -fsS http://127.0.0.1:8765/api/runs >/dev/null
```

Expected: every command exits 0.

- [ ] **Step 4: Run Docker smoke**

Run: `make docker-smoke SMOKE_PORT=8766`

Expected: Docker image builds and the container smoke check passes.

## Self-Review

- Spec coverage: direct routes, strict unknown paths, TradingView chart, markers, error handling, README, and validation are covered.
- Placeholder scan: no placeholder work remains.
- Type consistency: route helper and JavaScript state names are defined before use.
