# Combined Signals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a configurable strategy-combination signal plus an obvious missing SMA crossover baseline strategy.

**Architecture:** Extend the existing `StrategyName` enum and `_STRATEGIES` registry. Reuse existing strategy entry/exit methods inside a `combined-signals` strategy, configured by comma-separated member names, confirmation counts, and a lookback window. Surface the new config fields through CLI and API payload parsing, then add a dedicated `/combos` Vue page for configuring and charting combination signals without crowding the `/live` page.

**Tech Stack:** Python dataclasses/enums/unittest, existing strategy engine, existing Vue settings form, Vite build.

---

### Task 1: Strategy Behavior Tests

**Files:**
- Modify: `tests/test_strategy.py`
- Modify: `tests/test_simulator.py`

- [x] **Step 1: Write failing strategy tests**

Add tests asserting:
- `list_strategy_names()` includes `sma-crossover` and `combined-signals`.
- `sma-crossover` enters long on fast SMA crossing above slow SMA.
- `combined-signals` enters long when configured members produce enough long confirmations.
- `combined-signals` does not vote for itself when the member list includes `combined-signals`.
- `combined-signals` exits a long when enough member exits or opposite entries confirm.

- [x] **Step 2: Verify red**

Run:

```bash
python -m pytest tests/test_strategy.py -q
python -m pytest tests/test_simulator.py -q
```

Expected: failures for missing enum values/config fields/strategy registry entries.

- [x] **Step 3: Implement strategy behavior**

Modify:
- `algo_trading/models.py`: add `SMA_CROSSOVER`, `COMBINED_SIGNALS`, `combo_strategies`, `combo_entry_confirmations`, `combo_exit_confirmations`, `combo_lookback`.
- `algo_trading/strategy.py`: add `slow_sma` context field, `SmaCrossoverStrategy`, `CombinedSignalsStrategy`, helper parsing/counting functions, registry entries, preset values.
- `algo_trading/simulator.py`: validate combo fields and return sufficient required candles for combined signals.

- [x] **Step 4: Verify green**

Run:

```bash
python -m pytest tests/test_strategy.py tests/test_simulator.py -q
```

Expected: strategy and simulator tests pass.

### Task 2: CLI/API/Combo Page Surface Tests

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `tests/test_ui.py`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/types.ts`
- Modify: `algo_trading/cli.py`
- Modify: `algo_trading/ui.py`

- [x] **Step 1: Write failing surface tests**

Add tests asserting:
- CLI stores combo fields in `config.json`.
- `/api/strategies` exposes both new strategies.
- Strategy Lab can request `combined-signals`.
- `/api/combination-signals` returns a combined strategy summary and markers.
- Frontend routes include `/combos`.
- Frontend source includes a dedicated Combination Signals tab/page with combo controls.

- [x] **Step 2: Verify red**

Run:

```bash
python -m pytest tests/test_cli.py tests/test_ui.py -q
```

Expected: failures for unknown arguments, missing payload fields, and absent frontend controls.

- [x] **Step 3: Implement surface changes**

Add CLI args, UI payload parsing, a `/api/combination-signals` endpoint, Vue reactive defaults, a new `combos` mode, and dedicated controls for combo member list and confirmation counts.

- [x] **Step 4: Verify green**

Run:

```bash
python -m pytest tests/test_cli.py tests/test_ui.py -q
```

Expected: CLI/API/UI tests pass.

### Task 3: Docs, Build, Docker, Push

**Files:**
- Modify: `README.md`
- Build output: `algo_trading/web/dist/*`

- [x] **Step 1: Update docs**

Document `sma-crossover`, `combined-signals`, and the new combo configuration knobs.

- [x] **Step 2: Run full verification**

Run:

```bash
make check
```

Expected: unit tests, mypy, compileall, and frontend build pass.

- [x] **Step 3: Rebuild Docker**

Run:

```bash
docker compose up -d --build
```

Expected: app container is rebuilt and healthy.

- [x] **Step 4: Commit and push main**

Use the Lore commit protocol and push `main`:

```bash
git status --short
git add .
git commit -m "<lore protocol message>"
git push origin main
```

Expected: `main` and `origin/main` point to the new commit.
