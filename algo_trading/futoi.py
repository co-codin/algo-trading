from __future__ import annotations

import csv
import json
import os
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError

from algo_trading.data import MOEX_AUTHENTICATED_ISS_BASE_URL, TransientMarketDataError
from algo_trading.env import load_env_file

FUTOI_ENDPOINT_PATH = "analyticalproducts/futoi/securities"
FUTOI_SOURCE = "moex-futoi"
FUTOI_DATA_DIR = "historical_data/futoi"
FUTOI_RETENTION_DAYS = 730
FUTOI_PRUNE_SECONDS = 7 * 24 * 60 * 60
_DEFAULT_CSV_HISTORY: Any = object()
FUTOI_CSV_FIELDS = [
    "trade_date",
    "trade_time",
    "ticker",
    "client_group",
    "position",
    "position_long",
    "position_short",
    "position_long_count",
    "position_short_count",
    "session_id",
    "sequence_number",
    "system_time",
    "trade_session_date",
]


class MissingFutoiApiKey(ValueError):
    pass


@dataclass(frozen=True)
class FutoiRecord:
    trade_date: date
    trade_time: str
    ticker: str
    client_group: str
    position: float
    position_long: float
    position_short: float
    position_long_count: int
    position_short_count: int
    session_id: int | None = None
    sequence_number: int | None = None
    system_time: datetime | None = None
    trade_session_date: date | None = None


class FutoiClient:
    def __init__(
        self,
        base_url: str | None = None,
        opener: Callable[..., Any] = urllib.request.urlopen,
        timeout: int = 20,
        api_key: str | None = None,
    ) -> None:
        load_env_file()
        fallback_api_key = (
            os.environ.get("MOEX_FUTOI_API_KEY")
            or os.environ.get("MOEX_API_KEY")
            or os.environ.get("MOEXALGO_API_KEY")
            or ""
        )
        self.api_key = (api_key if api_key is not None else fallback_api_key).strip()
        self.base_url = (base_url or MOEX_AUTHENTICATED_ISS_BASE_URL).rstrip("/")
        self.opener = opener
        self.timeout = timeout

    def fetch_daily(
        self,
        trading_date: date | None = None,
        *,
        page_limit: int = 1000,
    ) -> list[FutoiRecord]:
        if not self.api_key:
            raise MissingFutoiApiKey("MOEX FUTOI API key is required")
        if page_limit <= 0:
            raise ValueError("page_limit must be positive")
        selected_date = trading_date or date.today()
        records: list[FutoiRecord] = []
        start = 0
        while True:
            payload = self._request_page(selected_date, start=start, limit=page_limit)
            rows = _rows_from_moex_table(payload)
            if not rows:
                break
            records.extend(_futoi_record_from_row(row) for row in rows)
            start += len(rows)
        return records

    def _request_page(self, trading_date: date, *, start: int, limit: int) -> dict[str, Any]:
        query = urllib.parse.urlencode(
            {
                "date": trading_date.isoformat(),
                "start": str(start),
                "limit": str(limit),
            }
        )
        url = f"{self.base_url}/{FUTOI_ENDPOINT_PATH}.json?{query}"
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                raise TransientMarketDataError(f"transient MOEX FUTOI HTTP {exc.code}") from exc
            raise ValueError(f"MOEX FUTOI HTTP {exc.code}") from exc
        except (TimeoutError, URLError) as exc:
            raise TransientMarketDataError("transient MOEX FUTOI market-data failure") from exc
        except json.JSONDecodeError as exc:
            raise ValueError("unexpected MOEX FUTOI response") from exc


class FutoiCsvHistory:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @classmethod
    def from_env(cls) -> FutoiCsvHistory:
        load_env_file()
        data_dir = Path(os.environ.get("MOEX_FUTOI_DATA_DIR", FUTOI_DATA_DIR))
        return cls(data_dir / "futoi.csv")

    def upsert_records(self, records: Sequence[FutoiRecord]) -> int:
        deduped = {_record_key(record): record for record in self.load_records()}
        before = set(deduped)
        for record in records:
            deduped[_record_key(record)] = _normalized_record(record)
        if records:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=FUTOI_CSV_FIELDS)
                writer.writeheader()
                for record in sorted(deduped.values(), key=_record_key):
                    writer.writerow(_record_to_csv_row(record))
        return len(set(deduped) - before)

    def prune_records(self, cutoff_date: date) -> int:
        records = self.load_records()
        kept = [record for record in records if record.trade_date >= cutoff_date]
        deleted = len(records) - len(kept)
        if deleted <= 0:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=FUTOI_CSV_FIELDS)
            writer.writeheader()
            for record in sorted(kept, key=_record_key):
                writer.writerow(_record_to_csv_row(record))
        return deleted

    def load_records(
        self,
        *,
        trading_date: date | None = None,
        ticker: str | None = None,
        limit: int | None = None,
    ) -> list[FutoiRecord]:
        if not self.path.is_file():
            return []
        normalized_ticker = ticker.strip().upper() if ticker else None
        with self.path.open("r", encoding="utf-8", newline="") as input_file:
            records = [_record_from_csv_row(row) for row in csv.DictReader(input_file)]
        if trading_date is not None:
            records = [record for record in records if record.trade_date == trading_date]
        if normalized_ticker is not None:
            records = [record for record in records if record.ticker == normalized_ticker]
        records = sorted(records, key=_record_key)
        if limit is not None and limit > 0:
            records = records[-limit:]
        return records


