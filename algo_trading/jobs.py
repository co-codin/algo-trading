from __future__ import annotations

import os

from algo_trading.auth import AuthStore, InMemoryAuthStore, PostgresAuthStore
from algo_trading.env import load_env_file
from algo_trading.historical_data import HistoricalCsvRefreshService
from algo_trading.historical_store import historical_store_from_env
from algo_trading.market_breadth import MarketBreadthService


def refresh_historical_csvs() -> dict[str, int]:
    return HistoricalCsvRefreshService().refresh_all()


def refresh_market_breadth() -> dict[str, int]:
    return MarketBreadthService(store=historical_store_from_env()).refresh_default_symbols()


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
