# Market Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a MOEX/FUTOI-centered intelligence layer with historical positioning, unusual activity, chart events, browser-visible strategy signals, Russian daily reports, and persisted user watchlists/workspaces.

**Architecture:** Add a pure backend intelligence module that derives reusable events from candles, FUTOI, AlgoPack, and breadth data. Persist user workspaces/watchlists through a dedicated store, expose active-user APIs, and keep existing chart pages as the primary UI surfaces.

**Tech Stack:** Python/FastAPI, existing historical Postgres/in-memory stores, Vue 3/TypeScript/Vite frontend, pytest/unittest.

---

### Task 1: Market Intelligence Events

**Files:**
- Create: `algo_trading/market_intelligence.py`
- Test: `tests/test_market_intelligence.py`
- Modify: `algo_trading/ui.py`

- [ ] **Step 1: Write failing tests**

Create tests proving FUTOI snapshots produce net daily/weekly changes, unusual activity events, volume spike events, breadth confirmation events, and public event payloads:

```bash
pytest tests/test_market_intelligence.py -q
```

Expected: FAIL because `algo_trading.market_intelligence` does not exist.

- [ ] **Step 2: Implement pure event builders**

Add dataclasses `MarketEvent`, `FutoiPositionSnapshot`, `FutoiActivitySummary`, plus builders:
- `build_futoi_position_dashboard(records, instruments)`
- `build_unusual_futoi_events(records)`
- `build_volume_spike_events(candles, market, symbol, interval)`
- `build_breadth_confirmation_events(bars_by_symbol)`
- `public_market_event(event)`

- [ ] **Step 3: Add events to live chart payload**

In `algo_trading/ui.py`, include `events` in `live_chart_payload`, derived from volume spikes and AlgoPack/MegaAlerts records. Preserve existing `strategy: None` behavior.

- [ ] **Step 4: Run focused tests**

```bash
pytest tests/test_market_intelligence.py tests/test_ui.py::UiTests::test_live_chart_payload_adds_algopack_indicators_for_russian_stocks -q
```

Expected: PASS.

### Task 2: FUTOI Dashboard API

**Files:**
- Modify: `algo_trading/web_app.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/i18n.ts`
- Test: `tests/test_web_app.py`
- Test: `tests/test_ui.py`

- [ ] **Step 1: Write failing API test**

Add a test that `/api/futoi` returns `dashboard` with `snapshots`, `summary`, and `events` for the selected ticker.

```bash
pytest tests/test_web_app.py::WebAppTests::test_active_user_can_read_futoi_dashboard_metrics -q
```

Expected: FAIL because the payload lacks `dashboard`.

- [ ] **Step 2: Wire dashboard builder**

In `/api/futoi`, build dashboard data from `chart_records` and instruments, returning:
- `dashboard.snapshots`
- `dashboard.summary`
- `dashboard.events`

- [ ] **Step 3: Wire frontend FUTOI cards/feed**

Add compact FUTOI metrics for daily/weekly net change, gross open interest, long/short balance, and unusual activity feed.

- [ ] **Step 4: Run focused tests**

```bash
pytest tests/test_web_app.py::WebAppTests::test_active_user_can_read_futoi_dashboard_metrics tests/test_ui.py::UiTests::test_frontend_exposes_futoi_positioning_dashboard -q
```

Expected: PASS.

### Task 3: Retired Telegram Alert Engine

Telegram delivery has been retired from this project. Do not recreate `algo_trading/alerts.py`, `tests/test_alerts.py`, or `/api/alerts/telegram` routes from this historical plan. Strategy and market events remain available through chart/API payloads and browser-side notifications.

- [x] **Step 1: Remove server-side Telegram alert surface**

Delete the server-side Telegram alert store, delivery helpers, and tests.

```bash
pytest tests/test_web_app.py::WebAppTests::test_removed_workflow_apis_return_404 -q
```

Expected: PASS.

- [x] **Step 2: Preserve chart/API event payloads**

Keep `rsi_alert_signal` and market `events` in chart/API payloads for browser-side handling.

- [x] **Step 3: Update frontend copy and tests**

Ensure frontend copy no longer advertises Telegram delivery and tests assert the Telegram alert UI/API is absent.

- [x] **Step 4: Run focused tests**

```bash
pytest tests/test_web_app.py::WebAppTests::test_removed_workflow_apis_return_404 tests/test_ui.py -k telegram -q
```

Expected: PASS.

### Task 4: Russian Daily Market Report

**Files:**
- Create: `algo_trading/market_reports.py`
- Modify: `algo_trading/web_app.py`
- Modify: `algo_trading/jobs.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/i18n.ts`
- Test: `tests/test_market_reports.py`
- Test: `tests/test_web_app.py`
- Test: `tests/test_ui.py`

- [ ] **Step 1: Write failing report tests**

Test that a deterministic Russian report includes changed positioning, symbols triggered, and breadth/volume context.

```bash
pytest tests/test_market_reports.py -q
```

Expected: FAIL because `algo_trading.market_reports` does not exist.

- [ ] **Step 2: Implement report generation**

Add `DailyMarketReport`, `build_daily_market_report()`, and `public_daily_market_report()`. Generate Russian text from stored FUTOI, AlgoPack, breadth, and candles.

- [ ] **Step 3: Expose report API and route**

Add `/api/reports/daily` for active users, cacheable like FUTOI. Add `/reports` frontend route/tab and Russian report panel.

- [ ] **Step 4: Run focused tests**

```bash
pytest tests/test_market_reports.py tests/test_web_app.py::WebAppTests::test_active_user_can_read_daily_market_report tests/test_ui.py::UiTests::test_frontend_exposes_daily_market_report_tab -q
```

Expected: PASS.

### Task 5: Persisted Watchlists And Workspaces

**Files:**
- Create: `algo_trading/workspaces.py`
- Modify: `algo_trading/web_app.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.vue`
- Test: `tests/test_workspaces.py`
- Test: `tests/test_web_app.py`
- Test: `tests/test_ui.py`

- [ ] **Step 1: Write failing store/API tests**

Test active-user CRUD for watchlists and workspaces, with inactive users blocked and user isolation preserved.

```bash
pytest tests/test_workspaces.py tests/test_web_app.py::WebAppTests::test_active_user_can_manage_watchlists_and_workspaces -q
```

Expected: FAIL because workspace storage does not exist.

- [ ] **Step 2: Implement in-memory and Postgres store**

Add tables:
- `user_watchlists`
- `user_watchlist_items`
- `user_workspaces`

Support markets `moex`, `us_etfs`, `crypto`, `hk_stocks` through normalized labels while storing exact symbols.

- [ ] **Step 3: Wire frontend fallback**

Load DB workspaces/watchlists after login, save to API first, and keep localStorage fallback on API failure.

- [ ] **Step 4: Run focused tests**

```bash
pytest tests/test_workspaces.py tests/test_web_app.py::WebAppTests::test_active_user_can_manage_watchlists_and_workspaces tests/test_ui.py::UiTests::test_frontend_uses_persisted_workspaces_and_watchlists -q
```

Expected: PASS.

### Task 6: Full Verification

**Files:**
- Review all modified files.

- [ ] **Step 1: Run backend test suite**

```bash
pytest -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend checks/build**

```bash
npm --prefix frontend run build
```

Expected: PASS.

- [ ] **Step 3: Inspect git diff**

```bash
git diff --stat
git status -sb
```

Expected: Only intentional source, test, and plan changes.
