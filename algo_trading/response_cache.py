from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from typing import Any, Protocol
from urllib.parse import urlencode

DEFAULT_API_CACHE_PREFIX = "algo-trading:api:"


class ResponseCache(Protocol):
    def get_json(self, key: str) -> dict[str, Any] | None:
        ...

    def set_json(
        self,
        key: str,
        payload: dict[str, Any],
        *,
        ttl_seconds: int,
    ) -> None:
        ...


class RedisResponseCache:
    def __init__(
        self,
        redis_url: str,
        *,
        prefix: str = DEFAULT_API_CACHE_PREFIX,
    ) -> None:
        from redis import Redis

        self._client = Redis.from_url(redis_url)
        self._prefix = prefix

    def get_json(self, key: str) -> dict[str, Any] | None:
        try:
            raw = self._client.get(self._prefixed_key(key))
        except Exception:
            return None
        if raw is None:
            return None
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            payload = json.loads(text)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def set_json(
        self,
        key: str,
        payload: dict[str, Any],
        *,
        ttl_seconds: int,
    ) -> None:
        if ttl_seconds <= 0:
            return
        try:
            serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
            self._client.setex(self._prefixed_key(key), ttl_seconds, serialized)
        except Exception:
            return

    def _prefixed_key(self, key: str) -> str:
        return f"{self._prefix}{key}"


def response_cache_from_env() -> ResponseCache | None:
    if not _env_flag_enabled("API_RESPONSE_CACHE_ENABLED"):
        return None
    redis_url = (
        os.environ.get("API_CACHE_REDIS_URL", "").strip()
        or os.environ.get("REDIS_URL", "").strip()
    )
    if not redis_url:
        return None
    return RedisResponseCache(
        redis_url,
        prefix=os.environ.get("API_CACHE_PREFIX", DEFAULT_API_CACHE_PREFIX),
    )


def api_cache_key(namespace: str, query_items: Iterable[tuple[str, str]]) -> str:
    query = urlencode(sorted((str(key), str(value)) for key, value in query_items))
    digest = hashlib.sha256(f"{namespace}?{query}".encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"


def _env_flag_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
