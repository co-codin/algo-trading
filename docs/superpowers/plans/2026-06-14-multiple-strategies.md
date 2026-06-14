# Multiple Strategies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add selectable strategy implementations, presets, and UI/CLI controls while keeping the app paper-only and read-only.

**Architecture:** Extend `StrategyConfig` with strategy/preset and strategy-specific parameters, then route all signal calculation through `algo_trading.strategy`. The simulator and live chart path will build one `StrategyContext` per candle set and call the selected registered strategy for entry/exit signals.

**Tech Stack:** Python dataclasses/enums, standard-library unit tests, existing vanilla HTML/CSS/JS UI, Docker/Make verification.

---

## File Structure

- Modify `algo_trading/models.py`: add `StrategyName`, `StrategyPreset`, and strategy-specific config fields.
- Modify `algo_trading/strategy.py`: add `StrategyContext`, registry helpers, preset application, and five strategy implementations.
- Modify `algo_trading/simulator.py`: use the selected strategy/context instead of hardcoded EMA/RSI signal functions.
- Modify `algo_trading/ui.py`: parse new payload fields and use the selected strategy for live markers.
- Modify `algo_trading/cli.py`: expose `--strategy`, `--preset`, and strategy-specific options.
- Modify `algo_trading/web/index.html`: add strategy/preset controls and fields.
- Modify `algo_trading/web/app.js`: include new strategy fields in live chart requests.
- Modify `README.md`: document available strategies and presets.
- Modify tests in `tests/test_models.py`, `tests/test_strategy.py`, `tests/test_simulator.py`, `tests/test_cli.py`, and `tests/test_ui.py`.

## Task 1: Model And Strategy API Tests

**Files:**
- Modify: `tests/test_models.py`
- Modify: `tests/test_strategy.py`

- [ ] **Step 1: Write failing model tests**

Add tests that expect `StrategyConfig().strategy.value == "ema-rsi"`, `StrategyConfig().preset.value == "custom"`, and default values for `macd_signal`, `bollinger_period`, `bollinger_stddev`, `donchian_period`, and `rsi_midline`.

- [ ] **Step 2: Write failing registry tests**

Add tests that import `StrategyName`, `StrategyPreset`, `apply_strategy_preset`, `build_strategy_context`, `get_strategy`, and `list_strategy_names`. Assert that all five strategy names are listed, unknown names raise `ValueError`, presets return deterministic config values, and each strategy emits an expected entry signal on deterministic candles.

- [ ] **Step 3: Run red tests**

Run:

```bash
python3 -m unittest tests.test_models tests.test_strategy -v
```

Expected: failures or import errors for missing strategy/preset fields and registry functions.

## Task 2: Strategy Registry And Presets

**Files:**
- Modify: `algo_trading/models.py`
- Modify: `algo_trading/strategy.py`

- [ ] **Step 1: Add enums and config fields**

Add `StrategyName` values `ema-rsi`, `macd`, `bollinger-reversion`, `donchian-breakout`, and `rsi-reversal`. Add `StrategyPreset` values `custom`, `conservative`, `balanced`, and `aggressive`. Extend `StrategyConfig` with strategy, preset, `macd_signal`, `bollinger_period`, `bollinger_stddev`, `donchian_period`, and `rsi_midline`.

- [ ] **Step 2: Add strategy context**

In `algo_trading/strategy.py`, add `StrategyContext` with candles, closes, highs, lows, fast EMA, slow EMA, RSI, MACD, MACD signal, Bollinger average/bands, and Donchian high/low series. Add `build_strategy_context(candles, config)`.

- [ ] **Step 3: Add registry**

Add `TradingStrategy` protocol/base class, `list_strategy_names()`, `get_strategy(name)`, `entry_signal_for_index(config, context, index)`, and `exit_signal_for_position(side, config, context, index)`.

- [ ] **Step 4: Implement strategies**

Move current EMA/RSI behavior into `EmaRsiStrategy`. Add `MacdStrategy`, `BollingerReversionStrategy`, `DonchianBreakoutStrategy`, and `RsiReversalStrategy` using the signal reasons from the spec.

- [ ] **Step 5: Implement presets**

Add `apply_strategy_preset(config)` that returns the unchanged config for `custom`, otherwise returns a dataclass-replaced config with deterministic values for common risk fields and strategy-specific lookbacks.

- [ ] **Step 6: Run focused green tests**

Run:

```bash
python3 -m unittest tests.test_models tests.test_strategy -v
```

Expected: pass.

