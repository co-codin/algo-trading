from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
import mimetypes
import os
import urllib.parse
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
from algo_trading.market_breadth import MarketBreadthService
from algo_trading.ui import (
    WEB_DIST_ROOT,
    combination_signals_payload,
    is_frontend_route,
    is_vite_asset_route,
    live_chart_payload,
    list_runs,
    load_run_details,
    run_backtest_payload,
    run_paper_payload,
    strategies_payload,
    strategy_lab_payload,
    top_symbols_payload,
    _live_client_for_handler,
)

ADMIN_EMAIL = "cuiyeqing960904@gmail.com"
EXPIRY_CHECK_SECONDS = 60 * 60


def create_app(
    output_root: str | Path = "runs",
    client_factory: Callable[[], MarketDataClient] = BinanceMarketDataClient,
    auth_store: AuthStore | None = None,
    market_breadth_service: Any | None = None,
    expiry_check_seconds: float | None = None,
) -> FastAPI:
    output_path = Path(output_root)
    store = auth_store or auth_store_from_env()
    store.ensure_schema()
    breadth_service = market_breadth_service or MarketBreadthService()
    expiry_interval = (
        expiry_check_seconds
        if expiry_check_seconds is not None
        else float(os.environ.get("USER_EXPIRY_CHECK_SECONDS", EXPIRY_CHECK_SECONDS))
    )
    expiry_task: asyncio.Task[None] | None = None

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
        if user.username != admin_email():
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="admin required",
            )
        return user

    async def deactivate_expired_users_loop() -> None:
        while True:
            store.deactivate_expired_users()
            await asyncio.sleep(max(1.0, expiry_interval))

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        nonlocal expiry_task
        store.deactivate_expired_users()
        if expiry_interval > 0:
            expiry_task = asyncio.create_task(deactivate_expired_users_loop())
        try:
            yield
        finally:
            if expiry_task is None:
                return
            expiry_task.cancel()
            with suppress(asyncio.CancelledError):
                await expiry_task
            expiry_task = None

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

    @app.get("/api/admin/users")
    def get_admin_users(_admin: AuthUser = Depends(require_admin_user)) -> dict[str, Any]:
        store.deactivate_expired_users()
        return {"ok": True, "users": [public_user(user) for user in store.list_users()]}

    @app.get("/api/symbols")
    def get_symbols(
        top: int = 10,
        _user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        return top_symbols_payload(client_factory(), top=top)

    @app.get("/api/strategies")
    def get_strategies(_user: AuthUser = Depends(require_active_user)) -> dict[str, Any]:
        return strategies_payload()

    @app.get("/api/runs")
    def get_runs(_user: AuthUser = Depends(require_active_user)) -> dict[str, Any]:
        return {"ok": True, "runs": list_runs(output_path)}

    @app.get("/api/live-chart")
    def get_live_chart(
        request: Request,
        _user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        payload = dict(request.query_params)
        return live_chart_payload(
            payload,
            _live_client_for_handler(payload, client_factory),
            output_path,
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

    @app.get("/api/run")
    def get_run(
        path: str = "",
        _user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        return load_run_details(path, output_path)

    @app.post("/api/backtest")
    def post_backtest(
        payload: dict[str, Any] | None = Body(default=None),
        _user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        return run_backtest_payload(payload or {}, client_factory(), output_path)

    @app.post("/api/paper")
    def post_paper(
        payload: dict[str, Any] | None = Body(default=None),
        _user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        return run_paper_payload(payload or {}, client_factory(), output_path)

    @app.post("/api/strategy-lab")
    def post_strategy_lab(
        payload: dict[str, Any] | None = Body(default=None),
        _user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        return strategy_lab_payload(payload or {}, client_factory())

    @app.post("/api/combination-signals")
    def post_combination_signals(
        payload: dict[str, Any] | None = Body(default=None),
        _user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        request_payload = payload or {}
        return combination_signals_payload(
            request_payload,
            _live_client_for_handler(request_payload, client_factory),
        )

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


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        max_age=SESSION_TTL_SECONDS,
        path="/",
        samesite="lax",
    )