class FutoiRefreshService:
    def __init__(
        self,
        store: Any | None = None,
        client: Any | None = None,
        csv_history: FutoiCsvHistory | None | object = _DEFAULT_CSV_HISTORY,
        now: Callable[[], datetime] | None = None,
        retention_days: int | None = None,
    ) -> None:
        load_env_file()
        if store is None:
            from algo_trading.historical_store import historical_store_from_env

            store = historical_store_from_env()
        self._store = store
        self._store.ensure_schema()
        self._client = client or FutoiClient()
        self._csv_history: FutoiCsvHistory | None = (
            FutoiCsvHistory.from_env()
            if csv_history is _DEFAULT_CSV_HISTORY
            else cast(FutoiCsvHistory | None, csv_history)
        )
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._retention_days = (
            int(retention_days)
            if retention_days is not None
            else int(os.environ.get("MOEX_FUTOI_RETENTION_DAYS", str(FUTOI_RETENTION_DAYS)))
        )

    def refresh_daily(self, trading_date: date | None = None) -> dict[str, int]:
        selected_date = trading_date or date.today()
        try:
            records = self._client.fetch_daily(selected_date)
        except MissingFutoiApiKey:
            return {"requested": 1, "refreshed": 0, "records": 0, "failed": 0, "skipped": 1}
        except Exception:
            return {"requested": 1, "refreshed": 0, "records": 0, "failed": 1, "skipped": 0}
        if records:
            self._store.upsert_futoi_records(records, source=FUTOI_SOURCE)
            if self._csv_history is not None:
                self._csv_history.upsert_records(records)
        return {
            "requested": 1,
            "refreshed": 1 if records else 0,
            "records": len(records),
            "failed": 0,
            "skipped": 0,
        }

    def prune_history(self) -> dict[str, int]:
        cutoff_date = self._retention_cutoff_date()
        try:
            store_deleted = self._store.prune_futoi_records(cutoff_date)
            csv_deleted = (
                self._csv_history.prune_records(cutoff_date)
                if self._csv_history is not None
                else 0
            )
        except Exception:
            return {
                "retention_days": self._retention_days,
                "store_deleted": 0,
                "csv_deleted": 0,
                "failed": 1,
            }
        return {
            "retention_days": self._retention_days,
            "store_deleted": store_deleted,
            "csv_deleted": csv_deleted,
            "failed": 0,
        }

    def load_records(
        self,
        *,
        trading_date: date | None = None,
        ticker: str | None = None,
        limit: int | None = None,
    ) -> list[FutoiRecord]:
        records = self._store.load_futoi_records(
            trading_date=trading_date,
            ticker=ticker,
            limit=limit,
        )
        if records or self._csv_history is None:
            return records
        return self._csv_history.load_records(
            trading_date=trading_date,
            ticker=ticker,
            limit=limit,
        )

    def _retention_cutoff_date(self) -> date:
        return self._now().astimezone(timezone.utc).date() - timedelta(
            days=max(0, self._retention_days)
        )


def public_futoi_record(record: FutoiRecord) -> dict[str, Any]:
    return {
        "trade_date": record.trade_date.isoformat(),
        "trade_time": record.trade_time,
        "ticker": record.ticker,
        "client_group": record.client_group,
        "position": record.position,
        "position_long": record.position_long,
        "position_short": record.position_short,
        "position_long_count": record.position_long_count,
        "position_short_count": record.position_short_count,
        "session_id": record.session_id,
        "sequence_number": record.sequence_number,
        "system_time": record.system_time.isoformat() if record.system_time else None,
        "trade_session_date": (
            record.trade_session_date.isoformat() if record.trade_session_date else None
        ),
    }


def parse_futoi_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc


def _rows_from_moex_table(payload: dict[str, Any]) -> list[dict[str, Any]]:
    table = payload.get("futoi")
    if not isinstance(table, dict):
        raise ValueError("MOEX FUTOI response does not contain a futoi table")
    columns = table.get("columns")
    data = table.get("data")
    if not isinstance(columns, list) or not isinstance(data, list):
        raise ValueError("unexpected MOEX FUTOI table format")
    return [dict(zip(columns, row, strict=False)) for row in data]


