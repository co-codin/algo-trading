from __future__ import annotations

import os

from algo_trading.env import load_env_file
from algo_trading.job_queue import DEFAULT_QUEUE_NAME, DEFAULT_REDIS_URL
from algo_trading.logging_config import configure_error_logging


def main() -> None:
    from redis import Redis
    from rq import Queue, Worker

    load_env_file()
    configure_error_logging("worker")
    redis_url = os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)
    queue_name = os.environ.get("RQ_QUEUE", DEFAULT_QUEUE_NAME)
    redis = Redis.from_url(redis_url)
    queue = Queue(queue_name, connection=redis)
    Worker([queue], connection=redis).work()


if __name__ == "__main__":
    main()
