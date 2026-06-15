# Strategy Lab Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add walk-forward validation, benchmark rows, richer metrics, and CSV export to the strategy lab.

**Architecture:** Keep simulator accounting in `algo_trading/simulator.py`. Keep lab orchestration in `algo_trading/ui.py`, adding pure helpers for walk-forward row enrichment, benchmarks, and CSV formatting so tests can call them directly.

**Tech Stack:** Python dataclasses/enums, `unittest`, existing HTTP server, Vue 3/Vite frontend, no new dependencies.

---

### Task 1: Rich Backtest Metrics

**Files:**
- Modify: `tests/test_simulator.py`
- Modify: `algo_trading/simulator.py`

- [ ] **Step 1: Write failing simulator metric tests**

Add assertions that a normal backtest summary includes `sharpe_ratio`, `sortino_ratio`, `max_drawdown_duration`, `average_trade_duration`, `exposure_pct`, and `worst_trade`.

- [ ] **Step 2: Run the simulator tests**

Run: `python3 -m unittest tests.test_simulator -v`
Expected: FAIL because the summary does not include the new metrics.

- [ ] **Step 3: Implement metrics from existing trades and equity**

Extend `_summary()` in `algo_trading/simulator.py` with pure helper functions for period returns, Sharpe, Sortino, drawdown duration, average trade duration, exposure, and worst trade.

- [ ] **Step 4: Run the simulator tests again**

Run: `python3 -m unittest tests.test_simulator -v`
Expected: PASS.

### Task 2: Benchmarks and Walk-Forward Rows

**Files:**
- Modify: `tests/test_ui.py`
- Modify: `algo_trading/ui.py`

- [ ] **Step 1: Write failing strategy lab tests**

Add tests that `strategy_lab_payload()` returns buy-and-hold benchmark rows and walk-forward fields when `walk_forward_windows` is greater than zero.

- [ ] **Step 2: Run the UI tests**

Run: `python3 -m unittest tests.test_ui -v`
Expected: FAIL because benchmark rows and walk-forward fields are missing.

- [ ] **Step 3: Implement helper functions**

Add `_benchmark_row()`, `_walk_forward_summaries()`, `_windowed_candles()`, and `_enrich_row_with_walk_forward()` in `algo_trading/ui.py`.

- [ ] **Step 4: Wire helpers into `strategy_lab_payload()`**

Append benchmark rows and enrich strategy rows with walk-forward aggregate fields. Preserve existing ranking behavior.

- [ ] **Step 5: Run the UI tests again**

Run: `python3 -m unittest tests.test_ui -v`
Expected: PASS.

### Task 3: CSV Export

**Files:**
- Modify: `tests/test_ui.py`
- Modify: `algo_trading/ui.py`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/types.ts`

- [ ] **Step 1: Write failing CSV tests**

Add a test for `strategy_lab_csv(rows)` that asserts headers and rows are escaped with Python `csv`.

- [ ] **Step 2: Run the UI tests**

Run: `python3 -m unittest tests.test_ui -v`
Expected: FAIL because the CSV helper does not exist.

- [ ] **Step 3: Implement CSV helper**

Add `strategy_lab_csv(rows)` using `csv.DictWriter` and `io.StringIO`.

- [ ] **Step 4: Add frontend export controls**

Add a CSV export button that serializes current `labRows` in the browser and downloads `strategy-lab.csv`.

- [ ] **Step 5: Run UI and frontend checks**

Run: `python3 -m unittest tests.test_ui -v`
Run: `npm run frontend:check`
Expected: PASS.

### Task 4: Documentation, Verification, Push, PR

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

Document walk-forward validation, benchmark rows, richer metrics, and CSV export.

- [ ] **Step 2: Run full verification**

Run: `make check`
Expected: PASS.

- [ ] **Step 3: Commit, push, and open draft PR**

Commit with Lore trailers, push `codex/strategy-lab-hardening`, and open a draft PR against `main`.
