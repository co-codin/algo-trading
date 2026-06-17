from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Protocol, cast

_MAX_BOT_TOKEN_LENGTH = 256
_MAX_CHAT_ID_LENGTH = 128
_TELEGRAM_API_ROOT = "https://api.telegram.org"


@dataclass(frozen=True)
class TelegramAlertSettings:
    user_id: int
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""
    updated_at: datetime | None = None


class AlertStore(Protocol):
    def ensure_schema(self) -> None: ...

    def get_telegram_settings(self, user_id: int) -> TelegramAlertSettings: ...

    def upsert_telegram_settings(
        self,
        *,
        user_id: int,
        enabled: bool,
        bot_token: str | None = None,
        chat_id: str | None = None,
    ) -> TelegramAlertSettings: ...

    def has_signal_delivery(self, user_id: int, signature: str) -> bool: ...

    def record_signal_delivery(self, user_id: int, signature: str) -> None: ...


class TelegramSender(Protocol):
    def send_message(self, bot_token: str, chat_id: str, text: str) -> None: ...


class InMemoryAlertStore:
    def __init__(self) -> None:
        self._telegram_settings: dict[int, TelegramAlertSettings] = {}
        self._signal_deliveries: set[tuple[int, str]] = set()

    def ensure_schema(self) -> None:
        return None

    def get_telegram_settings(self, user_id: int) -> TelegramAlertSettings:
        return self._telegram_settings.get(user_id, TelegramAlertSettings(user_id=user_id))

    def upsert_telegram_settings(
        self,
        *,
        user_id: int,
        enabled: bool,
        bot_token: str | None = None,
        chat_id: str | None = None,
    ) -> TelegramAlertSettings:
        existing = self.get_telegram_settings(user_id)
        normalized = normalize_telegram_alert_settings(
            user_id=user_id,
            enabled=enabled,
            bot_token=bot_token,
            chat_id=chat_id,
            existing=existing,
        )
        self._telegram_settings[user_id] = normalized
        return normalized

    def has_signal_delivery(self, user_id: int, signature: str) -> bool:
        return (user_id, normalize_signal_signature(signature)) in self._signal_deliveries

    def record_signal_delivery(self, user_id: int, signature: str) -> None:
        self._signal_deliveries.add((user_id, normalize_signal_signature(signature)))


class PostgresAlertStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS telegram_alert_settings (
                        user_id BIGINT PRIMARY KEY,
                        enabled BOOLEAN NOT NULL DEFAULT false,
                        bot_token TEXT NOT NULL DEFAULT '',
                        chat_id TEXT NOT NULL DEFAULT '',
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS telegram_alert_deliveries (
                        user_id BIGINT NOT NULL,
                        signal_signature TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        PRIMARY KEY (user_id, signal_signature)
                    )
                    """
                )

    def get_telegram_settings(self, user_id: int) -> TelegramAlertSettings:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id,
                           enabled,
                           bot_token,
                           chat_id,
                           updated_at
                    FROM telegram_alert_settings
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cursor.fetchone()
        if row is None:
            return TelegramAlertSettings(user_id=user_id)
        return telegram_settings_from_row(row)

    def upsert_telegram_settings(
        self,
        *,
        user_id: int,
        enabled: bool,
        bot_token: str | None = None,
        chat_id: str | None = None,
    ) -> TelegramAlertSettings:
        existing = self.get_telegram_settings(user_id)
        normalized = normalize_telegram_alert_settings(
            user_id=user_id,
            enabled=enabled,
            bot_token=bot_token,
            chat_id=chat_id,
            existing=existing,
        )
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO telegram_alert_settings (
                        user_id,
                        enabled,
                        bot_token,
                        chat_id,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, now())
                    ON CONFLICT (user_id) DO UPDATE
                    SET enabled = EXCLUDED.enabled,
                        bot_token = EXCLUDED.bot_token,
                        chat_id = EXCLUDED.chat_id,
                        updated_at = now()
                    RETURNING user_id,
                              enabled,
                              bot_token,
                              chat_id,
                              updated_at
                    """,
                    (
                        normalized.user_id,
                        normalized.enabled,
                        normalized.bot_token,
                        normalized.chat_id,
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise ValueError("telegram alert settings update failed")
        return telegram_settings_from_row(row)

    def has_signal_delivery(self, user_id: int, signature: str) -> bool:
        normalized_signature = normalize_signal_signature(signature)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 1
                    FROM telegram_alert_deliveries
                    WHERE user_id = %s
                      AND signal_signature = %s
                    """,
                    (user_id, normalized_signature),
                )
                row = cursor.fetchone()
        return row is not None

    def record_signal_delivery(self, user_id: int, signature: str) -> None:
        normalized_signature = normalize_signal_signature(signature)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO telegram_alert_deliveries (user_id, signal_signature)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id, signal_signature) DO NOTHING
                    """,
                    (user_id, normalized_signature),
                )

    def _connect(self):
        import psycopg  # type: ignore[import-not-found]

        return psycopg.connect(self.database_url)


class TelegramBotClient:
    def __init__(
        self,
        api_root: str = _TELEGRAM_API_ROOT,
        opener: Any = urllib.request.urlopen,
        timeout: int = 15,
    ) -> None:
        self.api_root = api_root.rstrip("/")
        self._opener = opener
        self._timeout = timeout

    def send_message(self, bot_token: str, chat_id: str, text: str) -> None:
        token = normalize_telegram_bot_token(bot_token)
        normalized_chat_id = normalize_telegram_chat_id(chat_id)
        payload = json.dumps(
            {
                "chat_id": normalized_chat_id,
                "text": text,
                "disable_web_page_preview": True,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_root}/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            raise ValueError(f"telegram send failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ValueError("telegram send failed") from exc

        try:
            decoded = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("telegram send returned invalid JSON") from exc
        if not bool(decoded.get("ok")):
            description = str(decoded.get("description") or "unknown error")
            raise ValueError(f"telegram send failed: {description}")


def telegram_settings_from_row(row: Sequence[object]) -> TelegramAlertSettings:
    return TelegramAlertSettings(
        user_id=int(str(row[0])),
        enabled=bool(row[1]),
        bot_token=str(row[2]),
        chat_id=str(row[3]),
        updated_at=cast(datetime | None, row[4]),
    )


def normalize_telegram_alert_settings(
    *,
    user_id: int,
    enabled: bool,
    bot_token: str | None,
    chat_id: str | None,
    existing: TelegramAlertSettings,
) -> TelegramAlertSettings:
    normalized_token = (
        normalize_telegram_bot_token(bot_token)
        if bot_token is not None and str(bot_token).strip()
        else existing.bot_token
    )
    normalized_chat_id = (
        normalize_telegram_chat_id(chat_id)
        if chat_id is not None and str(chat_id).strip()
        else existing.chat_id
    )
    if enabled and not normalized_token:
        raise ValueError("telegram bot token is required")
    if enabled and not normalized_chat_id:
        raise ValueError("telegram chat ID is required")
    return replace(
        existing,
        user_id=user_id,
        enabled=enabled,
        bot_token=normalized_token,
        chat_id=normalized_chat_id,
        updated_at=utcnow(),
    )


def normalize_telegram_bot_token(value: str | None) -> str:
    normalized = "" if value is None else str(value).strip()
    if not normalized:
        raise ValueError("telegram bot token is required")
    if len(normalized) > _MAX_BOT_TOKEN_LENGTH:
        raise ValueError(
            f"telegram bot token must be at most {_MAX_BOT_TOKEN_LENGTH} characters"
        )
    return normalized


def normalize_telegram_chat_id(value: str | None) -> str:
    normalized = "" if value is None else str(value).strip()
    if not normalized:
        raise ValueError("telegram chat ID is required")
    if len(normalized) > _MAX_CHAT_ID_LENGTH:
        raise ValueError(
            f"telegram chat ID must be at most {_MAX_CHAT_ID_LENGTH} characters"
        )
    if any(character.isspace() for character in normalized):
        raise ValueError("telegram chat ID cannot contain whitespace")
    return normalized


def normalize_signal_signature(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("alert signal signature is required")
    return normalized


def public_telegram_alert_settings(
    settings: TelegramAlertSettings,
) -> dict[str, object]:
    return {
        "enabled": settings.enabled,
        "bot_token_configured": bool(settings.bot_token),
        "bot_token_preview": mask_telegram_bot_token(settings.bot_token),
        "chat_id": settings.chat_id,
        "updated_at": isoformat_z(settings.updated_at),
    }


def mask_telegram_bot_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 8:
        return "..." + token[-4:]
    prefix = token.split(":", 1)[0]
    return f"{prefix}:...{token[-4:]}" if prefix else "..." + token[-4:]


def build_signal_signature(
    *,
    market: str,
    symbol: str,
    interval: str,
    signal: Mapping[str, object],
) -> str:
    return normalize_signal_signature(
        "|".join(
            [
                market,
                symbol,
                interval,
                "rsi-reversal",
                str(signal.get("time")),
                str(signal.get("type")),
                str(signal.get("reason")),
            ]
        )
    )


def build_telegram_signal_message(
    *,
    market: str,
    symbol: str,
    interval: str,
    signal: Mapping[str, object],
) -> str:
    signal_type = str(signal.get("type") or "signal")
    reason = str(signal.get("reason") or "rsi_reversal")
    price = signal.get("price")
    signal_time = signal.get("time")
    return "\n".join(
        [
            f"RSI alert: {symbol} {signal_type}",
            f"Market: {market}",
            f"Interval: {interval}",
            f"Price: {price}",
            f"Signal time: {signal_time}",
            f"Reason: {reason}",
        ]
    )


def build_telegram_test_message(username: str) -> str:
    return f"Test alert from algo-trading for {username}"


def isoformat_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
