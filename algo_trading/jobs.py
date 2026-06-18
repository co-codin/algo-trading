from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

from algo_trading.auth import AuthStore, InMemoryAuthStore, PostgresAuthStore
from algo_trading.env import load_env_file
from algo_trading.futoi import FutoiRefreshService
from algo_trading.historical_data import HistoricalCsvRefreshService
from algo_trading.historical_store import historical_store_from_env
from algo_trading.market_breadth import (
    MarketBreadthService,
    default_symbols as default_breadth_symbols,
)
from algo_trading.market_intelligence import build_unusual_futoi_events
from algo_trading.market_reports import build_daily_market_report


def refresh_historical_csvs() -> dict[str, int]:
    return HistoricalCsvRefreshService().refresh_all()


def refresh_market_breadth() -> dict[str, int]:
    return MarketBreadthService(store=historical_store_from_env()).refresh_default_symbols()


def refresh_futoi() -> dict[str, int]:
    return FutoiRefreshService(store=historical_store_from_env()).refresh_all()


def prune_futoi() -> dict[str, int]:
    return FutoiRefreshService(store=historical_store_from_env()).prune_history()


def generate_daily_market_report(trading_date: date | None = None) -> dict[str, object]:
    selected_date = trading_date or datetime.now(timezone.utc).date()
    store = historical_store_from_env()
    futoi_records = store.load_futoi_records(
        start_date=selected_date - timedelta(days=7),
        end_date=selected_date,
        limit=None,
    )
    algopack_records = store.load_algopack_records(
        start_date=selected_date,
        end_date=selected_date,
        limit=None,
    )
    breadth_bars_by_symbol = {
        symbol: store.load_breadth_bars(symbol)
        for symbol in default_breadth_symbols()[:8]
    }
    report = build_daily_market_report(
        trading_date=selected_date,
        futoi_records=futoi_records,
        algopack_records=algopack_records,
        breadth_bars_by_symbol=breadth_bars_by_symbol,
        triggered_events=build_unusual_futoi_events(futoi_records),
    )
    return {
        "date": report.date.isoformat(),
        "language": report.language,
        "sections": len(report.sections),
        "events": len(report.events),
        "triggered_symbols": report.triggered_symbols,
    }


def prune_historical_csvs() -> dict[str, int]:
    return HistoricalCsvRefreshService().prune_all()


def deactivate_expired_users() -> dict[str, int]:
    store = auth_store_from_env()
    store.ensure_schema()
    return {"deactivated": store.deactivate_expired_users()}


def auth_store_from_env() -> AuthStore:
    load_env_file()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return PostgresAuthStore(database_url)
    return InMemoryAuthStore()
