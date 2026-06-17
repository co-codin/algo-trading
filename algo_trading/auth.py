from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Protocol, cast

SESSION_COOKIE_NAME = "algo_session"
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
FREE_TRIAL_SETTING_KEY = "is_free_trial_enabled"

_SCRYPT_N = 16_384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64


@dataclass(frozen=True)
class AuthUser:
    id: int
    username: str
    is_active: bool = False
    is_admin: bool = False
    activated_at: datetime | None = None
    expired_at: datetime | None = None
    free_trial_end_at: datetime | None = None
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None


class AuthStore(Protocol):
    def ensure_schema(self) -> None: ...
    def register_user(self, username: str, password: str) -> AuthUser: ...
    def seed_admin_user(self, username: str, password: str) -> AuthUser: ...
    def authenticate_user(self, username: str, password: str) -> AuthUser: ...
    def create_session(self, user_id: int) -> str: ...
    def user_for_session(self, token: str | None) -> AuthUser | None: ...
    def delete_session(self, token: str | None) -> None: ...
    def list_users(self) -> list[AuthUser]: ...
    def is_free_trial_enabled(self) -> bool: ...
    def set_free_trial_enabled(self, enabled: bool) -> bool: ...
    def set_user_access(
        self,
        user_id: int,
        *,
        is_active: bool,
        activated_at: datetime | None = None,
        expired_at: datetime | None = None,
    ) -> AuthUser: ...
    def update_user_profile(
        self,
        user_id: int,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        middle_name: str | None = None,
    ) -> AuthUser: ...
    def deactivate_expired_users(self, now: datetime | None = None) -> int: ...


@dataclass
class _MemoryUser:
    user: AuthUser
    password_hash: str


@dataclass
class _MemorySession:
    token_hash: str
    user_id: int
    expires_at: datetime


