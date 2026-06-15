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

_SCRYPT_N = 16_384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64


@dataclass(frozen=True)
class AuthUser:
    id: int
    username: str
    is_active: bool = False
    activated_at: datetime | None = None
    expired_at: datetime | None = None


class AuthStore(Protocol):
    def ensure_schema(self) -> None: ...
    def register_user(self, username: str, password: str) -> AuthUser: ...
    def authenticate_user(self, username: str, password: str) -> AuthUser: ...
    def create_session(self, user_id: int) -> str: ...
    def user_for_session(self, token: str | None) -> AuthUser | None: ...
    def delete_session(self, token: str | None) -> None: ...
    def list_users(self) -> list[AuthUser]: ...
    def set_user_access(
        self,
        user_id: int,
        *,
        is_active: bool,
        activated_at: datetime | None = None,
        expired_at: datetime | None = None,
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

    def ensure_schema(self) -> None:
        return None

    def register_user(self, username: str, password: str) -> AuthUser:
        normalized = normalize_username(username)
        validate_password(password)
        if normalized in self._users_by_name:
            raise ValueError("username already exists")
        user = AuthUser(id=self._next_user_id, username=normalized)
        self._next_user_id += 1
        record = _MemoryUser(user=user, password_hash=hash_password(password))
        self._users_by_name[normalized] = record
        self._users_by_id[user.id] = record
        return user

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
        next_activated_at = activated_at if is_active else None
        if is_active and next_activated_at is None:
            next_activated_at = record.user.activated_at or utcnow()
        record.user = replace(
            record.user,
            is_active=is_active,
            activated_at=next_activated_at,
            expired_at=expired_at,
        )
        return record.user

    def deactivate_expired_users(self, now: datetime | None = None) -> int:
        current_time = now or utcnow()
        deactivated = 0
        for record in self._users_by_id.values():
            if (
                record.user.is_active
                and record.user.expired_at is not None
                and record.user.expired_at <= current_time
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

    def register_user(self, username: str, password: str) -> AuthUser:
        normalized = normalize_username(username)
        validate_password(password)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO users (username, password_hash)
                    VALUES (%s, %s)
                    ON CONFLICT (username) DO NOTHING
                    RETURNING id, username, is_active, activated_at, expired_at
                    """,
                    (normalized, hash_password(password)),
                )
                row = cursor.fetchone()
        if row is None:
            raise ValueError("username already exists")
        return user_from_row(row)

    def authenticate_user(self, username: str, password: str) -> AuthUser:
        normalized = normalize_username(username)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, username, is_active, activated_at, expired_at, password_hash
                    FROM users
                    WHERE username = %s
                    """,
                    (normalized,),
                )
                row = cursor.fetchone()
        if row is None or not verify_password(password, str(row[5])):
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
                           users.activated_at,
                           users.expired_at
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
                    SELECT id, username, is_active, activated_at, expired_at
                    FROM users
                    ORDER BY id
                    """
                )
                rows = cursor.fetchall()
        return [user_from_row(row) for row in rows]

    def set_user_access(
        self,
        user_id: int,
        *,
        is_active: bool,
        activated_at: datetime | None = None,
        expired_at: datetime | None = None,
    ) -> AuthUser:
        next_activated_at = activated_at if is_active else None
        if is_active and next_activated_at is None:
            next_activated_at = utcnow()
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE users
                    SET is_active = %s,
                        activated_at = %s,
                        expired_at = %s
                    WHERE id = %s
                    RETURNING id, username, is_active, activated_at, expired_at
                    """,
                    (is_active, next_activated_at, expired_at, user_id),
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
                      AND expired_at IS NOT NULL
                      AND expired_at <= %s
                    RETURNING id
                    """,
                    (current_time,),
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
        activated_at=cast(datetime | None, row[3]),
        expired_at=cast(datetime | None, row[4]),
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
        "activated_at": isoformat_or_none(user.activated_at),
        "expired_at": isoformat_or_none(user.expired_at),
    }


def isoformat_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
