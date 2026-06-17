from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Literal, Protocol, cast

FeedbackStatus = Literal["open", "in_progress", "resolved"]
FEEDBACK_STATUSES: tuple[FeedbackStatus, ...] = ("open", "in_progress", "resolved")
_MAX_TITLE_LENGTH = 160
_MAX_DESCRIPTION_LENGTH = 4000


@dataclass(frozen=True)
class FeedbackItem:
    id: int
    user_id: int
    username: str
    title: str
    description: str
    status: FeedbackStatus
    created_at: datetime
    updated_at: datetime


class FeedbackStore(Protocol):
    def ensure_schema(self) -> None: ...

    def create_feedback(
        self,
        *,
        user_id: int,
        username: str,
        title: str,
        description: str | None = None,
    ) -> FeedbackItem: ...

    def list_feedback(self) -> list[FeedbackItem]: ...

    def update_feedback_status(
        self,
        feedback_id: int,
        status: str,
    ) -> FeedbackItem: ...


class InMemoryFeedbackStore:
    def __init__(self) -> None:
        self._next_feedback_id = 1
        self._feedback: dict[int, FeedbackItem] = {}

    def ensure_schema(self) -> None:
        return None

    def create_feedback(
        self,
        *,
        user_id: int,
        username: str,
        title: str,
        description: str | None = None,
    ) -> FeedbackItem:
        now = utcnow()
        feedback = FeedbackItem(
            id=self._next_feedback_id,
            user_id=user_id,
            username=username,
            title=normalize_feedback_title(title),
            description=normalize_feedback_description(description),
            status="open",
            created_at=now,
            updated_at=now,
        )
        self._next_feedback_id += 1
        self._feedback[feedback.id] = feedback
        return feedback

    def list_feedback(self) -> list[FeedbackItem]:
        return [
            feedback
            for _feedback_id, feedback in sorted(
                self._feedback.items(),
                key=lambda item: item[1].created_at,
                reverse=True,
            )
        ]

    def update_feedback_status(
        self,
        feedback_id: int,
        status: str,
    ) -> FeedbackItem:
        existing = self._feedback.get(feedback_id)
        if existing is None:
            raise ValueError("unknown feedback")
        updated = replace(
            existing,
            status=normalize_feedback_status(status),
            updated_at=utcnow(),
        )
        self._feedback[feedback_id] = updated
        return updated


class PostgresFeedbackStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS feedback (
                        id BIGSERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        username TEXT NOT NULL,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'open',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS feedback_created_at_idx
                    ON feedback(created_at DESC)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS feedback_status_idx
                    ON feedback(status)
                    """
                )

    def create_feedback(
        self,
        *,
        user_id: int,
        username: str,
        title: str,
        description: str | None = None,
    ) -> FeedbackItem:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO feedback (
                        user_id,
                        username,
                        title,
                        description,
                        status
                    )
                    VALUES (%s, %s, %s, %s, 'open')
                    RETURNING id,
                              user_id,
                              username,
                              title,
                              description,
                              status,
                              created_at,
                              updated_at
                    """,
                    (
                        user_id,
                        username,
                        normalize_feedback_title(title),
                        normalize_feedback_description(description),
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise ValueError("feedback submission failed")
        return feedback_from_row(row)

    def list_feedback(self) -> list[FeedbackItem]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id,
                           user_id,
                           username,
                           title,
                           description,
                           status,
                           created_at,
                           updated_at
                    FROM feedback
                    ORDER BY created_at DESC, id DESC
                    """
                )
                rows = cursor.fetchall()
        return [feedback_from_row(row) for row in rows]

    def update_feedback_status(
        self,
        feedback_id: int,
        status: str,
    ) -> FeedbackItem:
        normalized_status = normalize_feedback_status(status)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE feedback
                    SET status = %s,
                        updated_at = now()
                    WHERE id = %s
                    RETURNING id,
                              user_id,
                              username,
                              title,
                              description,
                              status,
                              created_at,
                              updated_at
                    """,
                    (normalized_status, feedback_id),
                )
                row = cursor.fetchone()
        if row is None:
            raise ValueError("unknown feedback")
        return feedback_from_row(row)

    def _connect(self):
        import psycopg  # type: ignore[import-not-found]

        return psycopg.connect(self.database_url)


def feedback_from_row(row: Sequence[object]) -> FeedbackItem:
    return FeedbackItem(
        id=int(str(row[0])),
        user_id=int(str(row[1])),
        username=str(row[2]),
        title=str(row[3]),
        description=str(row[4]),
        status=normalize_feedback_status(str(row[5])),
        created_at=cast(datetime, row[6]),
        updated_at=cast(datetime, row[7]),
    )


def public_feedback(feedback: FeedbackItem) -> dict[str, object]:
    return {
        "id": feedback.id,
        "user_id": feedback.user_id,
        "username": feedback.username,
        "title": feedback.title,
        "description": feedback.description,
        "status": feedback.status,
        "created_at": isoformat_z(feedback.created_at),
        "updated_at": isoformat_z(feedback.updated_at),
    }


def normalize_feedback_title(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("feedback title is required")
    if len(normalized) > _MAX_TITLE_LENGTH:
        raise ValueError(f"feedback title must be at most {_MAX_TITLE_LENGTH} characters")
    return normalized


def normalize_feedback_description(value: str | None) -> str:
    normalized = "" if value is None else str(value).strip()
    if len(normalized) > _MAX_DESCRIPTION_LENGTH:
        raise ValueError(
            f"feedback description must be at most {_MAX_DESCRIPTION_LENGTH} characters"
        )
    return normalized


def normalize_feedback_status(value: str) -> FeedbackStatus:
    normalized = str(value).strip().lower()
    if normalized not in FEEDBACK_STATUSES:
        raise ValueError("unsupported feedback status")
    return cast(FeedbackStatus, normalized)


def isoformat_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