class InMemoryAuthStore:
    def __init__(self, session_ttl_seconds: int = SESSION_TTL_SECONDS) -> None:
        self._session_ttl_seconds = session_ttl_seconds
        self._next_user_id = 1
        self._users_by_name: dict[str, _MemoryUser] = {}
        self._users_by_id: dict[int, _MemoryUser] = {}
        self._sessions: dict[str, _MemorySession] = {}
        self._is_free_trial_enabled = False

    def ensure_schema(self) -> None:
        return None

    def register_user(self, username: str, password: str) -> AuthUser:
        normalized = normalize_username(username)
        validate_password(password)
        if normalized in self._users_by_name:
            raise ValueError("username already exists")
        now = utcnow()
        free_trial_end_at = (
            now + timedelta(days=7) if self._is_free_trial_enabled else None
        )
        user = AuthUser(
            id=self._next_user_id,
            username=normalized,
            is_active=self._is_free_trial_enabled,
            activated_at=now if self._is_free_trial_enabled else None,
            free_trial_end_at=free_trial_end_at,
        )
        self._next_user_id += 1
        record = _MemoryUser(user=user, password_hash=hash_password(password))
        self._users_by_name[normalized] = record
        self._users_by_id[user.id] = record
        return user

    def seed_admin_user(self, username: str, password: str) -> AuthUser:
        normalized = normalize_username(username)
        validate_password(password)
        existing = self._users_by_name.get(normalized)
        if existing is None:
            user = AuthUser(
                id=self._next_user_id,
                username=normalized,
                is_active=True,
                is_admin=True,
                activated_at=utcnow(),
            )
            self._next_user_id += 1
            record = _MemoryUser(user=user, password_hash=hash_password(password))
            self._users_by_name[normalized] = record
            self._users_by_id[user.id] = record
            return user

        existing.user = replace(
            existing.user,
            is_active=True,
            is_admin=True,
            activated_at=existing.user.activated_at or utcnow(),
            free_trial_end_at=None,
        )
        existing.password_hash = hash_password(password)
        return existing.user

    def authenticate_user(self, username: str, password: str) -> AuthUser:
        normalized = normalize_username(username)
        record = self._users_by_name.get(normalized)
        if record is None or not verify_password(password, record.password_hash):
            raise ValueError("invalid username or password")
        return record.user

    def create_session(self, user_id: int) -> str:
        if user_id not in self._users_by_id:
            raise ValueError("unknown user")
        token = secrets.token_urlsafe(48)
        token_hash = hash_session_token(token)
        self._sessions[token_hash] = _MemorySession(
            token_hash=token_hash,
            user_id=user_id,
            expires_at=utcnow() + timedelta(seconds=self._session_ttl_seconds),
        )
        return token

    def user_for_session(self, token: str | None) -> AuthUser | None:
        if not token:
            return None
        token_hash = hash_session_token(token)
        session = self._sessions.get(token_hash)
        if session is None:
            return None
        if session.expires_at <= utcnow():
            self._sessions.pop(token_hash, None)
            return None
        record = self._users_by_id.get(session.user_id)
        return record.user if record else None

    def delete_session(self, token: str | None) -> None:
        if token:
            self._sessions.pop(hash_session_token(token), None)

    def list_users(self) -> list[AuthUser]:
        return [
            record.user
            for _user_id, record in sorted(self._users_by_id.items())
        ]

    def is_free_trial_enabled(self) -> bool:
        return self._is_free_trial_enabled

    def set_free_trial_enabled(self, enabled: bool) -> bool:
        self._is_free_trial_enabled = enabled
        return self._is_free_trial_enabled

    def set_user_access(
        self,
        user_id: int,
        *,
        is_active: bool,
        activated_at: datetime | None = None,
        expired_at: datetime | None = None,
    ) -> AuthUser:
        record = self._users_by_id.get(user_id)
        if record is None:
            raise ValueError("unknown user")
        now = utcnow()
        next_activated_at = activated_at if is_active else None
        if is_active and next_activated_at is None:
            next_activated_at = record.user.activated_at or now
        record.user = replace(
            record.user,
            is_active=is_active,
            activated_at=next_activated_at,
            expired_at=expired_at,
            free_trial_end_at=None if is_active else record.user.free_trial_end_at,
        )
        return record.user

    def update_user_profile(
        self,
        user_id: int,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        middle_name: str | None = None,
    ) -> AuthUser:
        record = self._users_by_id.get(user_id)
        if record is None:
            raise ValueError("unknown user")
        record.user = replace(
            record.user,
            first_name=normalize_profile_name(first_name, "first name"),
            last_name=normalize_profile_name(last_name, "last name"),
            middle_name=normalize_profile_name(middle_name, "middle name"),
        )
        return record.user

    def deactivate_expired_users(self, now: datetime | None = None) -> int:
        current_time = now or utcnow()
        deactivated = 0
        for record in self._users_by_id.values():
            if (
                record.user.is_active
                and (
                    (
                        record.user.expired_at is not None
                        and record.user.expired_at <= current_time
                    )
                    or (
                        record.user.free_trial_end_at is not None
                        and record.user.free_trial_end_at <= current_time
                    )
                )
            ):
                record.user = replace(record.user, is_active=False, activated_at=None)
                deactivated += 1
        return deactivated


