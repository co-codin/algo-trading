from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from typing import Any, Protocol

DEFAULT_REDIS_URL = "redis://redis:6379/0"
DEFAULT_QUEUE_NAME = "maintenance"
DEFAULT_JOB_TIMEOUT = os.environ.get("RQ_JOB_TIMEOUT", "45m")
DEFAULT_RESULT_TTL_SECONDS = int(os.environ.get("RQ_RESULT_TTL_SECONDS", "3600"))
DEFAULT_FAILURE_TTL_SECONDS = int(os.environ.get("RQ_FAILURE_TTL_SECONDS", "86400"))


class JobQueue(Protocol):
    def enqueue(
        self,
        callback: Callable[[], Any],
        *,
        job_id_prefix: str,
        description: str,
    ) -> str:
        ...


class RqJobQueue:
    def __init__(
        self,
        redis_url: str = DEFAULT_REDIS_URL,
        queue_name: str = DEFAULT_QUEUE_NAME,
    ) -> None:
        from redis import Redis
        from rq import Queue

        self._queue = Queue(queue_name, connection=Redis.from_url(redis_url))

    def enqueue(
        self,
        callback: Callable[[], Any],
        *,
        job_id_prefix: str,
        description: str,
    ) -> str:
        job = self._queue.enqueue(
            callback,
            job_id=f"{_safe_job_id_prefix(job_id_prefix)}-{time.time_ns()}",
            job_timeout=DEFAULT_JOB_TIMEOUT,
            result_ttl=DEFAULT_RESULT_TTL_SECONDS,
            failure_ttl=DEFAULT_FAILURE_TTL_SECONDS,
            description=description,
        )
        return str(job.id)


def job_queue_from_env() -> JobQueue | None:
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        return None
    return RqJobQueue(
        redis_url=redis_url,
        queue_name=os.environ.get("RQ_QUEUE", DEFAULT_QUEUE_NAME).strip()
        or DEFAULT_QUEUE_NAME,
    )


def _safe_job_id_prefix(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    return normalized.strip("-") or "job"
