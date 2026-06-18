from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Protocol, cast

from algo_trading.env import load_env_file

_MAX_NAME_LENGTH = 80
_MAX_MARKET_LENGTH = 80
_MAX_SYMBOL_LENGTH = 64
_MAX_SYMBOLS = 100


@dataclass(frozen=True)
class SavedWorkspace:
    id: str
    user_id: int
    name: str
    market: str
    symbol: str
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SavedWatchlist:
    id: str
    user_id: int
    name: str
    market: str
    symbols: list[str]
    created_at: datetime
    updated_at: datetime


class WorkspaceStore(Protocol):
    def ensure_schema(self) -> None: ...

    def create_workspace(
        self,
        *,
        user_id: int,
        name: str,
        market: str,
        symbol: str,
        settings: Mapping[str, Any],
    ) -> SavedWorkspace: ...

    def update_workspace(
        self,
        *,
        user_id: int,
        workspace_id: str,
        name: str,
        market: str,
        symbol: str,
        settings: Mapping[str, Any],
    ) -> SavedWorkspace: ...

    def delete_workspace(self, user_id: int, workspace_id: str) -> bool: ...

    def list_workspaces(self, user_id: int) -> list[SavedWorkspace]: ...

    def create_watchlist(
        self,
        *,
        user_id: int,
        name: str,
        market: str,
        symbols: Sequence[str],
    ) -> SavedWatchlist: ...

    def update_watchlist(
        self,
        *,
        user_id: int,
        watchlist_id: str,
        name: str,
        market: str,
        symbols: Sequence[str],
    ) -> SavedWatchlist: ...

    def delete_watchlist(self, user_id: int, watchlist_id: str) -> bool: ...

    def list_watchlists(self, user_id: int) -> list[SavedWatchlist]: ...


