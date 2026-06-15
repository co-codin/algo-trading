from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

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


class AuthStore(Protocol):
    def ensure_schema(self) -> None: ...
    def register_user(self, username: str, password: str) -> AuthUser: ...
    def authenticate_user(self, username: str, password: str) -> AuthUser: ...
    def create_session(self, user_id: int) -> str: ...
    def user_for_session(self, token: str | None) -> AuthUser | None: ...
    def delete_session(self, token: str | None) -> None: ...


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
                    RETURNING id, username
                    """,
                    (normalized, hash_password(password)),
                )
                row = cursor.fetchone()
        if row is None:
            raise ValueError("username already exists")
        return AuthUser(id=int(row[0]), username=str(row[1]))

    def authenticate_user(self, username: str, password: str) -> AuthUser:
        normalized = normalize_username(username)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, username, password_hash FROM users WHERE username = %s",
                    (normalized,),
                )
                row = cursor.fetchone()
        if row is None or not verify_password(password, str(row[2])):
            raise ValueError("invalid username or password")
        return AuthUser(id=int(row[0]), username=str(row[1]))

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
                    SELECT users.id, users.username
                    FROM sessions
                    JOIN users ON users.id = sessions.user_id
                    WHERE sessions.token_hash = %s
                    """,
                    (token_hash,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return AuthUser(id=int(row[0]), username=str(row[1]))

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM sessions WHERE token_hash = %s",
                    (hash_session_token(token),),
                )

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url)


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


def public_user(user: AuthUser) -> dict[str, int | str]:
    return {"id": user.id, "username": user.username}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
