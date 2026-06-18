from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


DEFAULT_LOG_DIR = "logs"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5


def log_dir_from_env() -> Path:
    return Path(os.environ.get("APP_LOG_DIR", DEFAULT_LOG_DIR)).expanduser()


def log_file_path(service_name: str, log_dir: str | Path | None = None) -> Path:
    normalized = _normalize_service_name(service_name)
    base_dir = Path(log_dir) if log_dir is not None else log_dir_from_env()
    return base_dir / f"{normalized}.log"


def configure_error_logging(
    service_name: str,
    log_dir: str | Path | None = None,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> logging.Logger:
    log_path = log_file_path(service_name, log_dir=log_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_log_path = str(log_path.resolve())

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if not _has_algo_file_handler(root_logger, resolved_log_path):
        handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            delay=True,
        )
        handler.setLevel(logging.WARNING)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        setattr(handler, "_algo_trading_log_path", resolved_log_path)
        root_logger.addHandler(handler)

    logger = logging.getLogger(f"algo_trading.{_normalize_service_name(service_name)}")
    logger.setLevel(logging.INFO)
    return logger


def _has_algo_file_handler(logger: logging.Logger, resolved_log_path: str) -> bool:
    return any(
        getattr(handler, "_algo_trading_log_path", None) == resolved_log_path
        for handler in logger.handlers
    )


def _normalize_service_name(service_name: str) -> str:
    normalized = service_name.strip().lower().replace("-", "_")
    if not normalized or not normalized.replace("_", "").isalnum():
        raise ValueError("service_name must contain only letters, numbers, '-' or '_'")
    return normalized
