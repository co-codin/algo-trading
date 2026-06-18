from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError

from algo_trading.data import MOEX_AUTHENTICATED_ISS_BASE_URL, TransientMarketDataError
from algo_trading.env import load_env_file

ALGOPACK_SOURCE = "moex-algopack"
ALGOPACK_DATASETS = frozenset({"tradestats", "orderstats", "obstats", "alerts"})
ALGOPACK_ENDPOINTS = {
    "russian_bluechips": "datashop/algopack/eq",
    "russian_indices_futures": "datashop/algopack/fo",
    "russian_futures": "datashop/algopack/fo",
}
ALGOPACK_FUTURES_MARKETS = frozenset({"russian_indices_futures", "russian_futures"})
ALGOPACK_UNSUPPORTED_FUTURES_DATASETS = frozenset({"orderstats"})
ALGOPACK_INDEX_SYMBOLS = frozenset({"IMOEX", "RTSI"})
MOEX_TIMEZONE = timezone(timedelta(hours=3))


class MissingAlgoPackApiKey(ValueError):
    pass


@dataclass(frozen=True)
class AlgoPackRecord:
    dataset: str
    market: str
    ticker: str
    trade_date: date
    trade_time: str
    metrics: dict[str, Any]
    record_key: str = ""


class AlgoPackDataClient(Protocol):
    def fetch_ticker(
        self,
        market: str,
        dataset: str,
        ticker: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[AlgoPackRecord]: ...


class AlgoPackClient:
    def __init__(
        self,
        base_url: str | None = None,
        opener: Callable[..., Any] = urllib.request.urlopen,
        timeout: int = 20,
        api_key: str | None = None,
    ) -> None:
        load_env_file()
        fallback_api_key = (
            os.environ.get("MOEX_ALGOPACK_API_KEY")
            or os.environ.get("MOEX_API_KEY")
            or os.environ.get("MOEXALGO_API_KEY")
            or ""
        )
        self.api_key = (api_key if api_key is not None else fallback_api_key).strip()
        self.base_url = (base_url or MOEX_AUTHENTICATED_ISS_BASE_URL).rstrip("/")
        self.opener = opener
        self.timeout = timeout

    def fetch_ticker(
        self,
        market: str,
        dataset: str,
        ticker: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        page_limit: int = 1000,
    ) -> list[AlgoPackRecord]:
        if not self.api_key:
            raise MissingAlgoPackApiKey("MOEX AlgoPack API key is required")
        if page_limit <= 0:
            raise ValueError("page_limit must be positive")
        normalized_market = normalize_algopack_market(market, ticker)
        normalized_dataset = normalize_algopack_dataset(dataset, normalized_market)
        normalized_ticker = normalize_algopack_ticker(ticker)
        endpoint = ALGOPACK_ENDPOINTS[normalized_market]
        records: list[AlgoPackRecord] = []
        start = 0
        while True:
            payload = self._request_page(
                endpoint,
                normalized_dataset,
                normalized_ticker,
                start_date=start_date,
                end_date=end_date,
                start=start,
                limit=page_limit,
            )
            rows = _rows_from_algopack_table(payload)
            if not rows:
                break
            records.extend(
                _record_from_row(
                    row,
                    dataset=normalized_dataset,
                    market=normalized_market,
                    fallback_ticker=normalized_ticker,
                )
                for row in rows
            )
            if len(rows) < page_limit:
                break
            start += len(rows)
        return records

    def _request_page(
        self,
        endpoint: str,
        dataset: str,
        ticker: str,
        *,
        start_date: date | None,
        end_date: date | None,
        start: int,
        limit: int,
    ) -> dict[str, Any]:
        query_params: dict[str, str] = {
            "start": str(start),
            "limit": str(limit),
        }
        if start_date is not None:
            query_params["from"] = start_date.isoformat()
        if end_date is not None:
            query_params["till"] = end_date.isoformat()
        query = urllib.parse.urlencode(query_params)
        url = f"{self.base_url}/{endpoint}/{dataset}/{ticker}.json?{query}"
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                raise TransientMarketDataError(f"transient MOEX AlgoPack HTTP {exc.code}") from exc
            raise ValueError(f"MOEX AlgoPack HTTP {exc.code}") from exc
        except (TimeoutError, URLError) as exc:
            raise TransientMarketDataError("transient MOEX AlgoPack market-data failure") from exc
        except json.JSONDecodeError as exc:
            raise ValueError("unexpected MOEX AlgoPack response") from exc


class AlgoPackService:
    def __init__(
        self,
        store: Any | None = None,
        client: AlgoPackDataClient | None = None,
    ) -> None:
        self._store = store
        self._client = client or AlgoPackClient()

    def load_records(
        self,
        market: str,
        ticker: str,
        datasets: Sequence[str],
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[AlgoPackRecord]:
        records: list[AlgoPackRecord] = []
        for dataset in normalized_algopack_datasets(datasets, market, ticker):
            stored = self._load_store_records(
                dataset,
                market,
                ticker,
                start_date=start_date,
                end_date=end_date,
            )
            if stored:
                records.extend(stored)
                continue
            fetched = self._fetch_records(
                market,
                dataset,
                ticker,
                start_date=start_date,
                end_date=end_date,
            )
            if fetched and self._store is not None:
                try:
                    self._store.upsert_algopack_records(fetched, source=ALGOPACK_SOURCE)
                    fetched = self._load_store_records(
                        dataset,
                        market,
                        ticker,
                        start_date=start_date,
                        end_date=end_date,
                    ) or fetched
                except Exception:
                    pass
            records.extend(fetched)
        return sorted(records, key=algopack_record_key)

    def _load_store_records(
        self,
        dataset: str,
        market: str,
        ticker: str,
        *,
        start_date: date | None,
        end_date: date | None,
    ) -> list[AlgoPackRecord]:
        if self._store is None:
            return []
        try:
            return list(
                self._store.load_algopack_records(
                    dataset=dataset,
                    market=normalize_algopack_market(market, ticker),
                    ticker=ticker,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
        except Exception:
            return []

    def _fetch_records(
        self,
        market: str,
        dataset: str,
        ticker: str,
        *,
        start_date: date | None,
        end_date: date | None,
    ) -> list[AlgoPackRecord]:
        try:
            return self._client.fetch_ticker(
                market,
                dataset,
                ticker,
                start_date=start_date,
                end_date=end_date,
            )
        except (MissingAlgoPackApiKey, TransientMarketDataError, ValueError):
            return []


def normalize_algopack_ticker(ticker: str) -> str:
    normalized = str(ticker).strip().upper()
    if not normalized:
        raise ValueError("ticker is required")
    return normalized


def normalize_algopack_market(market: str, ticker: str = "") -> str:
    normalized_market = str(market).strip().lower()
    normalized_ticker = str(ticker).strip().upper()
    if normalized_market == "russian_futures":
        normalized_market = "russian_indices_futures"
    if normalized_market not in ALGOPACK_ENDPOINTS:
        raise ValueError(f"unsupported AlgoPack market: {market}")
    if normalized_ticker in ALGOPACK_INDEX_SYMBOLS:
        raise ValueError(f"unsupported AlgoPack index symbol: {ticker}")
    return normalized_market


def normalize_algopack_dataset(dataset: str, market: str) -> str:
    normalized_dataset = str(dataset).strip().lower()
    if normalized_dataset not in ALGOPACK_DATASETS:
        raise ValueError(f"unsupported AlgoPack dataset: {dataset}")
    if (
        market in ALGOPACK_FUTURES_MARKETS
        and normalized_dataset in ALGOPACK_UNSUPPORTED_FUTURES_DATASETS
    ):
        raise ValueError(f"unsupported AlgoPack futures dataset: {dataset}")
    return normalized_dataset


def normalized_algopack_datasets(
    datasets: Sequence[str],
    market: str,
    ticker: str,
) -> list[str]:
    try:
        normalized_market = normalize_algopack_market(market, ticker)
    except ValueError:
        return []
    normalized: list[str] = []
    for dataset in datasets:
        try:
            normalized_dataset = normalize_algopack_dataset(dataset, normalized_market)
        except ValueError:
            continue
        if normalized_dataset not in normalized:
            normalized.append(normalized_dataset)
    return normalized


def algopack_record_key(record: AlgoPackRecord) -> tuple[str, str, str, date, str, str]:
    normalized_dataset = normalize_algopack_dataset(
        record.dataset,
        normalize_algopack_market(record.market, record.ticker),
    )
    return (
        normalized_dataset,
        normalize_algopack_market(record.market, record.ticker),
        normalize_algopack_ticker(record.ticker),
        record.trade_date,
        str(record.trade_time),
        _record_key_from_record(record, normalized_dataset),
    )


def algopack_record_time_millis(record: AlgoPackRecord) -> int:
    trade_time = time.fromisoformat(str(record.trade_time))
    moment = datetime.combine(record.trade_date, trade_time).replace(tzinfo=MOEX_TIMEZONE)
    return int(moment.astimezone(timezone.utc).timestamp() * 1000)


def _rows_from_algopack_table(payload: dict[str, Any]) -> list[dict[str, Any]]:
    table = payload.get("data")
    if not isinstance(table, dict):
        table = next(
            (
                value
                for value in payload.values()
                if isinstance(value, dict)
                and isinstance(value.get("columns"), list)
                and isinstance(value.get("data"), list)
            ),
            None,
        )
    if not isinstance(table, dict):
        return []
    columns = table.get("columns")
    rows = table.get("data")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return []
    return [
        dict(zip([str(column).lower() for column in columns], row))
        for row in rows
        if isinstance(row, list | tuple)
    ]


def _record_from_row(
    row: dict[str, Any],
    *,
    dataset: str,
    market: str,
    fallback_ticker: str,
) -> AlgoPackRecord:
    tradedate = row.get("tradedate") or row.get("trade_date")
    tradetime = row.get("tradetime") or row.get("trade_time")
    if tradedate is None or tradetime is None:
        raise ValueError("AlgoPack row is missing tradedate/tradetime")
    ticker = row.get("ticker") or row.get("secid") or fallback_ticker
    excluded_keys = {
        "ticker",
        "secid",
        "tradedate",
        "trade_date",
        "tradetime",
        "trade_time",
        "begin",
        "end",
    }
    return AlgoPackRecord(
        dataset=dataset,
        market=market,
        ticker=normalize_algopack_ticker(str(ticker)),
        trade_date=tradedate if isinstance(tradedate, date) else date.fromisoformat(str(tradedate)),
        trade_time=str(tradetime),
        metrics={key: value for key, value in row.items() if key not in excluded_keys and value is not None},
        record_key=str(row.get("alert_type") or ""),
    )


def _record_key_from_record(record: AlgoPackRecord, dataset: str) -> str:
    if record.record_key:
        return str(record.record_key)
    if dataset == "alerts":
        alert_type = record.metrics.get("alert_type")
        threshold = record.metrics.get("threshold")
        value = record.metrics.get("value")
        return "|".join(str(item) for item in (alert_type, threshold, value) if item is not None)
    return ""
