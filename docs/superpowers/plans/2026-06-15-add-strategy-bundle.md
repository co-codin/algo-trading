# Add Strategy Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add nine deterministic strategy options across trend/breakout, mean-reversion, and volume-confirmation categories.

**Architecture:** Extend the existing enum-backed strategy registry. Add pure indicator helpers, compute the new series once in `StrategyContext`, then implement one class per strategy with focused entry/exit rules and warmup requirements.

**Tech Stack:** Python dataclasses/enums, unittest, existing simulator/strategy modules, Vue UI through existing dynamic metadata.

---

## File Structure

- Modify `algo_trading/indicators.py`: add Keltner, CCI, Williams %R, OBV, rolling volume mean, and Bollinger width helpers.
- Modify `algo_trading/models.py`: add nine `StrategyName` values and minimal config knobs for CCI/Williams thresholds, Keltner multiplier, volume multiplier, and squeeze threshold.
- Modify `algo_trading/strategy.py`: extend `StrategyContext`, compute new indicators, add nine strategy classes, register them.
- Modify `algo_trading/simulator.py`: add warmup requirements and validation for new config knobs.
- Modify `tests/test_indicators.py`: indicator helper tests.
- Modify `tests/test_strategy.py`: registry plus one entry test per strategy.
- Modify `tests/test_simulator.py`: warmup and backtest smoke coverage for new strategies.
- Modify `README.md`: strategy list descriptions.

### Task 1: Indicator Helpers

**Files:**
- Modify: `tests/test_indicators.py`
- Modify: `algo_trading/indicators.py`

- [ ] **Step 1: Write failing indicator tests**

Add tests for `commodity_channel_index`, `williams_r`, `on_balance_volume`, `rolling_volume_mean`, `keltner_channels`, and `bollinger_width`.

- [ ] **Step 2: Run red test**

Run: `python3 -m unittest tests.test_indicators -v`

Expected: import/name failures for the new helpers.

- [ ] **Step 3: Implement minimal pure helpers**

Implement helpers with existing `rolling_mean`, `ema`, and `atr` primitives. Return one output value per input candle/value.

- [ ] **Step 4: Run green test**

Run: `python3 -m unittest tests.test_indicators -v`

Expected: all indicator tests pass.

### Task 2: Strategy Registry and Context

**Files:**
- Modify: `tests/test_strategy.py`
- Modify: `algo_trading/models.py`
- Modify: `algo_trading/strategy.py`

- [ ] **Step 1: Write failing registry/context tests**

Update `test_registry_lists_all_strategies` to include the nine new names. Add context assertions through strategy entry tests rather than direct private coupling.

- [ ] **Step 2: Run red test**

Run: `python3 -m unittest tests.test_strategy.StrategyTests.test_registry_lists_all_strategies -v`

Expected: list mismatch because enum values are not present.

- [ ] **Step 3: Add enum/config/context fields**

Add `StrategyName` enum values. Add config fields for `keltner_multiplier`, `cci_period`, `cci_oversold`, `cci_overbought`, `williams_period`, `williams_oversold`, `williams_overbought`, `volume_period`, `volume_multiplier`, and `squeeze_threshold_pct`. Compute the matching context series.

- [ ] **Step 4: Run registry test**

Run: `python3 -m unittest tests.test_strategy.StrategyTests.test_registry_lists_all_strategies -v`

Expected: pass once registry classes are registered in Task 3.

### Task 3: Nine Strategy Classes

**Files:**
- Modify: `tests/test_strategy.py`
- Modify: `algo_trading/strategy.py`

- [ ] **Step 1: Write failing strategy entry tests**

Add one entry test for each new strategy using the existing `first_entry_signal` helper and explicit config periods.

- [ ] **Step 2: Run red tests**

Run: `python3 -m unittest tests.test_strategy -v`

Expected: failures for unsupported strategy names or no signals.

- [ ] **Step 3: Implement strategy classes**

Add classes `KeltnerBreakoutStrategy`, `EmaPullbackStrategy`, `AtrTrailingTrendStrategy`, `CciReversalStrategy`, `WilliamsRReversalStrategy`, `BollingerSqueezeReleaseStrategy`, `ObvTrendStrategy`, `VolumeBreakoutStrategy`, and `VwapTrendContinuationStrategy`. Register them in `_STRATEGIES`.

- [ ] **Step 4: Run green strategy tests**

Run: `python3 -m unittest tests.test_strategy -v`

Expected: all strategy tests pass.

### Task 4: Simulator Validation and Docs

**Files:**
- Modify: `tests/test_simulator.py`
- Modify: `algo_trading/simulator.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing simulator validation tests**

Add tests proving new strategy periods are positive and each new strategy can run a small backtest without warmup rejection when given enough candles.

- [ ] **Step 2: Run red simulator tests**

Run: `python3 -m unittest tests.test_simulator -v`

Expected: failures for missing warmup rules or missing validation.

- [ ] **Step 3: Implement validation/warmups and docs**

Add validation for new numeric knobs, update `_required_candles`, and document the new strategy names in README.

- [ ] **Step 4: Run full verification**

Run: `make check`

Expected: unit tests, mypy, compileall, and Vue check all pass.

