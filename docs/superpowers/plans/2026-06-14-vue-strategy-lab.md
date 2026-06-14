# Vue Strategy Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the browser UI as Vue 3/Vite, keep TradingView Lightweight Charts, and add more famous paper/backtest strategies plus a ranked strategy lab API.

**Architecture:** Keep Python as the API/static server and simulation engine. Add a `frontend/` Vue source tree that builds into `algo_trading/web/dist`, then serve known frontend routes from that build output. Extend the existing strategy registry and `StrategyConfig` so CLI, API, live markers, paper trading, backtests, and the Vue dropdown all use one backend strategy source.

**Tech Stack:** Python `unittest`, Vue 3, Vite, TypeScript, TradingView Lightweight Charts, Docker multi-stage build.

---

## File Structure

- `algo_trading/models.py`: add strategy enum names and parameters.
- `algo_trading/indicators.py`: add ATR, VWAP, stochastic RSI, and rolling helpers.
- `algo_trading/strategy.py`: add strategy implementations and preset values.
- `algo_trading/simulator.py`: validate new parameters and warmup requirements.
- `algo_trading/ui.py`: add `/api/strategies`, `/api/strategy-lab`, and serve Vue dist routes.
- `tests/test_strategy.py`, `tests/test_simulator.py`, `tests/test_ui.py`: prove new backend behavior first.
- `frontend/`: Vue source, components, API client, and TradingView chart component.
- `package.json`, `vite.config.ts`, `tsconfig*.json`: frontend build/test tooling.
- `Makefile`, `Dockerfile`, `.dockerignore`: build Vue assets and include them in local/container checks.
- `README.md`: document Vue UI, TradingView chart, strategy lab, and safety boundary.

### Task 1: Backend Strategy Tests

- [ ] Write failing tests that `list_strategy_names()` includes `supertrend`, `vwap-reversion`, `stoch-rsi-reversal`, `ema-ribbon`, and `momentum-scalping`.
- [ ] Write failing entry-signal tests for each new strategy using deterministic candle fixtures.
- [ ] Write failing simulator validation tests for ATR, VWAP, stochastic RSI, EMA ribbon, and momentum periods.
- [ ] Run targeted tests and confirm failure is due to missing enum/config/strategy support.

### Task 2: Backend Strategy Implementation

- [ ] Add strategy enum values and `StrategyConfig` fields.
- [ ] Add indicator helpers: ATR, rolling VWAP, stochastic RSI, and EMA ribbon.
- [ ] Extend `StrategyContext` and `build_strategy_context`.
- [ ] Implement the five new strategies with long/short support.
- [ ] Extend presets and validation/warmup rules.
- [ ] Run targeted tests until green and commit this slice.

### Task 3: Strategy Metadata And Lab API

- [ ] Add failing tests for `/api/strategies` metadata and `strategy_lab_payload`.
- [ ] Implement strategy metadata from the registry.
- [ ] Implement strategy lab matrix ranking over symbols, strategies, and presets.
- [ ] Add `/api/strategies` and `/api/strategy-lab` routes.
- [ ] Run targeted UI tests until green and commit this slice.

### Task 4: Vue/Vite Frontend

- [ ] Add Vue/Vite/TypeScript package files.
- [ ] Create `frontend/index.html`, `src/main.ts`, `src/App.vue`, `src/api.ts`, and components for forms, live chart, run history, and strategy lab.
- [ ] Use TradingView Lightweight Charts in the live/chart component.
- [ ] Build to `algo_trading/web/dist`.
- [ ] Replace legacy static assets by serving only the Vue build output.
- [ ] Run `npm install`, `npm run build`, and commit this slice.

### Task 5: Server, Docker, Docs, Verification

- [ ] Update `ui.py` route serving to use `algo_trading/web/dist/index.html`.
- [ ] Update `Makefile` targets for frontend install/build/check.
- [ ] Update Dockerfile to build frontend assets before copying into the Python image.
- [ ] Update README with Vue UI routes, strategy lab, TradingView chart, and no-real-orders warning.
- [ ] Run `make check`, route smoke checks, Docker smoke, then push.

## Self-Review

- Spec coverage: Vue rebuild, TradingView chart, route serving, strategy expansion, strategy lab, docs, Docker, and no-profit guarantee are covered.
- Placeholder scan: all tasks are concrete and bounded.
- Type consistency: strategy names, route names, and output paths match the design.
