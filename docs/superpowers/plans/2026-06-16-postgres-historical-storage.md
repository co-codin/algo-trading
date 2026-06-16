# Postgres Historical Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist live candles and breadth history in Postgres instead of primary CSV cache files.

**Architecture:** Introduce a storage abstraction with memory and Postgres implementations. Wire `/live`, breadth, Redis jobs, Docker, and docs to the DB-first storage path while preserving CSV fixture/export helpers.

**Tech Stack:** Python, FastAPI, psycopg, PostgreSQL, Redis/RQ, unittest, Docker Compose.

---

### Task 1: Storage Contract

**Files:**
- Create: `algo_trading/historical_store.py`
- Test: `tests/test_historical_store.py`

- [ ] Write failing tests for candle upsert/dedup/load, tracked series discovery, candle pruning, breadth upsert/load/freshness, and breadth pruning.
- [ ] Implement `InMemoryHistoricalDataStore` and `PostgresHistoricalDataStore` with matching public methods.
- [ ] Verify `python3 -m unittest tests.test_historical_store -v`.

### Task 2: Live Chart Persistence

**Files:**
- Modify: `algo_trading/ui.py`
- Modify: `algo_trading/web_app.py`
- Test: `tests/test_ui.py`, `tests/test_web_app.py`

- [ ] Write failing tests proving `/api/live-chart` upserts fetched candles and returns the merged stored series.
- [ ] Add optional `historical_store` support to `live_chart_payload`.
- [ ] Wire the app-created store into the live route.
- [ ] Verify targeted UI and web app tests.

### Task 3: Refresh Jobs

**Files:**
- Modify: `algo_trading/historical_data.py`
- Modify: `algo_trading/jobs.py`
- Modify: `algo_trading/web_app.py`
- Test: `tests/test_historical_data.py`, `tests/test_jobs.py`

- [ ] Write failing tests for refreshing tracked DB series and pruning old DB candles.
- [ ] Replace CSV-primary refresh logic with `HistoricalDataRefreshService`.
- [ ] Keep legacy class/function aliases where they avoid breaking existing callers.
- [ ] Verify targeted historical and job tests.

### Task 4: Breadth Store

**Files:**
- Modify: `algo_trading/market_breadth.py`
- Test: `tests/test_market_breadth.py`

- [ ] Write failing tests proving fresh stored breadth bars avoid API calls and stale bars fetch/merge/upsert.
- [ ] Read/write breadth bars through the historical store when available.
- [ ] Preserve Cboe full-history behavior for `$CPC`.
- [ ] Verify targeted breadth tests.

### Task 5: Runtime Config And Docs

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Modify: `tests/test_infrastructure.py`

- [ ] Update failing infrastructure tests to expect DB-backed historical storage instead of mounted CSV caches.
- [ ] Remove Docker CSV cache mounts/env from app and worker services.
- [ ] Document Postgres as primary storage and CSV as export/fixture support.
- [ ] Verify infrastructure tests and `docker compose config --quiet`.

### Task 6: Full Verification

**Files:**
- No production edits.

- [ ] Run `python3 -m unittest -v`.
- [ ] Run `python3 -m compileall algo_trading`.
- [ ] Run `git diff --check`.
- [ ] Rebuild with `docker compose up -d --build`.
- [ ] Confirm `docker compose ps` shows app, postgres, redis, and worker healthy.
- [ ] Enqueue one RQ smoke job and confirm the worker logs `Job OK`.