class PostgresAuthStore:
    def __init__(
        self,
        database_url: str,
        session_ttl_seconds: int = SESSION_TTL_SECONDS,
    ) -> None:
        self.database_url = database_url
        self._session_ttl_seconds = session_ttl_seconds

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id BIGSERIAL PRIMARY KEY,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT false
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT false
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS expired_at TIMESTAMPTZ
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS free_trial_end_at TIMESTAMPTZ
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS first_name TEXT
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS last_name TEXT
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS middle_name TEXT
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        token_hash TEXT PRIMARY KEY,
                        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        expires_at TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS sessions_user_id_idx
                    ON sessions(user_id)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS sessions_expires_at_idx
                    ON sessions(expires_at)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS users_expired_at_idx
                    ON users(expired_at)
                    WHERE expired_at IS NOT NULL
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS users_free_trial_end_at_idx
                    ON users(free_trial_end_at)
                    WHERE free_trial_end_at IS NOT NULL
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS platform_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cursor.execute(
                    """
                    INSERT INTO platform_settings (key, value)
                    VALUES (%s, 'false')
                    ON CONFLICT (key) DO NOTHING
                    """,
                    (FREE_TRIAL_SETTING_KEY,),
                )

    def register_user(self, username: str, password: str) -> AuthUser:
        normalized = normalize_username(username)
        validate_password(password)
        free_trial_enabled = self.is_free_trial_enabled()
        now = utcnow()
        free_trial_end_at = now + timedelta(days=7) if free_trial_enabled else None
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO users (
                        username,
                        password_hash,
                        is_active,
                        activated_at,
                        free_trial_end_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (username) DO NOTHING
                    RETURNING id,
                              username,
                              is_active,
                              is_admin,
                              activated_at,
                              expired_at,
                              free_trial_end_at,
                              first_name,
                              last_name,
                              middle_name
                    """,
                    (
                        normalized,
                        hash_password(password),
                        free_trial_enabled,
                        now if free_trial_enabled else None,
                        free_trial_end_at,
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise ValueError("username already exists")
        return user_from_row(row)

    def seed_admin_user(self, username: str, password: str) -> AuthUser:
        normalized = normalize_username(username)
        validate_password(password)
        password_hash = hash_password(password)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO users (
                        username,
                        password_hash,
                        is_active,
                        is_admin,
                        activated_at
                    )
                    VALUES (%s, %s, true, true, now())
                    ON CONFLICT (username) DO UPDATE
                    SET password_hash = EXCLUDED.password_hash,
                        is_active = true,
                        is_admin = true,
                        activated_at = COALESCE(users.activated_at, now()),
                        free_trial_end_at = NULL
                    RETURNING id,
                              username,
                              is_active,
                              is_admin,
                              activated_at,
                              expired_at,
                              free_trial_end_at,
                              first_name,
                              last_name,
                              middle_name
                    """,
                    (normalized, password_hash),
                )
                row = cursor.fetchone()
        if row is None:
            raise ValueError("admin seed failed")
        return user_from_row(row)

    def authenticate_user(self, username: str, password: str) -> AuthUser:
        normalized = normalize_username(username)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id,
                           username,
                           is_active,
                           is_admin,
                           activated_at,
                           expired_at,
                           free_trial_end_at,
                           first_name,
                           last_name,
                           middle_name,
                           password_hash
                    FROM users
                    WHERE username = %s
                    """,
                    (normalized,),
                )
                row = cursor.fetchone()
        if row is None or not verify_password(password, str(row[10])):
            raise ValueError("invalid username or password")
        return user_from_row(row)

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(48)
        token_hash = hash_session_token(token)
        expires_at = utcnow() + timedelta(seconds=self._session_ttl_seconds)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO sessions (token_hash, user_id, expires_at)
                    VALUES (%s, %s, %s)
                    """,
                    (token_hash, user_id, expires_at),
                )
        return token

    def user_for_session(self, token: str | None) -> AuthUser | None:
        if not token:
            return None
        token_hash = hash_session_token(token)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM sessions WHERE expires_at <= now()")
                cursor.execute(
                    """
                    SELECT users.id,
                           users.username,
                           users.is_active,
                           users.is_admin,
                           users.activated_at,
                           users.expired_at,
                           users.free_trial_end_at,
                           users.first_name,
                           users.last_name,
                           users.middle_name
                    FROM sessions
                    JOIN users ON users.id = sessions.user_id
                    WHERE sessions.token_hash = %s
                    """,
                    (token_hash,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return user_from_row(row)

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM sessions WHERE token_hash = %s",
                    (hash_session_token(token),),
                )

    def list_users(self) -> list[AuthUser]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id,
                           username,
                           is_active,
                           is_admin,
                           activated_at,
                           expired_at,
                           free_trial_end_at,
                           first_name,
                           last_name,
                           middle_name
                    FROM users
                    ORDER BY id
                    """
                )
                rows = cursor.fetchall()
        return [user_from_row(row) for row in rows]

    def is_free_trial_enabled(self) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT value
                    FROM platform_settings
                    WHERE key = %s
                    """,
                    (FREE_TRIAL_SETTING_KEY,),
                )
                row = cursor.fetchone()
        if row is None:
            return False
        return str(row[0]).strip().lower() in {"1", "true", "yes", "on"}

    def set_free_trial_enabled(self, enabled: bool) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO platform_settings (key, value, updated_at)
                    VALUES (%s, %s, now())
                    ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value,
                        updated_at = now()
                    RETURNING value
                    """,
                    (FREE_TRIAL_SETTING_KEY, "true" if enabled else "false"),
                )
                row = cursor.fetchone()
        return bool(row and str(row[0]).strip().lower() == "true")

    def set_user_access(
        self,
        user_id: int,
        *,
        is_active: bool,
        activated_at: datetime | None = None,
        expired_at: datetime | None = None,
    ) -> AuthUser:
        next_activated_at = activated_at if is_active else None
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE users
                    SET is_active = %s,
                        activated_at = CASE
                            WHEN %s THEN COALESCE(%s, activated_at, now())
                            ELSE NULL
                        END,
                        expired_at = %s,
                        free_trial_end_at = CASE
                            WHEN %s THEN NULL
                            ELSE free_trial_end_at
                        END
                    WHERE id = %s
                    RETURNING id,
                              username,
                              is_active,
                              is_admin,
                              activated_at,
                              expired_at,
                              free_trial_end_at,
                              first_name,
                              last_name,
                              middle_name
                    """,
                    (
                        is_active,
                        is_active,
                        next_activated_at,
                        expired_at,
                        is_active,
                        user_id,
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise ValueError("unknown user")
        return user_from_row(row)

    def update_user_profile(
        self,
        user_id: int,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        middle_name: str | None = None,
    ) -> AuthUser:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE users
                    SET first_name = %s,
                        last_name = %s,
                        middle_name = %s
                    WHERE id = %s
                    RETURNING id,
                              username,
                              is_active,
                              is_admin,
                              activated_at,
                              expired_at,
                              free_trial_end_at,
                              first_name,
                              last_name,
                              middle_name
                    """,
                    (
                        normalize_profile_name(first_name, "first name"),
                        normalize_profile_name(last_name, "last name"),
                        normalize_profile_name(middle_name, "middle name"),
                        user_id,
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise ValueError("unknown user")
        return user_from_row(row)

    def deactivate_expired_users(self, now: datetime | None = None) -> int:
        current_time = now or utcnow()
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE users
                    SET is_active = false,
                        activated_at = NULL
                    WHERE is_active = true
                      AND (
                          (expired_at IS NOT NULL AND expired_at <= %s)
                          OR (free_trial_end_at IS NOT NULL AND free_trial_end_at <= %s)
                      )
                    RETURNING id
                    """,
                    (current_time, current_time),
                )
                rows = cursor.fetchall()
        return len(rows)

    def _connect(self):
        import psycopg  # type: ignore[import-not-found]

        return psycopg.connect(self.database_url)


