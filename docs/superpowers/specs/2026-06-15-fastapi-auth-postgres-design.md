# FastAPI Auth And Postgres Design

## Goal

Add login and registration to the trading UI, backed by PostgreSQL in Docker, and migrate the HTTP surface to FastAPI.

## Architecture

The trading and strategy functions remain in `algo_trading.ui` as plain Python payload builders. A new `algo_trading.web_app` module owns the FastAPI app, routes, auth dependencies, cookie handling, and SPA/static-file serving. A new `algo_trading.auth` module owns password hashing, user registration, login validation, session creation, and two auth stores: in-memory for tests/local fallback and Postgres for Docker/runtime persistence.

## Auth Model

- Registration accepts `username` and `password`.
- Username is normalized by trimming whitespace and lowercasing.
- Passwords are hashed with `hashlib.scrypt` and per-user random salts.
- Sessions use random tokens from `secrets.token_urlsafe`.
- Only a SHA-256 hash of the session token is stored.
- Browser sessions are stored in an `HttpOnly`, `SameSite=Lax` cookie named `algo_session`.
- `/api/auth/register`, `/api/auth/login`, `/api/auth/logout`, and `/api/auth/me` are public.
- All existing trading APIs require an authenticated user.
- Frontend routes and static assets remain public so the SPA can load and show the auth screen.

## FastAPI Surface

The FastAPI app provides:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- Existing trading endpoints under `/api/*`
- Existing SPA routes such as `/live`, `/lab`, and `/combos`
- Existing Vite asset routes under `/assets/*`

FastAPI exception handlers keep the frontend-compatible JSON error shape: `{"ok": false, "error": "..."}`.

## Docker/Postgres

`docker-compose.yml` adds a `postgres` service with a persistent volume and healthcheck. The app service gets `DATABASE_URL=postgresql://algo:algo@postgres:5432/algo_trading` and waits for Postgres health. The Docker image installs FastAPI, Uvicorn, and psycopg runtime dependencies.

## Frontend

The Vue app checks `/api/auth/me` on startup. Anonymous users see a login/register screen. Authenticated users see the existing trading UI plus a logout button in the top bar. `requestJson` sends same-origin credentials explicitly so the session cookie is included.

## Testing

- Auth unit tests cover password hashing, duplicate-user rejection, login failure, session lookup, and logout.
- FastAPI route tests use `fastapi.testclient.TestClient` with `InMemoryAuthStore`.
- Existing trading route tests move from `ThreadingHTTPServer` to FastAPI TestClient where needed.
- Frontend source tests verify login/register UI wiring and auth API calls.
- Compose/Docker tests verify Postgres service, app `DATABASE_URL`, dependency install, and Uvicorn startup command.

## References

- FastAPI official docs: app creation, dependencies, cookies, static files, and TestClient.
- psycopg official docs: PostgreSQL connections and connection usage.