## Task 3: Simulator And Validation Wiring

**Files:**
- Modify: `algo_trading/simulator.py`
- Modify: `tests/test_simulator.py`

- [ ] **Step 1: Write failing simulator tests**

Add tests that `run_backtest` can execute at least one trade for `StrategyName.MACD`, `StrategyName.BOLLINGER_REVERSION`, `StrategyName.DONCHIAN_BREAKOUT`, and `StrategyName.RSI_REVERSAL` on deterministic candles. Add a test that invalid periods for new fields raise `ValueError`.

- [ ] **Step 2: Run red tests**

Run:

```bash
python3 -m unittest tests.test_simulator -v
```

Expected: failures because simulator still uses hardcoded EMA/RSI functions.

- [ ] **Step 3: Use registry in simulator**

In `run_backtest`, apply presets once, build one strategy context, and pass context/config into `_Account.on_candle`. Replace hardcoded `signal_for_index` and `exit_signal_for_position` calls with registry-backed functions.

- [ ] **Step 4: Extend validation**

Validate positive `macd_signal`, positive `bollinger_period`, positive `bollinger_stddev`, positive `donchian_period`, and `0 <= rsi_midline <= 100`. Preserve existing EMA/RSI validation because several strategies still use those periods.

- [ ] **Step 5: Run focused green tests**

Run:

```bash
python3 -m unittest tests.test_simulator -v
```

Expected: pass.

## Task 4: CLI And UI Payload Wiring

**Files:**
- Modify: `algo_trading/cli.py`
- Modify: `algo_trading/ui.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_ui.py`

- [ ] **Step 1: Write failing CLI/UI tests**

Add a CLI test that running a fixture backtest with `--strategy macd --preset aggressive --macd-signal 3` writes a config containing those values. Add a UI payload test that `live_chart_payload` with `strategy=macd` returns `long_signal` or `short_signal` markers whose reason begins with `macd_`.

- [ ] **Step 2: Run red tests**

Run:

```bash
python3 -m unittest tests.test_cli tests.test_ui -v
```

Expected: argument parsing or payload parsing failures for new fields.

- [ ] **Step 3: Extend CLI parsing**

Add `--strategy`, `--preset`, `--macd-signal`, `--bollinger-period`, `--bollinger-stddev`, `--donchian-period`, and `--rsi-midline` to common options. Parse values into `StrategyConfig`.

- [ ] **Step 4: Extend UI parsing**

In `_strategy_config_from_payload`, parse the same fields using `StrategyName` and `StrategyPreset`. Update `_strategy_signal_markers` to use `apply_strategy_preset`, `build_strategy_context`, and registry-backed entry signals.

- [ ] **Step 5: Run focused green tests**

Run:

```bash
python3 -m unittest tests.test_cli tests.test_ui -v
```

Expected: pass.

## Task 5: Browser UI And Documentation

**Files:**
- Modify: `algo_trading/web/index.html`
- Modify: `algo_trading/web/app.js`
- Modify: `README.md`

- [ ] **Step 1: Add controls**

Add strategy and preset dropdowns near the existing side selector. Add compact inputs for MACD signal, Bollinger period/stddev, Donchian period, and RSI midpoint.

- [ ] **Step 2: Send fields to live chart**

Add the new field names to the `liveQueryString()` field list so live markers use the same selected strategy and preset as backtests/paper runs.

- [ ] **Step 3: Update README**

Document the five strategies, presets, CLI flags, and UI dropdown behavior. Re-state that all strategies are simulation-only.

- [ ] **Step 4: Run syntax and docs-adjacent checks**

Run:

```bash
node --check algo_trading/web/app.js
git diff --check
```

Expected: both pass.

## Task 6: Full Verification, Commit, Push

**Files:**
- All modified files.

- [ ] **Step 1: Run full verification**

Run:

```bash
make check
make docker-smoke SMOKE_PORT=8766
```

Expected: both pass.

- [ ] **Step 2: Smoke live server**

If a local UI server is running on port 8765, restart it from the new code. Verify:

```bash
curl -fsS 'http://127.0.0.1:8765/api/live-chart?symbol=BTCUSDT&interval=1m&limit=80&strategy=macd' >/dev/null
```

Expected: HTTP 200.

- [ ] **Step 3: Commit with Lore protocol**

Commit the implementation files with a message that records simulation-only constraints, rejected real-execution scope, and verification evidence.

- [ ] **Step 4: Push**

Run:

```bash
git push origin main
```

Expected: remote `main` advances to the implementation commit.
