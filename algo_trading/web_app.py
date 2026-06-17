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

from fastapi import BackgroundTasks, Body, Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from algo_trading.alerts import (
    AlertStore,
    InMemoryAlertStore,
    PostgresAlertStore,
    TelegramBotClient,
    TelegramSender,
    build_signal_signature,
    build_telegram_signal_message,
    build_telegram_test_message,
    public_telegram_alert_settings,
)
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
from algo_trading.feedback import (
    FeedbackStore,
    InMemoryFeedbackStore,
    PostgresFeedbackStore,
    public_feedback,
)
from algo_trading.futoi import (
    FutoiRefreshService,
    FUTOI_PRUNE_SECONDS,
    parse_futoi_date,
    public_futoi_record,
)
from algo_trading.historical_store import HistoricalDataStore, historical_store_from_env
from algo_trading.historical_data import HistoricalCsvRefreshService
from algo_trading import jobs as background_jobs
from algo_trading.job_queue import JobQueue, job_queue_from_env
from algo_trading.logging_config import configure_error_logging
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
MOEX_FUTOI_REFRESH_SECONDS = 24 * 60 * 60
MOEX_FUTOI_PRUNE_SECONDS = FUTOI_PRUNE_SECONDS


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
    futoi_service: Any | None = None,
    expiry_check_seconds: float | None = None,
    historical_csv_refresh_seconds: float | None = None,
    historical_csv_prune_seconds: float | None = None,
    futoi_refresh_seconds: float | None = None,
    futoi_prune_seconds: float | None = None,
    historical_store: HistoricalDataStore | None = None,
    feedback_store: FeedbackStore | None = None,
    alert_store: AlertStore | None = None,
    telegram_sender: TelegramSender | None = None,
    job_queue: JobQueue | None = None,
    seed_admin: bool = True,
    admin_seed_password: str | None = None,
    log_dir: str | Path | None = None,
) -> FastAPI:
    load_env_file()
    error_logger = configure_error_logging("app", log_dir=log_dir)
    store = auth_store or auth_store_from_env()
    store.ensure_schema()
    if seed_admin:
        store.seed_admin_user(admin_email(), admin_seed_password or admin_password())
    feedback = feedback_store or feedback_store_from_env()
    feedback.ensure_schema()
    alerts = alert_store or alert_store_from_env()
    alerts.ensure_schema()
    telegram = telegram_sender or TelegramBotClient()
    history_store = historical_store or historical_store_from_env()
    history_store.ensure_schema()
    breadth_service = market_breadth_service or MarketBreadthService(store=history_store)
    csv_service = historical_csv_service or HistoricalCsvRefreshService()
    futoi = futoi_service or FutoiRefreshService(store=history_store)
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
    futoi_interval = (
        futoi_refresh_seconds
        if futoi_refresh_seconds is not None
        else float(os.environ.get("MOEX_FUTOI_REFRESH_SECONDS", MOEX_FUTOI_REFRESH_SECONDS))
    )
    futoi_prune_interval = (
        futoi_prune_seconds
        if futoi_prune_seconds is not None
        else float(os.environ.get("MOEX_FUTOI_PRUNE_SECONDS", MOEX_FUTOI_PRUNE_SECONDS))
    )
    maintenance_interval = min(
        [
            interval
            for interval in (csv_refresh_interval, futoi_interval, futoi_prune_interval)
            if interval > 0
        ],
        default=0,
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
        last_csv_refresh = 0.0
        last_prune = 0.0
        last_futoi = 0.0
        last_futoi_prune = 0.0
        while True:
            await asyncio.sleep(max(0.01, maintenance_interval))
            now = time.monotonic()
            if csv_refresh_interval > 0 and now - last_csv_refresh >= csv_refresh_interval:
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
                last_csv_refresh = now
            refresh_futoi = getattr(futoi, "refresh_daily", None)
            if (
                futoi_interval > 0
                and callable(refresh_futoi)
                and now - last_futoi >= futoi_interval
            ):
                await enqueue_or_run_background_job(
                    background_jobs.refresh_futoi,
                    refresh_futoi,
                    job_id_prefix="refresh-futoi",
                    description="Refresh MOEX FUTOI historical data",
                )
                last_futoi = now
            prune_futoi = getattr(futoi, "prune_history", None)
            if (
                futoi_prune_interval > 0
                and callable(prune_futoi)
                and now - last_futoi_prune >= futoi_prune_interval
            ):
                await enqueue_or_run_background_job(
                    background_jobs.prune_futoi,
                    prune_futoi,
                    job_id_prefix="prune-futoi",
                    description="Prune MOEX FUTOI historical data older than retention",
                )
                last_futoi_prune = now
            if csv_prune_interval > 0 and now - last_prune >= csv_prune_interval:
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
        if maintenance_interval > 0:
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
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        error_logger.error(
            "Unhandled API error %s %s",
            request.method,
            request.url.path,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
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
        background_tasks: BackgroundTasks,
        user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        payload = dict(request.query_params)
        cache_state: dict[str, bool] = {}
        chart_payload = live_chart_payload(
            payload,
            _live_client_for_handler(payload, client_factory),
            historical_store=history_store,
            allow_stale_cache=True,
            cache_state=cache_state,
        )
        if cache_state.get("cache_stale"):
            background_tasks.add_task(refresh_live_chart_cache, payload)
        maybe_send_telegram_rsi_alert(user, chart_payload)
        return chart_payload

    def refresh_live_chart_cache(payload: dict[str, Any]) -> None:
        try:
            live_chart_payload(
                payload,
                _live_client_for_handler(payload, client_factory),
                historical_store=history_store,
            )
        except Exception:
            error_logger.warning("Live chart stale-cache refresh failed", exc_info=True)

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

    @app.get("/api/futoi")
    def get_futoi(
        date: str = "",
        ticker: str = "",
        limit: int = 500,
        _user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        if limit < 0:
            raise ValueError("limit cannot be negative")
        selected_date = parse_futoi_date(date)
        records = futoi.load_records(
            trading_date=selected_date,
            ticker=ticker.strip().upper() or None,
            limit=min(limit, 5000) if limit else None,
        )
        return {"ok": True, "records": [public_futoi_record(record) for record in records]}

    @app.post("/api/feedback")
    def submit_feedback(
        payload: dict[str, Any] | None = Body(default=None),
        user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        feedback_payload = payload or {}
        created = feedback.create_feedback(
            user_id=user.id,
            username=user.username,
            title=str(feedback_payload.get("title") or ""),
            description=optional_text(feedback_payload.get("description")),
        )
        return {"ok": True, "feedback": public_feedback(created)}

    @app.get("/api/alerts/telegram")
    def get_telegram_alert_settings(
        user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "settings": public_telegram_alert_settings(
                alerts.get_telegram_settings(user.id)
            ),
        }

    @app.put("/api/alerts/telegram")
    def update_telegram_alert_settings(
        payload: dict[str, Any] | None = Body(default=None),
        user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        settings_payload = payload or {}
        settings = alerts.upsert_telegram_settings(
            user_id=user.id,
            enabled=bool(settings_payload.get("enabled")),
            bot_token=optional_text(settings_payload.get("bot_token")),
            chat_id=optional_text(settings_payload.get("chat_id")),
        )
        return {"ok": True, "settings": public_telegram_alert_settings(settings)}

    @app.post("/api/alerts/telegram/test")
    def test_telegram_alert(
        user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        settings = alerts.get_telegram_settings(user.id)
        if not settings.enabled or not settings.bot_token or not settings.chat_id:
            raise ValueError("telegram alerts are not configured")
        telegram.send_message(
            settings.bot_token,
            settings.chat_id,
            build_telegram_test_message(user.username),
        )
        return {"ok": True}

    @app.get("/api/admin/feedback")
    def get_admin_feedback(
        _admin: AuthUser = Depends(require_admin_user),
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "feedback": [public_feedback(item) for item in feedback.list_feedback()],
        }

    @app.patch("/api/admin/feedback/{feedback_id}/status")
    def update_admin_feedback_status(
        feedback_id: int,
        payload: dict[str, Any] | None = Body(default=None),
        _admin: AuthUser = Depends(require_admin_user),
    ) -> dict[str, Any]:
        status_payload = payload or {}
        updated = feedback.update_feedback_status(
            feedback_id,
            str(status_payload.get("status") or ""),
        )
        return {"ok": True, "feedback": public_feedback(updated)}

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

    def maybe_send_telegram_rsi_alert(
        user: AuthUser,
        chart_payload: dict[str, Any],
    ) -> None:
        settings = alerts.get_telegram_settings(user.id)
        if not settings.enabled or not settings.bot_token or not settings.chat_id:
            return
        signal = chart_payload.get("rsi_alert_signal")
        if not isinstance(signal, dict):
            return
        market = str(chart_payload.get("market") or "")
        symbol = str(chart_payload.get("symbol") or "")
        interval = str(chart_payload.get("interval") or "")
        signature = build_signal_signature(
            market=market,
            symbol=symbol,
            interval=interval,
            signal=signal,
        )
        if alerts.has_signal_delivery(user.id, signature):
            return
        try:
            telegram.send_message(
                settings.bot_token,
                settings.chat_id,
                build_telegram_signal_message(
                    market=market,
                    symbol=symbol,
                    interval=interval,
                    signal=signal,
                ),
            )
        except Exception:
            return
        alerts.record_signal_delivery(user.id, signature)

    return app


def auth_store_from_env() -> AuthStore:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return PostgresAuthStore(database_url)
    return InMemoryAuthStore()


def feedback_store_from_env() -> FeedbackStore:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return PostgresFeedbackStore(database_url)
    return InMemoryFeedbackStore()


def alert_store_from_env() -> AlertStore:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return PostgresAlertStore(database_url)
    return InMemoryAlertStore()


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