def user_from_row(row: Sequence[object]) -> AuthUser:
    return AuthUser(
        id=int(str(row[0])),
        username=str(row[1]),
        is_active=bool(row[2]),
        is_admin=bool(row[3]),
        activated_at=cast(datetime | None, row[4]),
        expired_at=cast(datetime | None, row[5]),
        free_trial_end_at=cast(datetime | None, row[6]),
        first_name=cast(str | None, row[7]),
        last_name=cast(str | None, row[8]),
        middle_name=cast(str | None, row[9]),
    )


def normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if len(normalized) < 3:
        raise ValueError("username must be at least 3 characters")
    if len(normalized) > 64:
        raise ValueError("username must be at most 64 characters")
    return normalized


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")


def normalize_profile_name(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 80:
        raise ValueError(f"{field_name} must be at most 80 characters")
    return normalized


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N,
        _SCRYPT_R,
        _SCRYPT_P,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, raw_n, raw_r, raw_p, raw_salt, raw_digest = password_hash.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(raw_salt.encode("ascii"))
        expected_digest = base64.urlsafe_b64decode(raw_digest.encode("ascii"))
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(raw_n),
            r=int(raw_r),
            p=int(raw_p),
            dklen=len(expected_digest),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected_digest)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def public_user(user: AuthUser) -> dict[str, object]:
    return {
        "id": user.id,
        "username": user.username,
        "is_active": user.is_active,
        "is_admin": user.is_admin,
        "activated_at": isoformat_or_none(user.activated_at),
        "expired_at": isoformat_or_none(user.expired_at),
        "free_trial_end_at": isoformat_or_none(user.free_trial_end_at),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "middle_name": user.middle_name,
    }


def isoformat_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    formatted = value.isoformat()
    return formatted.replace("+00:00", "Z")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
