from __future__ import annotations

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


def create_app(
    output_root: str | Path = "runs",
    client_factory: Callable[[], MarketDataClient] = BinanceMarketDataClient,
    auth_store: AuthStore | None = None,
) -> FastAPI:
    output_path = Path(output_root)
    store = auth_store or auth_store_from_env()
    store.ensure_schema()
    app = FastAPI(title="Algo Trading")

    def require_user(
        session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> AuthUser:
        user = store.user_for_session(session_token)
        if user is None:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="authentication required",
            )
        return user

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
        user = store.user_for_session(session_token)
        return {"ok": True, "user": public_user(user) if user else None}

    @app.get("/api/symbols")
    def get_symbols(
        top: int = 10,
        _user: AuthUser = Depends(require_user),
    ) -> dict[str, Any]:
        return top_symbols_payload(client_factory(), top=top)

    @app.get("/api/strategies")
    def get_strategies(_user: AuthUser = Depends(require_user)) -> dict[str, Any]:
        return strategies_payload()

    @app.get("/api/runs")
    def get_runs(_user: AuthUser = Depends(require_user)) -> dict[str, Any]:
        return {"ok": True, "runs": list_runs(output_path)}

    @app.get("/api/live-chart")
    def get_live_chart(
        request: Request,
        _user: AuthUser = Depends(require_user),
    ) -> dict[str, Any]:
        payload = dict(request.query_params)
        return live_chart_payload(
            payload,
            _live_client_for_handler(payload, client_factory),
            output_path,
        )

    @app.get("/api/run")
    def get_run(
        path: str = "",
        _user: AuthUser = Depends(require_user),
    ) -> dict[str, Any]:
        return load_run_details(path, output_path)

    @app.post("/api/backtest")
    def post_backtest(
        payload: dict[str, Any] | None = Body(default=None),
        _user: AuthUser = Depends(require_user),
    ) -> dict[str, Any]:
        return run_backtest_payload(payload or {}, client_factory(), output_path)

    @app.post("/api/paper")
    def post_paper(
        payload: dict[str, Any] | None = Body(default=None),
        _user: AuthUser = Depends(require_user),
    ) -> dict[str, Any]:
        return run_paper_payload(payload or {}, client_factory(), output_path)

    @app.post("/api/strategy-lab")
    def post_strategy_lab(
        payload: dict[str, Any] | None = Body(default=None),
        _user: AuthUser = Depends(require_user),
    ) -> dict[str, Any]:
        return strategy_lab_payload(payload or {}, client_factory())

    @app.post("/api/combination-signals")
    def post_combination_signals(
        payload: dict[str, Any] | None = Body(default=None),
        _user: AuthUser = Depends(require_user),
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


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        max_age=SESSION_TTL_SECONDS,
        path="/",
        samesite="lax",
    )