def _futoi_record_from_row(row: dict[str, Any]) -> FutoiRecord:
    ticker = _required_text(row.get("ticker") or row.get("assetcode"), "ticker")
    return FutoiRecord(
        trade_date=_required_date(row.get("tradedate"), "tradedate"),
        trade_time=_required_text(row.get("tradetime"), "tradetime"),
        ticker=ticker.upper(),
        client_group=_required_text(row.get("clgroup"), "clgroup").upper(),
        position=_required_float(row.get("pos"), "pos"),
        position_long=_required_float(row.get("pos_long"), "pos_long"),
        position_short=_required_float(row.get("pos_short"), "pos_short"),
        position_long_count=_required_int(row.get("pos_long_num"), "pos_long_num"),
        position_short_count=_required_int(row.get("pos_short_num"), "pos_short_num"),
        session_id=_optional_int(row.get("sess_id")),
        sequence_number=_optional_int(row.get("seqnum")),
        system_time=_optional_datetime(row.get("systime")),
        trade_session_date=_optional_date(row.get("trade_session_date")),
    )


def _normalized_record(record: FutoiRecord) -> FutoiRecord:
    return FutoiRecord(
        trade_date=record.trade_date,
        trade_time=record.trade_time,
        ticker=record.ticker.strip().upper(),
        client_group=record.client_group.strip().upper(),
        position=float(record.position),
        position_long=float(record.position_long),
        position_short=float(record.position_short),
        position_long_count=int(record.position_long_count),
        position_short_count=int(record.position_short_count),
        session_id=record.session_id,
        sequence_number=record.sequence_number,
        system_time=record.system_time,
        trade_session_date=record.trade_session_date,
    )


def _record_key(record: FutoiRecord) -> tuple[date, str, str, str]:
    return (
        record.trade_date,
        record.trade_time,
        record.ticker.strip().upper(),
        record.client_group.strip().upper(),
    )


def _record_to_csv_row(record: FutoiRecord) -> dict[str, str]:
    normalized = _normalized_record(record)
    return {
        "trade_date": normalized.trade_date.isoformat(),
        "trade_time": normalized.trade_time,
        "ticker": normalized.ticker,
        "client_group": normalized.client_group,
        "position": str(normalized.position),
        "position_long": str(normalized.position_long),
        "position_short": str(normalized.position_short),
        "position_long_count": str(normalized.position_long_count),
        "position_short_count": str(normalized.position_short_count),
        "session_id": "" if normalized.session_id is None else str(normalized.session_id),
        "sequence_number": (
            "" if normalized.sequence_number is None else str(normalized.sequence_number)
        ),
        "system_time": (
            "" if normalized.system_time is None else normalized.system_time.isoformat()
        ),
        "trade_session_date": (
            ""
            if normalized.trade_session_date is None
            else normalized.trade_session_date.isoformat()
        ),
    }


def _record_from_csv_row(row: dict[str, str]) -> FutoiRecord:
    return FutoiRecord(
        trade_date=_required_date(row.get("trade_date"), "trade_date"),
        trade_time=_required_text(row.get("trade_time"), "trade_time"),
        ticker=_required_text(row.get("ticker"), "ticker").upper(),
        client_group=_required_text(row.get("client_group"), "client_group").upper(),
        position=_required_float(row.get("position"), "position"),
        position_long=_required_float(row.get("position_long"), "position_long"),
        position_short=_required_float(row.get("position_short"), "position_short"),
        position_long_count=_required_int(
            row.get("position_long_count"),
            "position_long_count",
        ),
        position_short_count=_required_int(
            row.get("position_short_count"),
            "position_short_count",
        ),
        session_id=_optional_int(row.get("session_id")),
        sequence_number=_optional_int(row.get("sequence_number")),
        system_time=_optional_datetime(row.get("system_time")),
        trade_session_date=_optional_date(row.get("trade_session_date")),
    )


def _required_text(value: Any, field_name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"MOEX FUTOI row is missing {field_name}")
    return text


def _required_date(value: Any, field_name: str) -> date:
    parsed = _optional_date(value)
    if parsed is None:
        raise ValueError(f"MOEX FUTOI row is missing {field_name}")
    return parsed


def _optional_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def _optional_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace(" ", "T").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _required_float(value: Any, field_name: str) -> float:
    if value in (None, ""):
        raise ValueError(f"MOEX FUTOI row is missing {field_name}")
    return float(value)


def _required_int(value: Any, field_name: str) -> int:
    if value in (None, ""):
        raise ValueError(f"MOEX FUTOI row is missing {field_name}")
    return int(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)
