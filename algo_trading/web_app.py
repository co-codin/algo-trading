from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
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
    build_event_signature,
    build_signal_signature,
    build_telegram_event_message,
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
    public_futoi_instrument,
    public_futoi_record,
)
from algo_trading.historical_store import HistoricalDataStore, historical_store_from_env
from algo_trading.historical_data import HistoricalCsvRefreshService
from algo_trading import jobs as background_jobs
from algo_trading.job_queue import JobQueue, job_queue_from_env
from algo_trading.live_symbols import (
    LiveSymbolStore,
    live_symbol_store_from_env,
    live_symbols_payload,
)
from algo_trading.logging_config import configure_error_logging
from algo_trading.market_breadth import (
    MarketBreadthService,
    default_symbols as default_breadth_symbols,
)
from algo_trading.market_intelligence import (
    build_breadth_confirmation_events,
    build_futoi_position_dashboard,
    build_unusual_futoi_events,
    public_futoi_dashboard,
    public_market_event,
)
from algo_trading.market_reports import (
    build_daily_market_report,
    public_daily_market_report,
)
from algo_trading.response_cache import (
    ResponseCache,
    api_cache_key,
    response_cache_from_env,
)
from algo_trading.ui import (
    WEB_DIST_ROOT,
    is_frontend_route,
    is_vite_asset_route,
    live_chart_payload,
    quant_strategy_ideas_payload,
    strategies_payload,
    top_symbols_payload,
    _live_client_for_handler,
)
from algo_trading.workspaces import (
    WorkspaceStore,
    public_watchlist,
    public_workspace,
    workspace_store_from_env,
)

