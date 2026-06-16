from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
import mimetypes
import os
import time
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable

from fastapi import Body, Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from algo_trading.auth import (
    AuthStore,
    AuthUser,
    InMemoryAuthStore,
    PostgresAuthStore,
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    public_user,
)
from algo_trading.data import BinanceMarketDataClient, MarketDataClient
from algo_trading.env import load_env_file
from algo_trading.historical_store import HistoricalDataStore, historical_store_from_env
from algo_trading.historical_data import HistoricalCsvRefreshService
from algo_trading import jobs as background_jobs
from algo_trading.job_queue import JobQueue, job_queue_from_env
from algo_trading.market_breadth import MarketBreadthService
from algo_trading.ui import (
    WEB_DIST_ROOT,
    is_frontend_route,
    is_vite_asset_route,
    live_chart_payload,
    strategies_payload,
    top_symbols_payload,
    _live_client_for_handler,
)

ADMIN_EMAIL = "cuiyeqing960904@gmail.com"
ADMIN_PASSWORD = "Vladimir960904"
EXPIRY_CHECK_SECONDS = 60 * 60
HISTORICAL_CSV_REFRESH_SECONDS = 60 * 60
HISTORICAL_CSV_PRUNE_SECONDS = 24 * 60 * 60


def parse_optional_datetime(value: Any, field_name: str) -> datetime | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO datetime or null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO datetime or null") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def create_app(
    output_root: str | Path = "runs",
    client_factory: Callable[[], MarketDataClient] = BinanceMarketDataClient,
    auth_store: AuthStore | None = None,
    market_breadth_service: Any | None = None,
    historical_csv_service: Any | None = None,
    expiry_check_seconds: float | None = None,
    historical_csv_refresh_seconds: float | None = None,
    historical_csv_prune_seconds: float | None = None,
    historical_store: HistoricalDataStore | None = None,
    job_queue: JobQueue | None = None,
    seed_admin: bool = True,
    admin_seed_password: str | None = None,
) -> FastAPI:
    load_env_file()
    store = auth_store or auth_store_from_env()
    store.ensure_schema()
    if seed_admin:
        store.seed_admin_user(admin_email(), admin_seed_password or admin_password())
    history_store = historical_store or historical_store_from_env()
    history_store.ensure_schema()
    breadth_service = market_breadth_service or MarketBreadthService(store=history_store)
    csv_service = historical_csv_service or HistoricalCsvRefreshService()
    background_queue = job_queue if job_queue is not None else job_queue_from_env()
    expiry_interval = (
        expiry_check_seconds
        if expiry_check_seconds is not None
        else float(os.environ.get("USER_EXPIRY_CHECK_SECONDS", EXPIRY_CHECK_SECONDS))
    )
    csv_refresh_interval = (
        historical_csv_refresh_seconds
        if historical_csv_refresh_seconds is not None
        else float(
            os.environ.get(
                "HISTORICAL_CSV_REFRESH_SECONDS",
                HISTORICAL_CSV_REFRESH_SECONDS,
            )
        )
    )
    csv_prune_interval = (
        historical_csv_prune_seconds
        if historical_csv_prune_seconds is not None
        else float(
            os.environ.get(
                "HISTORICAL_CSV_PRUNE_SECONDS",
                HISTORICAL_CSV_PRUNE_SECONDS,
            )
        )
    )
    expiry_task: asyncio.Task[None] | None = None
    historical_csv_task: asyncio.Task[None] | None = None

    def require_user(
        session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> AuthUser:
        store.deactivate_expired_users()
        user = store.user_for_session(session_token)
        if user is None:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="authentication required",
            )
        return user

    def require_active_user(user: AuthUser = Depends(require_user)) -> AuthUser:
        if not user.is_active:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="account inactive",
            )
        return user

    def require_admin_user(user: AuthUser = Depends(require_user)) -> AuthUser:
        if not user.is_admin:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="admin required",
            )
        return user

    async def deactivate_expired_users_loop() -> None:
        while True:
            await enqueue_or_run_background_job(
                background_jobs.deactivate_expired_users,
                store.deactivate_expired_users,
                job_id_prefix="deactivate-expired-users",
                description="Deactivate users whose access has expired",
            )
            await asyncio.sleep(max(1.0, expiry_interval))

    async def maintain_historical_csvs_loop() -> None:
        last_prune = 0.0
        while True:
            await asyncio.sleep(max(0.01, csv_refresh_interval))
            await enqueue_or_run_background_job(
                background_jobs.refresh_historical_csvs,
                csv_service.refresh_all,
                job_id_prefix="refresh-historical-csvs",
                description="Refresh live-page historical candle CSV files",
            )
            refresh_breadth = getattr(breadth_service, "refresh_default_symbols", None)
            if callable(refresh_breadth):
                await enqueue_or_run_background_job(
                    background_jobs.refresh_market_breadth,
                    refresh_breadth,
                    job_id_prefix="refresh-market-breadth",
                    description="Refresh US market breadth CSV files",
                )
            if csv_prune_interval <= 0:
                continue
            now = time.monotonic()
            if now - last_prune < csv_prune_interval:
                continue
            prune_all = getattr(csv_service, "prune_all", None)
            if callable(prune_all):
                await enqueue_or_run_background_job(
                    background_jobs.prune_historical_csvs,
                    prune_all,
                    job_id_prefix="prune-historical-csvs",
                    description="Prune expired historical candle CSV rows",
                )
            last_prune = now

    async def enqueue_or_run_background_job(
        queued_callback: Callable[[], Any],
        direct_callback: Callable[[], Any],
        *,
        job_id_prefix: str,
        description: str,
    ) -> None:
        if background_queue is not None:
            try:
                await asyncio.to_thread(
                    background_queue.enqueue,
                    queued_callback,
                    job_id_prefix=job_id_prefix,
                    description=description,
                )
                return
            except Exception:
                pass
        await run_background_call(direct_callback)

    async def run_background_call(callback: Callable[[], Any]) -> None:
        with suppress(Exception):
            await asyncio.to_thread(callback)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        nonlocal expiry_task, historical_csv_task
        store.deactivate_expired_users()
        if expiry_interval > 0:
            expiry_task = asyncio.create_task(deactivate_expired_users_loop())
        if csv_refresh_interval > 0:
            historical_csv_task = asyncio.create_task(maintain_historical_csvs_loop())
        try:
            yield
        finally:
            if expiry_task is not None:
                expiry_task.cancel()
                with suppress(asyncio.CancelledError):
                    await expiry_task
            expiry_task = None
            if historical_csv_task is not None:
                historical_csv_task.cancel()
                with suppress(asyncio.CancelledError):
                    await historical_csv_task
            historical_csv_task = None

    app = FastAPI(title="Algo Trading", lifespan=lifespan)

    @app.exception_handler(HTTPException)
    async def http_error_handler(
        _request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        return JSONResponse(
            {"ok": False, "error": str(exc.detail)},
            status_code=exc.status_code,
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(
        _request: Request,
        exc: ValueError,
    ) -> JSONResponse:
        return JSONResponse(
            {"ok": False, "error": str(exc)},
            status_code=HTTPStatus.BAD_REQUEST,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        _request: Request,
        exc: Exception,
    ) -> JSONResponse:
        return JSONResponse(
            {"ok": False, "error": str(exc)},
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    @app.post("/api/auth/register")
    def register(
        response: Response,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any]:
        credentials = payload or {}
        user = store.register_user(
            str(credentials.get("username") or ""),
            str(credentials.get("password") or ""),
        )
        set_session_cookie(response, store.create_session(user.id))
        return {"ok": True, "user": public_user(user)}

    @app.post("/api/auth/login")
    def login(
        response: Response,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any]:
        credentials = payload or {}
        try:
            user = store.authenticate_user(
                str(credentials.get("username") or ""),
                str(credentials.get("password") or ""),
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=str(exc),
            ) from exc
        set_session_cookie(response, store.create_session(user.id))
        return {"ok": True, "user": public_user(user)}

    @app.post("/api/auth/logout")
    def logout(
        response: Response,
        session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        store.delete_session(session_token)
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
        return {"ok": True}

    @app.get("/api/auth/me")
    def current_user(
        session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        store.deactivate_expired_users()
        user = store.user_for_session(session_token)
        return {"ok": True, "user": public_user(user) if user else None}

    @app.get("/api/profile")
    def get_profile(user: AuthUser = Depends(require_user)) -> dict[str, Any]:
        return {"ok": True, "user": public_user(user)}

    @app.patch("/api/profile")
    def update_profile(
        payload: dict[str, Any] | None = Body(default=None),
        user: AuthUser = Depends(require_user),
    ) -> dict[str, Any]:
        profile = payload or {}
        updated = store.update_user_profile(
            user.id,
            first_name=optional_text(profile.get("first_name")),
            last_name=optional_text(profile.get("last_name")),
            middle_name=optional_text(profile.get("middle_name")),
        )
        return {"ok": True, "user": public_user(updated)}

    @app.get("/api/admin/users")
    def get_admin_users(_admin: AuthUser = Depends(require_admin_user)) -> dict[str, Any]:
        store.deactivate_expired_users()
        return {"ok": True, "users": [public_user(user) for user in store.list_users()]}

    @app.patch("/api/admin/users/{user_id}/access")
    def update_admin_user_access(
        user_id: int,
        payload: dict[str, Any] | None = Body(default=None),
        _admin: AuthUser = Depends(require_admin_user),
    ) -> dict[str, Any]:
        access = payload or {}
        is_active = access.get("is_active")
        if not isinstance(is_active, bool):
            raise ValueError("is_active must be a boolean")
        existing_user = next(
            (listed_user for listed_user in store.list_users() if listed_user.id == user_id),
            None,
        )
        if existing_user is None:
            raise ValueError("unknown user")
        expired_at = (
            parse_optional_datetime(access["expired_at"], "expired_at")
            if "expired_at" in access
            else existing_user.expired_at
        )
        updated = store.set_user_access(
            user_id,
            is_active=is_active,
            expired_at=expired_at,
        )
        return {"ok": True, "user": public_user(updated)}

    @app.get("/api/symbols")
    def get_symbols(
        top: int = 10,
        _user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        return top_symbols_payload(client_factory(), top=top)

    @app.get("/api/strategies")
    def get_strategies(_user: AuthUser = Depends(require_active_user)) -> dict[str, Any]:
        return strategies_payload()

    @app.get("/api/live-chart")
    def get_live_chart(
        request: Request,
        _user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        payload = dict(request.query_params)
        return live_chart_payload(
            payload,
            _live_client_for_handler(payload, client_factory),
            historical_store=history_store,
        )

    @app.get("/api/market-breadth")
    def get_market_breadth(
        symbols: str = "",
        _user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        requested_symbols = (
            [symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()]
            if symbols
            else None
        )
        return breadth_service.payload(requested_symbols)

    @app.api_route(
        "/api/{_full_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    def unknown_api(_full_path: str) -> None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="not found")

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend(full_path: str) -> FileResponse:
        request_path = f"/{full_path}" if full_path else "/"
        if is_frontend_route(request_path):
            return FileResponse(
                WEB_DIST_ROOT / "index.html",
                media_type="text/html; charset=utf-8",
            )
        if is_vite_asset_route(request_path):
            asset_path = WEB_DIST_ROOT / request_path.lstrip("/")
            if not asset_path.is_file():
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="not found")
            return FileResponse(
                asset_path,
                media_type=mimetypes.guess_type(asset_path.name)[0]
                or "application/octet-stream",
            )
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="not found")

    return app


def auth_store_from_env() -> AuthStore:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return PostgresAuthStore(database_url)
    return InMemoryAuthStore()


def admin_email() -> str:
    return os.environ.get("ADMIN_EMAIL", ADMIN_EMAIL).strip().lower()


def admin_password() -> str:
    return os.environ.get("ADMIN_PASSWORD", ADMIN_PASSWORD)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        max_age=SESSION_TTL_SECONDS,
        path="/",
        samesite="lax",
    )


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
