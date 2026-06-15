# FastAPI Auth Postgres Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add FastAPI-powered login/registration with Postgres-backed users and sessions while preserving the existing trading behavior.

**Architecture:** Keep trading payload functions in `algo_trading.ui`, add `algo_trading.auth` for auth stores and password/session primitives, and add `algo_trading.web_app` for FastAPI routes. The Vue app gates the current trading UI behind `/api/auth/me`, and Docker Compose starts Postgres plus the app.

**Tech Stack:** FastAPI, Uvicorn, psycopg 3, PostgreSQL 16, Vue 3, Python unittest, FastAPI TestClient.

---

### Task 1: Auth Store Contract

**Files:**
- Create: `tests/test_auth.py`
- Create: `algo_trading/auth.py`

- [ ] Write failing tests for password hashing, user registration, duplicate rejection, login validation, session lookup, and logout in `tests/test_auth.py`.
- [ ] Run `python3 -m pytest tests/test_auth.py -q` and confirm failures because `algo_trading.auth` does not exist.
- [ ] Implement `algo_trading.auth` with `InMemoryAuthStore`, scrypt password hashing, token hashing, and session expiry.
- [ ] Run `python3 -m pytest tests/test_auth.py -q` and confirm all auth unit tests pass.

### Task 2: FastAPI App Contract

**Files:**
- Create: `tests/test_web_app.py`
- Create: `algo_trading/web_app.py`
- Modify: `algo_trading/ui.py`
- Modify: `tests/test_ui.py`

- [ ] Write failing FastAPI tests for anonymous 401 on protected API, register cookie, login cookie, logout, `/api/auth/me`, frontend route serving, and existing live-chart route behavior.
- [ ] Run focused FastAPI tests and confirm failures because `create_app` does not exist.
- [ ] Implement `algo_trading.web_app.create_app` with auth routes, protected trading routes, JSON error handlers, Vite asset serving, and SPA route serving.
- [ ] Update `algo_trading.ui.serve` to run the FastAPI app with Uvicorn.
- [ ] Replace the old `ThreadingHTTPServer/create_handler` test path in `tests/test_ui.py` with FastAPI TestClient.
- [ ] Run focused FastAPI tests and the updated UI route test.

### Task 3: Frontend Auth Shell

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/i18n.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`
- Modify: `tests/test_ui.py`

- [ ] Write failing source tests that require auth state, login/register forms, `/api/auth/me`, `/api/auth/login`, `/api/auth/register`, `/api/auth/logout`, logout button, and `credentials: "same-origin"`.
- [ ] Run focused UI source tests and confirm failures.
- [ ] Implement frontend auth state and shell.
- [ ] Add translated English/Russian auth labels and messages.
- [ ] Run focused UI source tests and `npm run frontend:check`.

### Task 4: Docker And Dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `Makefile`
- Modify: `tests/test_ui.py`

- [ ] Write failing source tests for FastAPI/Uvicorn/psycopg dependencies, Docker dependency install, Uvicorn command, Postgres service, persistent volume, app `DATABASE_URL`, and Postgres health dependency.
- [ ] Run focused Docker/dependency source tests and confirm failures.
- [ ] Add runtime dependencies and Docker/Compose Postgres wiring.
- [ ] Update Docker smoke behavior to register/login before hitting protected APIs.
- [ ] Run focused Docker/dependency source tests.

### Task 5: Verification And Publish

**Files:**
- Generated: `algo_trading/web/dist/*`

- [ ] Run `make check`.
- [ ] Run `git diff --check`.
- [ ] Run `docker compose up -d --build`.
- [ ] Verify `GET /` and `GET /api/auth/me` respond on `http://127.0.0.1:8765`.
- [ ] Commit implementation with Lore trailers.
- [ ] Push `main`.

## Self-Review

- Spec coverage: FastAPI migration, auth endpoints, session cookie, Postgres Docker service, frontend auth shell, route protection, and test strategy are covered.
- Placeholder scan: No placeholder tokens or unassigned implementation steps remain.
- Type consistency: `InMemoryAuthStore`, `PostgresAuthStore`, `create_app`, `AuthUser`, and `algo_session` are named consistently across tasks.