ADMIN_EMAIL = "cuiyeqing960904@gmail.com"
EXPIRY_CHECK_SECONDS = 60 * 60
HISTORICAL_CSV_REFRESH_SECONDS = 60 * 60
HISTORICAL_CSV_PRUNE_SECONDS = 24 * 60 * 60
MOEX_FUTOI_REFRESH_SECONDS = 24 * 60 * 60
MOEX_FUTOI_PRUNE_SECONDS = FUTOI_PRUNE_SECONDS
DAILY_MARKET_REPORT_REFRESH_SECONDS = 24 * 60 * 60
API_CACHE_TTL_SYMBOLS_SECONDS = 30
API_CACHE_TTL_LIVE_CHART_SECONDS = 10
API_CACHE_TTL_QUANT_STRATEGIES_SECONDS = 30
API_CACHE_TTL_MARKET_BREADTH_SECONDS = 300
API_CACHE_TTL_FUTOI_SECONDS = 60
API_CACHE_TTL_FUTOI_INSTRUMENTS_SECONDS = 300
API_CACHE_TTL_DAILY_REPORT_SECONDS = 300


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
    daily_market_report_refresh_seconds: float | None = None,
    historical_store: HistoricalDataStore | None = None,
    feedback_store: FeedbackStore | None = None,
    alert_store: AlertStore | None = None,
    live_symbol_store: LiveSymbolStore | None = None,
    workspace_store: WorkspaceStore | None = None,
    telegram_sender: TelegramSender | None = None,
    job_queue: JobQueue | None = None,
    response_cache: ResponseCache | None = None,
    seed_admin: bool = True,
    admin_seed_password: str | None = None,
    log_dir: str | Path | None = None,
) -> FastAPI:
    load_env_file()
    error_logger = configure_error_logging("app", log_dir=log_dir)
    store = auth_store or auth_store_from_env()
    store.ensure_schema()
    if seed_admin:
        seed_password = (
            admin_seed_password
            if admin_seed_password is not None
            else admin_password()
        )
        if not seed_password.strip():
            raise ValueError("ADMIN_PASSWORD must be set to seed admin user")
        store.seed_admin_user(admin_email(), seed_password)
    feedback = feedback_store or feedback_store_from_env()
    feedback.ensure_schema()
    alerts = alert_store or alert_store_from_env()
    alerts.ensure_schema()
    symbol_store = live_symbol_store or live_symbol_store_from_env()
    symbol_store.ensure_schema()
    symbol_store.seed_default_symbols()
    saved_state = workspace_store or workspace_store_from_env()
    saved_state.ensure_schema()
    telegram = telegram_sender or TelegramBotClient()
    history_store = historical_store or historical_store_from_env()
    history_store.ensure_schema()
    breadth_service = market_breadth_service or MarketBreadthService(store=history_store)
    csv_service = historical_csv_service or HistoricalCsvRefreshService()
    futoi = futoi_service or FutoiRefreshService(store=history_store)
    background_queue = job_queue if job_queue is not None else job_queue_from_env()
    api_cache = response_cache if response_cache is not None else response_cache_from_env()
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
    report_refresh_interval = (
        daily_market_report_refresh_seconds
        if daily_market_report_refresh_seconds is not None
        else float(
            os.environ.get(
                "DAILY_MARKET_REPORT_REFRESH_SECONDS",
                DAILY_MARKET_REPORT_REFRESH_SECONDS,
            )
        )
    )
    api_cache_ttls = {
        "symbols": env_int("API_CACHE_TTL_SYMBOLS_SECONDS", API_CACHE_TTL_SYMBOLS_SECONDS),
        "live-chart": env_int(
            "API_CACHE_TTL_LIVE_CHART_SECONDS",
            API_CACHE_TTL_LIVE_CHART_SECONDS,
        ),
        "quant-strategies": env_int(
            "API_CACHE_TTL_QUANT_STRATEGIES_SECONDS",
            API_CACHE_TTL_QUANT_STRATEGIES_SECONDS,
        ),
        "market-breadth": env_int(
            "API_CACHE_TTL_MARKET_BREADTH_SECONDS",
            API_CACHE_TTL_MARKET_BREADTH_SECONDS,
        ),
        "futoi": env_int("API_CACHE_TTL_FUTOI_SECONDS", API_CACHE_TTL_FUTOI_SECONDS),
        "futoi-instruments": env_int(
            "API_CACHE_TTL_FUTOI_INSTRUMENTS_SECONDS",
            API_CACHE_TTL_FUTOI_INSTRUMENTS_SECONDS,
        ),
        "daily-report": env_int(
            "API_CACHE_TTL_DAILY_REPORT_SECONDS",
            API_CACHE_TTL_DAILY_REPORT_SECONDS,
        ),
    }
    maintenance_interval = min(
        [
            interval
            for interval in (csv_refresh_interval, futoi_interval, futoi_prune_interval)
            + (report_refresh_interval,)
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

    def require_admin_user(user: AuthUser = Depends(require_active_user)) -> AuthUser:
        if not user.is_admin:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="admin required",
            )
        return user

    def require_platform_admin_user(
        user: AuthUser = Depends(require_admin_user),
    ) -> AuthUser:
        if user.username != admin_email():
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="platform admin required",
            )
        return user

    async def deactivate_expired_users_loop() -> None:
        while True:
            await enqueue_or_run_background_job(
                background_jobs.deactivate_expired_users,
                store.deactivate_expired_users,
                job_id_prefix="deactivate-expired-users",
                description="Deactivate users whose access or free trial has expired",
            )
            await asyncio.sleep(max(1.0, expiry_interval))

    async def maintain_historical_csvs_loop() -> None:
        last_csv_refresh = 0.0
        last_prune = 0.0
        last_futoi = 0.0
        last_futoi_prune = 0.0
        last_report = 0.0
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
            refresh_futoi = getattr(futoi, "refresh_all", None) or getattr(
                futoi,
                "refresh_daily",
                None,
            )
            if (
                futoi_interval > 0
                and callable(refresh_futoi)
                and now - last_futoi >= futoi_interval
            ):
                await enqueue_or_run_background_job(
                    background_jobs.refresh_futoi,
                    refresh_futoi,
                    job_id_prefix="refresh-futoi",
                    description="Refresh MOEX FUTOI instruments and historical data",
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
            if report_refresh_interval > 0 and now - last_report >= report_refresh_interval:
                await enqueue_or_run_background_job(
                    background_jobs.generate_daily_market_report,
                    background_jobs.generate_daily_market_report,
                    job_id_prefix="generate-daily-market-report",
                    description="Generate Russian daily market intelligence report",
                )
                last_report = now
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

    def cached_api_payload(
        request: Request,
        namespace: str,
        loader: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        ttl_seconds = api_cache_ttls.get(namespace, 0)
        if api_cache is None or ttl_seconds <= 0:
            return loader()
        key = api_cache_key(namespace, request.query_params.multi_items())
        try:
            cached = api_cache.get_json(key)
        except Exception:
            error_logger.warning("API response cache get failed for %s", namespace, exc_info=True)
            cached = None
        if cached is not None:
            return cached
        payload = loader()
        try:
            api_cache.set_json(key, payload, ttl_seconds=ttl_seconds)
        except Exception:
            error_logger.warning("API response cache set failed for %s", namespace, exc_info=True)
            pass
        return payload

    def read_cached_api_payload(
        request: Request,
        namespace: str,
    ) -> tuple[str, dict[str, Any] | None]:
        ttl_seconds = api_cache_ttls.get(namespace, 0)
        key = api_cache_key(namespace, request.query_params.multi_items())
        if api_cache is None or ttl_seconds <= 0:
            return key, None
        try:
            return key, api_cache.get_json(key)
        except Exception:
            error_logger.warning("API response cache get failed for %s", namespace, exc_info=True)
            return key, None

    def write_cached_api_payload(
        namespace: str,
        key: str,
        payload: dict[str, Any],
    ) -> None:
        ttl_seconds = api_cache_ttls.get(namespace, 0)
        if api_cache is None or ttl_seconds <= 0:
            return
        try:
            api_cache.set_json(key, payload, ttl_seconds=ttl_seconds)
        except Exception:
            error_logger.warning("API response cache set failed for %s", namespace, exc_info=True)
            pass

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

    @app.get("/api/admin/settings/free-trial")
    def get_admin_free_trial_settings(
        _admin: AuthUser = Depends(require_platform_admin_user),
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "settings": {
                "is_free_trial_enabled": store.is_free_trial_enabled(),
            },
        }

    @app.put("/api/admin/settings/free-trial")
    def update_admin_free_trial_settings(
        payload: dict[str, Any] | None = Body(default=None),
        _admin: AuthUser = Depends(require_platform_admin_user),
    ) -> dict[str, Any]:
        settings = payload or {}
        enabled = settings.get("is_free_trial_enabled")
        if not isinstance(enabled, bool):
            raise ValueError("is_free_trial_enabled must be a boolean")
        return {
            "ok": True,
            "settings": {
                "is_free_trial_enabled": store.set_free_trial_enabled(enabled),
            },
        }

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
        request: Request,
        top: int = 10,
        _user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        return cached_api_payload(
            request,
            "symbols",
            lambda: top_symbols_payload(client_factory(), top=top),
        )

    @app.get("/api/live-symbols")
    def get_live_symbols(
        _user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        return live_symbols_payload(symbol_store)

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
        cache_key, cached = read_cached_api_payload(request, "live-chart")
        if cached is not None:
            maybe_send_telegram_rsi_alert(user, cached)
            maybe_send_telegram_market_events(user, cached.get("events"))
            return cached
        cache_state: dict[str, bool] = {}
        chart_payload = live_chart_payload(
            payload,
            _live_client_for_handler(payload, client_factory),
            historical_store=history_store,
            allow_stale_cache=True,
            cache_state=cache_state,
        )
        if cache_state.get("cache_stale"):
            background_tasks.add_task(refresh_live_chart_cache, payload, cache_key)
        else:
            write_cached_api_payload("live-chart", cache_key, chart_payload)
        maybe_send_telegram_rsi_alert(user, chart_payload)
        maybe_send_telegram_market_events(user, chart_payload.get("events"))
        return chart_payload

    @app.get("/api/quant-strategies")
    def get_quant_strategies(
        request: Request,
        _user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        payload = dict(request.query_params)
        return cached_api_payload(
            request,
            "quant-strategies",
            lambda: quant_strategy_ideas_payload(
                payload,
                _live_client_for_handler(payload, client_factory),
                historical_store=history_store,
            ),
        )

    def refresh_live_chart_cache(payload: dict[str, Any], cache_key: str) -> None:
        try:
            refreshed_payload = live_chart_payload(
                payload,
                _live_client_for_handler(payload, client_factory),
                historical_store=history_store,
            )
            write_cached_api_payload("live-chart", cache_key, refreshed_payload)
        except Exception:
            error_logger.warning("Live chart stale-cache refresh failed", exc_info=True)

    @app.get("/api/market-breadth")
    def get_market_breadth(
        request: Request,
        symbols: str = "",
        user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        requested_symbols = (
            [symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()]
            if symbols
            else None
        )
        payload = cached_api_payload(
            request,
            "market-breadth",
            lambda: breadth_service.payload(requested_symbols),
        )
        breadth_events = build_breadth_confirmation_events(
            {
                symbol: history_store.load_breadth_bars(symbol)
                for symbol in (requested_symbols or default_breadth_symbols())
            }
        )
        maybe_send_telegram_market_events(
            user,
            [public_market_event(event) for event in breadth_events],
        )
        return payload

    @app.get("/api/futoi")
    def get_futoi(
        request: Request,
        date: str = "",
        ticker: str = "",
        limit: int = 500,
        history_days: int = 365,
        user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        if limit < 0:
            raise ValueError("limit cannot be negative")
        if history_days < 0:
            raise ValueError("history_days cannot be negative")
        selected_date = parse_futoi_date(date)
        selected_ticker = ticker.strip().upper() or None

        def futoi_payload() -> dict[str, Any]:
            records = futoi.load_records(
                trading_date=selected_date,
                ticker=selected_ticker,
                limit=min(limit, 5000) if limit else None,
            )
            chart_records = (
                futoi.load_ticker_history(
                    selected_ticker,
                    end_date=selected_date,
                    days=min(history_days or 365, 730),
                )
                if selected_ticker
                else records
            )
            dashboard = build_futoi_position_dashboard(
                chart_records,
                futoi.list_instruments(),
            )
            return {
                "ok": True,
                "records": [public_futoi_record(record) for record in records],
                "chart_records": [
                    public_futoi_record(record)
                    for record in chart_records
                ],
                "dashboard": public_futoi_dashboard(dashboard),
            }

        payload = cached_api_payload(
            request,
            "futoi",
            futoi_payload,
        )
        dashboard = payload.get("dashboard")
        events = dashboard.get("events") if isinstance(dashboard, dict) else None
        maybe_send_telegram_market_events(user, events)
        return payload

    @app.get("/api/futoi/instruments")
    def get_futoi_instruments(
        request: Request,
        _user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        return cached_api_payload(
            request,
            "futoi-instruments",
            lambda: {
                "ok": True,
                "instruments": [
                    public_futoi_instrument(instrument)
                    for instrument in futoi.list_instruments()
                ],
            },
        )

    @app.get("/api/reports/daily")
    def get_daily_market_report(
        request: Request,
        date: str = "",
        _user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        selected_date = parse_futoi_date(date) or datetime.now(timezone.utc).date()

        def report_payload() -> dict[str, Any]:
            start_date = selected_date - timedelta(days=7)
            futoi_records = history_store.load_futoi_records(
                start_date=start_date,
                end_date=selected_date,
                limit=None,
            )
            algopack_records = history_store.load_algopack_records(
                start_date=selected_date,
                end_date=selected_date,
                limit=None,
            )
            breadth_bars_by_symbol = {
                symbol: history_store.load_breadth_bars(symbol)
                for symbol in default_breadth_symbols()[:8]
            }
            report = build_daily_market_report(
                trading_date=selected_date,
                futoi_records=futoi_records,
                algopack_records=algopack_records,
                breadth_bars_by_symbol=breadth_bars_by_symbol,
                triggered_events=build_unusual_futoi_events(futoi_records),
            )
            return {"ok": True, "report": public_daily_market_report(report)}

        return cached_api_payload(request, "daily-report", report_payload)

    @app.get("/api/workspaces")
    def get_workspaces(user: AuthUser = Depends(require_active_user)) -> dict[str, Any]:
        return {
            "ok": True,
            "workspaces": [
                public_workspace(workspace)
                for workspace in saved_state.list_workspaces(user.id)
            ],
        }

    @app.post("/api/workspaces")
    def create_workspace(
        payload: dict[str, Any] | None = Body(default=None),
        user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        workspace_payload = payload or {}
        workspace = saved_state.create_workspace(
            user_id=user.id,
            name=str(workspace_payload.get("name") or ""),
            market=str(workspace_payload.get("market") or ""),
            symbol=str(workspace_payload.get("symbol") or ""),
            settings=workspace_payload.get("settings") or {},
        )
        return {"ok": True, "workspace": public_workspace(workspace)}

    @app.put("/api/workspaces/{workspace_id}")
    def update_workspace(
        workspace_id: str,
        payload: dict[str, Any] | None = Body(default=None),
        user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        workspace_payload = payload or {}
        workspace = saved_state.update_workspace(
            user_id=user.id,
            workspace_id=workspace_id,
            name=str(workspace_payload.get("name") or ""),
            market=str(workspace_payload.get("market") or ""),
            symbol=str(workspace_payload.get("symbol") or ""),
            settings=workspace_payload.get("settings") or {},
        )
        return {"ok": True, "workspace": public_workspace(workspace)}

    @app.delete("/api/workspaces/{workspace_id}")
    def delete_workspace(
        workspace_id: str,
        user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "deleted": saved_state.delete_workspace(user.id, workspace_id),
        }

    @app.get("/api/watchlists")
    def get_watchlists(user: AuthUser = Depends(require_active_user)) -> dict[str, Any]:
        return {
            "ok": True,
            "watchlists": [
                public_watchlist(watchlist)
                for watchlist in saved_state.list_watchlists(user.id)
            ],
        }

    @app.post("/api/watchlists")
    def create_watchlist(
        payload: dict[str, Any] | None = Body(default=None),
        user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        watchlist_payload = payload or {}
        watchlist = saved_state.create_watchlist(
            user_id=user.id,
            name=str(watchlist_payload.get("name") or ""),
            market=str(watchlist_payload.get("market") or ""),
            symbols=watchlist_payload.get("symbols") or [],
        )
        return {"ok": True, "watchlist": public_watchlist(watchlist)}

    @app.put("/api/watchlists/{watchlist_id}")
    def update_watchlist(
        watchlist_id: str,
        payload: dict[str, Any] | None = Body(default=None),
        user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        watchlist_payload = payload or {}
        watchlist = saved_state.update_watchlist(
            user_id=user.id,
            watchlist_id=watchlist_id,
            name=str(watchlist_payload.get("name") or ""),
            market=str(watchlist_payload.get("market") or ""),
            symbols=watchlist_payload.get("symbols") or [],
        )
        return {"ok": True, "watchlist": public_watchlist(watchlist)}

    @app.delete("/api/watchlists/{watchlist_id}")
    def delete_watchlist(
        watchlist_id: str,
        user: AuthUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "deleted": saved_state.delete_watchlist(user.id, watchlist_id),
        }

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

    def maybe_send_telegram_market_events(
        user: AuthUser,
        events: Any,
    ) -> None:
        settings = alerts.get_telegram_settings(user.id)
        if not settings.enabled or not settings.bot_token or not settings.chat_id:
            return
        if not isinstance(events, list):
            return
        for event in events:
            if not isinstance(event, dict):
                continue
            try:
                signature = build_event_signature(event)
            except ValueError:
                continue
            if alerts.has_signal_delivery(user.id, signature):
                continue
            try:
                telegram.send_message(
                    settings.bot_token,
                    settings.chat_id,
                    build_telegram_event_message(event),
                )
            except Exception:
                continue
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


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def admin_email() -> str:
    return os.environ.get("ADMIN_EMAIL", ADMIN_EMAIL).strip().lower()


def admin_password() -> str:
    value = os.environ.get("ADMIN_PASSWORD")
    if value is None or not value.strip():
        raise ValueError("ADMIN_PASSWORD must be set to seed admin user")
    return value


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