class InMemoryWorkspaceStore:
    def __init__(self) -> None:
        self._next_workspace_id = 1
        self._next_watchlist_id = 1
        self._workspaces: dict[str, SavedWorkspace] = {}
        self._watchlists: dict[str, SavedWatchlist] = {}

    def ensure_schema(self) -> None:
        return None

    def create_workspace(
        self,
        *,
        user_id: int,
        name: str,
        market: str,
        symbol: str,
        settings: Mapping[str, Any],
    ) -> SavedWorkspace:
        workspace = SavedWorkspace(
            id=str(self._next_workspace_id),
            user_id=normalize_user_id(user_id),
            name=normalize_name(name, "workspace name"),
            market=normalize_market(market),
            symbol=normalize_symbol(symbol),
            settings=normalize_settings(settings, "workspace settings"),
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        self._next_workspace_id += 1
        self._workspaces[workspace.id] = workspace
        return workspace

    def update_workspace(
        self,
        *,
        user_id: int,
        workspace_id: str,
        name: str,
        market: str,
        symbol: str,
        settings: Mapping[str, Any],
    ) -> SavedWorkspace:
        existing = self._workspaces.get(normalize_record_id(workspace_id, "workspace"))
        if existing is None or existing.user_id != normalize_user_id(user_id):
            raise ValueError("unknown workspace")
        updated = replace(
            existing,
            name=normalize_name(name, "workspace name"),
            market=normalize_market(market),
            symbol=normalize_symbol(symbol),
            settings=normalize_settings(settings, "workspace settings"),
            updated_at=utcnow(),
        )
        self._workspaces[updated.id] = updated
        return updated

    def delete_workspace(self, user_id: int, workspace_id: str) -> bool:
        normalized_id = normalize_record_id(workspace_id, "workspace")
        existing = self._workspaces.get(normalized_id)
        if existing is None or existing.user_id != normalize_user_id(user_id):
            return False
        del self._workspaces[normalized_id]
        return True

    def list_workspaces(self, user_id: int) -> list[SavedWorkspace]:
        normalized_user_id = normalize_user_id(user_id)
        return sorted(
            [
                workspace
                for workspace in self._workspaces.values()
                if workspace.user_id == normalized_user_id
            ],
            key=lambda workspace: (workspace.updated_at, int(workspace.id)),
            reverse=True,
        )

    def create_watchlist(
        self,
        *,
        user_id: int,
        name: str,
        market: str,
        symbols: Sequence[str],
    ) -> SavedWatchlist:
        watchlist = SavedWatchlist(
            id=str(self._next_watchlist_id),
            user_id=normalize_user_id(user_id),
            name=normalize_name(name, "watchlist name"),
            market=normalize_market(market),
            symbols=normalize_symbol_list(symbols),
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        self._next_watchlist_id += 1
        self._watchlists[watchlist.id] = watchlist
        return watchlist

    def update_watchlist(
        self,
        *,
        user_id: int,
        watchlist_id: str,
        name: str,
        market: str,
        symbols: Sequence[str],
    ) -> SavedWatchlist:
        existing = self._watchlists.get(normalize_record_id(watchlist_id, "watchlist"))
        if existing is None or existing.user_id != normalize_user_id(user_id):
            raise ValueError("unknown watchlist")
        updated = replace(
            existing,
            name=normalize_name(name, "watchlist name"),
            market=normalize_market(market),
            symbols=normalize_symbol_list(symbols),
            updated_at=utcnow(),
        )
        self._watchlists[updated.id] = updated
        return updated

    def delete_watchlist(self, user_id: int, watchlist_id: str) -> bool:
        normalized_id = normalize_record_id(watchlist_id, "watchlist")
        existing = self._watchlists.get(normalized_id)
        if existing is None or existing.user_id != normalize_user_id(user_id):
            return False
        del self._watchlists[normalized_id]
        return True

    def list_watchlists(self, user_id: int) -> list[SavedWatchlist]:
        normalized_user_id = normalize_user_id(user_id)
        return sorted(
            [
                watchlist
                for watchlist in self._watchlists.values()
                if watchlist.user_id == normalized_user_id
            ],
            key=lambda watchlist: (watchlist.updated_at, int(watchlist.id)),
            reverse=True,
        )


class PostgresWorkspaceStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_workspaces (
                        id BIGSERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        name TEXT NOT NULL,
                        market TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        settings JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS user_workspaces_user_updated_idx
                    ON user_workspaces(user_id, updated_at DESC)
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_watchlists (
                        id BIGSERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        name TEXT NOT NULL,
                        market TEXT NOT NULL,
                        symbols JSONB NOT NULL DEFAULT '[]'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS user_watchlists_user_updated_idx
                    ON user_watchlists(user_id, updated_at DESC)
                    """
                )

    def create_workspace(
        self,
        *,
        user_id: int,
        name: str,
        market: str,
        symbol: str,
        settings: Mapping[str, Any],
    ) -> SavedWorkspace:
        normalized_settings = normalize_settings(settings, "workspace settings")
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO user_workspaces (
                        user_id,
                        name,
                        market,
                        symbol,
                        settings
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    RETURNING id,
                              user_id,
                              name,
                              market,
                              symbol,
                              settings,
                              created_at,
                              updated_at
                    """,
                    (
                        normalize_user_id(user_id),
                        normalize_name(name, "workspace name"),
                        normalize_market(market),
                        normalize_symbol(symbol),
                        json.dumps(normalized_settings, ensure_ascii=True),
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise ValueError("workspace save failed")
        return workspace_from_row(row)

    def update_workspace(
        self,
        *,
        user_id: int,
        workspace_id: str,
        name: str,
        market: str,
        symbol: str,
        settings: Mapping[str, Any],
    ) -> SavedWorkspace:
        normalized_settings = normalize_settings(settings, "workspace settings")
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE user_workspaces
                    SET name = %s,
                        market = %s,
                        symbol = %s,
                        settings = %s::jsonb,
                        updated_at = now()
                    WHERE id = %s
                      AND user_id = %s
                    RETURNING id,
                              user_id,
                              name,
                              market,
                              symbol,
                              settings,
                              created_at,
                              updated_at
                    """,
                    (
                        normalize_name(name, "workspace name"),
                        normalize_market(market),
                        normalize_symbol(symbol),
                        json.dumps(normalized_settings, ensure_ascii=True),
                        normalize_record_id(workspace_id, "workspace"),
                        normalize_user_id(user_id),
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise ValueError("unknown workspace")
        return workspace_from_row(row)

    def delete_workspace(self, user_id: int, workspace_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM user_workspaces
                    WHERE id = %s
                      AND user_id = %s
                    """,
                    (
                        normalize_record_id(workspace_id, "workspace"),
                        normalize_user_id(user_id),
                    ),
                )
                return cursor.rowcount > 0

    def list_workspaces(self, user_id: int) -> list[SavedWorkspace]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id,
                           user_id,
                           name,
                           market,
                           symbol,
                           settings,
                           created_at,
                           updated_at
                    FROM user_workspaces
                    WHERE user_id = %s
                    ORDER BY updated_at DESC, id DESC
                    """,
                    (normalize_user_id(user_id),),
                )
                rows = cursor.fetchall()
        return [workspace_from_row(row) for row in rows]

    def create_watchlist(
        self,
        *,
        user_id: int,
        name: str,
        market: str,
        symbols: Sequence[str],
    ) -> SavedWatchlist:
        normalized_symbols = normalize_symbol_list(symbols)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO user_watchlists (
                        user_id,
                        name,
                        market,
                        symbols
                    )
                    VALUES (%s, %s, %s, %s::jsonb)
                    RETURNING id,
                              user_id,
                              name,
                              market,
                              symbols,
                              created_at,
                              updated_at
                    """,
                    (
                        normalize_user_id(user_id),
                        normalize_name(name, "watchlist name"),
                        normalize_market(market),
                        json.dumps(normalized_symbols, ensure_ascii=True),
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise ValueError("watchlist save failed")
        return watchlist_from_row(row)

    def update_watchlist(
        self,
        *,
        user_id: int,
        watchlist_id: str,
        name: str,
        market: str,
        symbols: Sequence[str],
    ) -> SavedWatchlist:
        normalized_symbols = normalize_symbol_list(symbols)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE user_watchlists
                    SET name = %s,
                        market = %s,
                        symbols = %s::jsonb,
                        updated_at = now()
                    WHERE id = %s
                      AND user_id = %s
                    RETURNING id,
                              user_id,
                              name,
                              market,
                              symbols,
                              created_at,
                              updated_at
                    """,
                    (
                        normalize_name(name, "watchlist name"),
                        normalize_market(market),
                        json.dumps(normalized_symbols, ensure_ascii=True),
                        normalize_record_id(watchlist_id, "watchlist"),
                        normalize_user_id(user_id),
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise ValueError("unknown watchlist")
        return watchlist_from_row(row)

    def delete_watchlist(self, user_id: int, watchlist_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM user_watchlists
                    WHERE id = %s
                      AND user_id = %s
                    """,
                    (
                        normalize_record_id(watchlist_id, "watchlist"),
                        normalize_user_id(user_id),
                    ),
                )
                return cursor.rowcount > 0

    def list_watchlists(self, user_id: int) -> list[SavedWatchlist]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id,
                           user_id,
                           name,
                           market,
                           symbols,
                           created_at,
                           updated_at
                    FROM user_watchlists
                    WHERE user_id = %s
                    ORDER BY updated_at DESC, id DESC
                    """,
                    (normalize_user_id(user_id),),
                )
                rows = cursor.fetchall()
        return [watchlist_from_row(row) for row in rows]

    def _connect(self):
        import psycopg  # type: ignore[import-not-found]

        return psycopg.connect(self.database_url)


def workspace_store_from_env() -> WorkspaceStore:
    load_env_file()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return PostgresWorkspaceStore(database_url)
    return InMemoryWorkspaceStore()


def workspace_from_row(row: Sequence[object]) -> SavedWorkspace:
    return SavedWorkspace(
        id=str(row[0]),
        user_id=int(str(row[1])),
        name=str(row[2]),
        market=str(row[3]),
        symbol=str(row[4]),
        settings=normalize_settings(row[5], "workspace settings"),
        created_at=cast(datetime, row[6]),
        updated_at=cast(datetime, row[7]),
    )


def watchlist_from_row(row: Sequence[object]) -> SavedWatchlist:
    return SavedWatchlist(
        id=str(row[0]),
        user_id=int(str(row[1])),
        name=str(row[2]),
        market=str(row[3]),
        symbols=normalize_symbol_list(normalize_json_value(row[4], "watchlist symbols")),
        created_at=cast(datetime, row[5]),
        updated_at=cast(datetime, row[6]),
    )


def public_workspace(workspace: SavedWorkspace) -> dict[str, object]:
    return {
        "id": workspace.id,
        "name": workspace.name,
        "market": workspace.market,
        "symbol": workspace.symbol,
        "settings": workspace.settings,
        "created_at": isoformat_z(workspace.created_at),
        "updated_at": isoformat_z(workspace.updated_at),
    }


def public_watchlist(watchlist: SavedWatchlist) -> dict[str, object]:
    return {
        "id": watchlist.id,
        "name": watchlist.name,
        "market": watchlist.market,
        "symbols": watchlist.symbols,
        "created_at": isoformat_z(watchlist.created_at),
        "updated_at": isoformat_z(watchlist.updated_at),
    }


def normalize_user_id(value: int) -> int:
    normalized = int(value)
    if normalized <= 0:
        raise ValueError("user_id must be positive")
    return normalized


def normalize_record_id(value: str, label: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{label} id is required")
    if not normalized.isdigit():
        raise ValueError(f"{label} id is invalid")
    return normalized


def normalize_name(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    if len(normalized) > _MAX_NAME_LENGTH:
        raise ValueError(f"{label} must be at most {_MAX_NAME_LENGTH} characters")
    return normalized


def normalize_market(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        raise ValueError("market is required")
    if len(normalized) > _MAX_MARKET_LENGTH:
        raise ValueError(f"market must be at most {_MAX_MARKET_LENGTH} characters")
    return normalized


def normalize_symbol(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    if len(normalized) > _MAX_SYMBOL_LENGTH:
        raise ValueError(f"symbol must be at most {_MAX_SYMBOL_LENGTH} characters")
    return normalized


def normalize_symbol_list(values: Sequence[str] | object) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise ValueError("watchlist symbols are required")
    symbols: list[str] = []
    seen: set[str] = set()
    for value in values:
        symbol = normalize_symbol(str(value))
        if symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    if not symbols:
        raise ValueError("watchlist symbols are required")
    if len(symbols) > _MAX_SYMBOLS:
        raise ValueError(f"watchlist symbols must contain at most {_MAX_SYMBOLS} items")
    return symbols


def normalize_settings(value: Mapping[str, Any] | object, label: str) -> dict[str, Any]:
    decoded = normalize_json_value(value, label)
    if not isinstance(decoded, Mapping):
        raise ValueError(f"{label} are required")
    if not decoded:
        raise ValueError(f"{label} are required")
    try:
        encoded = json.dumps(decoded, allow_nan=False, ensure_ascii=True)
        round_tripped = json.loads(encoded)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be JSON serializable") from exc
    if not isinstance(round_tripped, dict):
        raise ValueError(f"{label} are required")
    return {str(key): value for key, value in round_tripped.items()}


def normalize_json_value(value: object, label: str) -> object:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} must be valid JSON") from exc
    return value


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
