from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Protocol

from algo_trading.env import load_env_file
from algo_trading.models import Candle


@dataclass(frozen=True, order=True)
class CandleSeries:
    market: str
    symbol: str
    interval: str


class HistoricalDataStore(Protocol):
    def ensure_schema(self) -> None: ...

    def upsert_candles(
        self,
        market: str,
        symbol: str,
        interval: str,
        candles: Sequence[Candle],
        *,
        source: str = "",
    ) -> int: ...

    def load_candles(
        self,
        market: str,
        symbol: str,
        interval: str,
        *,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[Candle]: ...

    def list_candle_series(self) -> list[CandleSeries]: ...

    def mark_candle_series_refreshed(
        self,
        market: str,
        symbol: str,
        interval: str,
    ) -> None: ...

    def prune_candles(self, cutoff_open_time: int) -> int: ...

    def upsert_breadth_bars(
        self,
        symbol: str,
        bars: Sequence[Any],
        *,
        source: str = "",
    ) -> int: ...

    def load_breadth_bars(self, symbol: str) -> list[Any]: ...

    def is_breadth_fresh(self, symbol: str, max_age_seconds: int) -> bool: ...

    def prune_breadth_bars(
        self,
        cutoff_date: date,
        *,
        exclude_symbols: Iterable[str] = (),
    ) -> int: ...

    def upsert_futoi_records(
        self,
        records: Sequence[Any],
        *,
        source: str = "",
    ) -> int: ...

    def upsert_futoi_instruments(
        self,
        instruments: Sequence[Any],
        *,
        source: str = "",
    ) -> int: ...

    def load_futoi_records(
        self,
        *,
        trading_date: date | None = None,
        ticker: str | None = None,
        limit: int | None = None,
    ) -> list[Any]: ...

    def list_futoi_instruments(self) -> list[Any]: ...

    def prune_futoi_records(self, cutoff_date: date) -> int: ...


class InMemoryHistoricalDataStore:
    def __init__(
        self,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._time_offset = timedelta(0)
        self._candles: dict[CandleSeries, dict[int, Candle]] = {}
        self._series_sources: dict[CandleSeries, str] = {}
        self._breadth_bars: dict[str, dict[date, Any]] = {}
        self._breadth_updated_at: dict[str, datetime] = {}
        self._futoi_records: dict[tuple[date, str, str, str], Any] = {}
        self._futoi_instruments: dict[str, Any] = {}

    def ensure_schema(self) -> None:
        return None

    def advance_time(self, delta: timedelta) -> None:
        self._time_offset += delta

    def upsert_candles(
        self,
        market: str,
        symbol: str,
        interval: str,
        candles: Sequence[Candle],
        *,
        source: str = "",
    ) -> int:
        series = normalize_candle_series(market, symbol, interval)
        bucket = self._candles.setdefault(series, {})
        self._series_sources[series] = source
        before = set(bucket)
        for candle in candles:
            bucket[candle.open_time] = candle
        return len(set(bucket) - before)

    def load_candles(
        self,
        market: str,
        symbol: str,
        interval: str,
        *,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[Candle]:
        series = normalize_candle_series(market, symbol, interval)
        candles = sorted(
            self._candles.get(series, {}).values(),
            key=lambda candle: candle.open_time,
        )
        if start_time is not None:
            candles = [candle for candle in candles if candle.open_time >= start_time]
        if end_time is not None:
            candles = [candle for candle in candles if candle.open_time <= end_time]
        if limit is not None and limit > 0:
            candles = candles[-limit:]
        return list(candles)

    def list_candle_series(self) -> list[CandleSeries]:
        return sorted(self._candles)

    def mark_candle_series_refreshed(
        self,
        market: str,
        symbol: str,
        interval: str,
    ) -> None:
        series = normalize_candle_series(market, symbol, interval)
        self._candles.setdefault(series, {})

    def prune_candles(self, cutoff_open_time: int) -> int:
        deleted = 0
        for bucket in self._candles.values():
            old_keys = [
                open_time
                for open_time in bucket
                if open_time < cutoff_open_time
            ]
            for open_time in old_keys:
                bucket.pop(open_time, None)
            deleted += len(old_keys)
        return deleted

    def upsert_breadth_bars(
        self,
        symbol: str,
        bars: Sequence[Any],
        *,
        source: str = "",
    ) -> int:
        normalized_symbol = normalize_symbol(symbol)
        bucket = self._breadth_bars.setdefault(normalized_symbol, {})
        before = set(bucket)
        for bar in bars:
            bucket[bar.date] = bar
        if bars:
            self._breadth_updated_at[normalized_symbol] = self._utcnow()
        return len(set(bucket) - before)

    def load_breadth_bars(self, symbol: str) -> list[Any]:
        normalized_symbol = normalize_symbol(symbol)
        return [
            self._breadth_bars[normalized_symbol][bar_date]
            for bar_date in sorted(self._breadth_bars.get(normalized_symbol, {}))
        ]

    def is_breadth_fresh(self, symbol: str, max_age_seconds: int) -> bool:
        if max_age_seconds <= 0:
            return False
        updated_at = self._breadth_updated_at.get(normalize_symbol(symbol))
        if updated_at is None:
            return False
        return (self._utcnow() - updated_at).total_seconds() < max_age_seconds

    def prune_breadth_bars(
        self,
        cutoff_date: date,
        *,
        exclude_symbols: Iterable[str] = (),
    ) -> int:
        excluded = {normalize_symbol(symbol) for symbol in exclude_symbols}
        deleted = 0
        for symbol, bucket in self._breadth_bars.items():
            if symbol in excluded:
                continue
            old_dates = [bar_date for bar_date in bucket if bar_date < cutoff_date]
            for bar_date in old_dates:
                bucket.pop(bar_date, None)
            deleted += len(old_dates)
        return deleted

    def upsert_futoi_records(
        self,
        records: Sequence[Any],
        *,
        source: str = "",
    ) -> int:
        before = set(self._futoi_records)
        for record in records:
            self._futoi_records[futoi_record_key(record)] = record
        return len(set(self._futoi_records) - before)

    def upsert_futoi_instruments(
        self,
        instruments: Sequence[Any],
        *,
        source: str = "",
    ) -> int:
        before = set(self._futoi_instruments)
        for instrument in instruments:
            normalized = normalize_futoi_instrument(instrument, updated_at=self._utcnow())
            self._futoi_instruments[normalized.ticker] = normalized
        return len(set(self._futoi_instruments) - before)

    def load_futoi_records(
        self,
        *,
        trading_date: date | None = None,
        ticker: str | None = None,
        limit: int | None = None,
    ) -> list[Any]:
        normalized_ticker = normalize_symbol(ticker) if ticker else None
        records = [
            record
            for record in self._futoi_records.values()
            if (trading_date is None or record.trade_date == trading_date)
            and (normalized_ticker is None or normalize_symbol(record.ticker) == normalized_ticker)
        ]
        records = sorted(records, key=futoi_record_key)
        if limit is not None and limit > 0:
            records = records[-limit:]
        return records

    def list_futoi_instruments(self) -> list[Any]:
        return [
            self._futoi_instruments[ticker]
            for ticker in sorted(self._futoi_instruments)
        ]

    def prune_futoi_records(self, cutoff_date: date) -> int:
        old_keys = [
            key
            for key, record in self._futoi_records.items()
            if record.trade_date < cutoff_date
        ]
        for key in old_keys:
            self._futoi_records.pop(key, None)
        return len(old_keys)

    def _utcnow(self) -> datetime:
        return self._now().astimezone(timezone.utc) + self._time_offset


class PostgresHistoricalDataStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tracked_market_series (
                        market TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        interval TEXT NOT NULL,
                        source TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        refreshed_at TIMESTAMPTZ,
                        PRIMARY KEY (market, symbol, interval)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS market_candles (
                        market TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        interval TEXT NOT NULL,
                        open_time BIGINT NOT NULL,
                        open DOUBLE PRECISION NOT NULL,
                        high DOUBLE PRECISION NOT NULL,
                        low DOUBLE PRECISION NOT NULL,
                        close DOUBLE PRECISION NOT NULL,
                        volume DOUBLE PRECISION NOT NULL,
                        source TEXT NOT NULL DEFAULT '',
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        PRIMARY KEY (market, symbol, interval, open_time)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS market_candles_series_time_idx
                    ON market_candles (market, symbol, interval, open_time DESC)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS market_candles_open_time_idx
                    ON market_candles (open_time)
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS market_breadth_bars (
                        symbol TEXT NOT NULL,
                        bar_date DATE NOT NULL,
                        open DOUBLE PRECISION NOT NULL,
                        high DOUBLE PRECISION NOT NULL,
                        low DOUBLE PRECISION NOT NULL,
                        close DOUBLE PRECISION NOT NULL,
                        volume DOUBLE PRECISION NOT NULL,
                        source TEXT NOT NULL DEFAULT '',
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        PRIMARY KEY (symbol, bar_date)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS market_breadth_bars_symbol_date_idx
                    ON market_breadth_bars (symbol, bar_date DESC)
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS moex_futoi_records (
                        trade_date DATE NOT NULL,
                        trade_time TEXT NOT NULL,
                        ticker TEXT NOT NULL,
                        client_group TEXT NOT NULL,
                        position DOUBLE PRECISION NOT NULL,
                        position_long DOUBLE PRECISION NOT NULL,
                        position_short DOUBLE PRECISION NOT NULL,
                        position_long_count BIGINT NOT NULL,
                        position_short_count BIGINT NOT NULL,
                        session_id BIGINT,
                        sequence_number BIGINT,
                        system_time TIMESTAMPTZ,
                        trade_session_date DATE,
                        source TEXT NOT NULL DEFAULT '',
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        PRIMARY KEY (trade_date, trade_time, ticker, client_group)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS moex_futoi_records_ticker_date_idx
                    ON moex_futoi_records (ticker, trade_date DESC, trade_time DESC)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS moex_futoi_records_recent_idx
                    ON moex_futoi_records (trade_date DESC, trade_time DESC, ticker, client_group)
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS moex_futoi_instruments (
                        ticker TEXT PRIMARY KEY,
                        last_trade_date DATE,
                        last_trade_time TEXT,
                        system_time TIMESTAMPTZ,
                        trade_session_date DATE,
                        client_groups TEXT NOT NULL DEFAULT '',
                        net_position DOUBLE PRECISION NOT NULL DEFAULT 0,
                        gross_position DOUBLE PRECISION NOT NULL DEFAULT 0,
                        long_position DOUBLE PRECISION NOT NULL DEFAULT 0,
                        short_position DOUBLE PRECISION NOT NULL DEFAULT 0,
                        long_count BIGINT NOT NULL DEFAULT 0,
                        short_count BIGINT NOT NULL DEFAULT 0,
                        row_count INTEGER NOT NULL DEFAULT 0,
                        source TEXT NOT NULL DEFAULT '',
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS moex_futoi_instruments_gross_idx
                    ON moex_futoi_instruments (gross_position DESC, ticker)
                    """
                )

    def upsert_candles(
        self,
        market: str,
        symbol: str,
        interval: str,
        candles: Sequence[Candle],
        *,
        source: str = "",
    ) -> int:
        series = normalize_candle_series(market, symbol, interval)
        deduped = {candle.open_time: candle for candle in candles}
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO tracked_market_series (market, symbol, interval, source)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (market, symbol, interval) DO UPDATE
                    SET source = EXCLUDED.source
                    """,
                    (series.market, series.symbol, series.interval, source),
                )
                cursor.executemany(
                    """
                    INSERT INTO market_candles (
                        market,
                        symbol,
                        interval,
                        open_time,
                        open,
                        high,
                        low,
                        close,
                        volume,
                        source
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (market, symbol, interval, open_time) DO UPDATE
                    SET open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        source = EXCLUDED.source,
                        updated_at = now()
                    """,
                    [
                        (
                            series.market,
                            series.symbol,
                            series.interval,
                            candle.open_time,
                            candle.open,
                            candle.high,
                            candle.low,
                            candle.close,
                            candle.volume,
                            source,
                        )
                        for candle in deduped.values()
                    ],
                )
        return len(deduped)

    def load_candles(
        self,
        market: str,
        symbol: str,
        interval: str,
        *,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[Candle]:
        series = normalize_candle_series(market, symbol, interval)
        filters = [
            "market = %s",
            "symbol = %s",
            "interval = %s",
        ]
        params: list[Any] = [series.market, series.symbol, series.interval]
        if start_time is not None:
            filters.append("open_time >= %s")
            params.append(start_time)
        if end_time is not None:
            filters.append("open_time <= %s")
            params.append(end_time)
        query = f"""
            SELECT open_time, open, high, low, close, volume
            FROM market_candles
            WHERE {' AND '.join(filters)}
            ORDER BY open_time DESC
        """
        if limit is not None and limit > 0:
            query += " LIMIT %s"
            params.append(limit)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [
            Candle(
                open_time=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in reversed(rows)
        ]

    def list_candle_series(self) -> list[CandleSeries]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT market, symbol, interval
                    FROM tracked_market_series
                    ORDER BY market, symbol, interval
                    """
                )
                rows = cursor.fetchall()
        return [CandleSeries(str(row[0]), str(row[1]), str(row[2])) for row in rows]

    def mark_candle_series_refreshed(
        self,
        market: str,
        symbol: str,
        interval: str,
    ) -> None:
        series = normalize_candle_series(market, symbol, interval)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO tracked_market_series (
                        market,
                        symbol,
                        interval,
                        refreshed_at
                    )
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (market, symbol, interval) DO UPDATE
                    SET refreshed_at = now()
                    """,
                    (series.market, series.symbol, series.interval),
                )

    def prune_candles(self, cutoff_open_time: int) -> int:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM market_candles WHERE open_time < %s",
                    (cutoff_open_time,),
                )
                return int(cursor.rowcount)

    def upsert_breadth_bars(
        self,
        symbol: str,
        bars: Sequence[Any],
        *,
        source: str = "",
    ) -> int:
        normalized_symbol = normalize_symbol(symbol)
        deduped = {bar.date: bar for bar in bars}
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO market_breadth_bars (
                        symbol,
                        bar_date,
                        open,
                        high,
                        low,
                        close,
                        volume,
                        source
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, bar_date) DO UPDATE
                    SET open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        source = EXCLUDED.source,
                        updated_at = now()
                    """,
                    [
                        (
                            normalized_symbol,
                            bar.date,
                            bar.open,
                            bar.high,
                            bar.low,
                            bar.close,
                            bar.volume,
                            source,
                        )
                        for bar in deduped.values()
                    ],
                )
        return len(deduped)

    def load_breadth_bars(self, symbol: str) -> list[Any]:
        normalized_symbol = normalize_symbol(symbol)
        from algo_trading.market_breadth import MarketBreadthBar

        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT symbol, bar_date, open, high, low, close, volume
                    FROM market_breadth_bars
                    WHERE symbol = %s
                    ORDER BY bar_date
                    """,
                    (normalized_symbol,),
                )
                rows = cursor.fetchall()
        return [
            MarketBreadthBar(
                symbol=str(row[0]),
                date=row[1],
                open=float(row[2]),
                high=float(row[3]),
                low=float(row[4]),
                close=float(row[5]),
                volume=float(row[6]),
            )
            for row in rows
        ]

    def is_breadth_fresh(self, symbol: str, max_age_seconds: int) -> bool:
        if max_age_seconds <= 0:
            return False
        normalized_symbol = normalize_symbol(symbol)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT max(updated_at)
                    FROM market_breadth_bars
                    WHERE symbol = %s
                    """,
                    (normalized_symbol,),
                )
                row = cursor.fetchone()
        updated_at = row[0] if row else None
        if updated_at is None:
            return False
        return (
            datetime.now(timezone.utc) - updated_at.astimezone(timezone.utc)
        ).total_seconds() < max_age_seconds

    def prune_breadth_bars(
        self,
        cutoff_date: date,
        *,
        exclude_symbols: Iterable[str] = (),
    ) -> int:
        excluded = [normalize_symbol(symbol) for symbol in exclude_symbols]
        with self._connect() as conn:
            with conn.cursor() as cursor:
                if excluded:
                    cursor.execute(
                        """
                        DELETE FROM market_breadth_bars
                        WHERE bar_date < %s
                          AND NOT (symbol = ANY(%s))
                        """,
                        (cutoff_date, excluded),
                    )
                else:
                    cursor.execute(
                        "DELETE FROM market_breadth_bars WHERE bar_date < %s",
                        (cutoff_date,),
                    )
                return int(cursor.rowcount)

    def upsert_futoi_records(
        self,
        records: Sequence[Any],
        *,
        source: str = "",
    ) -> int:
        deduped = {futoi_record_key(record): record for record in records}
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO moex_futoi_records (
                        trade_date,
                        trade_time,
                        ticker,
                        client_group,
                        position,
                        position_long,
                        position_short,
                        position_long_count,
                        position_short_count,
                        session_id,
                        sequence_number,
                        system_time,
                        trade_session_date,
                        source
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (trade_date, trade_time, ticker, client_group) DO UPDATE
                    SET position = EXCLUDED.position,
                        position_long = EXCLUDED.position_long,
                        position_short = EXCLUDED.position_short,
                        position_long_count = EXCLUDED.position_long_count,
                        position_short_count = EXCLUDED.position_short_count,
                        session_id = EXCLUDED.session_id,
                        sequence_number = EXCLUDED.sequence_number,
                        system_time = EXCLUDED.system_time,
                        trade_session_date = EXCLUDED.trade_session_date,
                        source = EXCLUDED.source,
                        updated_at = now()
                    """,
                    [
                        (
                            record.trade_date,
                            record.trade_time,
                            normalize_symbol(record.ticker),
                            str(record.client_group).strip().upper(),
                            record.position,
                            record.position_long,
                            record.position_short,
                            record.position_long_count,
                            record.position_short_count,
                            record.session_id,
                            record.sequence_number,
                            record.system_time,
                            record.trade_session_date,
                            source,
                        )
                        for record in deduped.values()
                    ],
                )
        return len(deduped)

    def upsert_futoi_instruments(
        self,
        instruments: Sequence[Any],
        *,
        source: str = "",
    ) -> int:
        normalized_instruments = [
            normalize_futoi_instrument(instrument)
            for instrument in instruments
        ]
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO moex_futoi_instruments (
                        ticker,
                        last_trade_date,
                        last_trade_time,
                        system_time,
                        trade_session_date,
                        client_groups,
                        net_position,
                        gross_position,
                        long_position,
                        short_position,
                        long_count,
                        short_count,
                        row_count,
                        source
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker) DO UPDATE
                    SET last_trade_date = EXCLUDED.last_trade_date,
                        last_trade_time = EXCLUDED.last_trade_time,
                        system_time = EXCLUDED.system_time,
                        trade_session_date = EXCLUDED.trade_session_date,
                        client_groups = EXCLUDED.client_groups,
                        net_position = EXCLUDED.net_position,
                        gross_position = EXCLUDED.gross_position,
                        long_position = EXCLUDED.long_position,
                        short_position = EXCLUDED.short_position,
                        long_count = EXCLUDED.long_count,
                        short_count = EXCLUDED.short_count,
                        row_count = EXCLUDED.row_count,
                        source = EXCLUDED.source,
                        updated_at = now()
                    """,
                    [
                        (
                            instrument.ticker,
                            instrument.last_trade_date,
                            instrument.last_trade_time,
                            instrument.system_time,
                            instrument.trade_session_date,
                            ",".join(instrument.client_groups),
                            instrument.net_position,
                            instrument.gross_position,
                            instrument.long_position,
                            instrument.short_position,
                            instrument.long_count,
                            instrument.short_count,
                            instrument.row_count,
                            source,
                        )
                        for instrument in normalized_instruments
                    ],
                )
        return len(normalized_instruments)

    def load_futoi_records(
        self,
        *,
        trading_date: date | None = None,
        ticker: str | None = None,
        limit: int | None = None,
    ) -> list[Any]:
        from algo_trading.futoi import FutoiRecord

        filters: list[str] = []
        params: list[Any] = []
        if trading_date is not None:
            filters.append("trade_date = %s")
            params.append(trading_date)
        if ticker:
            filters.append("ticker = %s")
            params.append(normalize_symbol(ticker))
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        query = f"""
            SELECT
                trade_date,
                trade_time,
                ticker,
                client_group,
                position,
                position_long,
                position_short,
                position_long_count,
                position_short_count,
                session_id,
                sequence_number,
                system_time,
                trade_session_date
            FROM moex_futoi_records
            {where_clause}
            ORDER BY trade_date DESC, trade_time DESC, ticker, client_group
        """
        if limit is not None and limit > 0:
            query += " LIMIT %s"
            params.append(limit)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [
            FutoiRecord(
                trade_date=row[0],
                trade_time=str(row[1]),
                ticker=str(row[2]),
                client_group=str(row[3]),
                position=float(row[4]),
                position_long=float(row[5]),
                position_short=float(row[6]),
                position_long_count=int(row[7]),
                position_short_count=int(row[8]),
                session_id=int(row[9]) if row[9] is not None else None,
                sequence_number=int(row[10]) if row[10] is not None else None,
                system_time=row[11],
                trade_session_date=row[12],
            )
            for row in reversed(rows)
        ]

    def list_futoi_instruments(self) -> list[Any]:
        from algo_trading.futoi import FutoiInstrument

        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        ticker,
                        last_trade_date,
                        last_trade_time,
                        system_time,
                        trade_session_date,
                        client_groups,
                        net_position,
                        gross_position,
                        long_position,
                        short_position,
                        long_count,
                        short_count,
                        row_count,
                        updated_at
                    FROM moex_futoi_instruments
                    ORDER BY ticker
                    """
                )
                rows = cursor.fetchall()
        return [
            FutoiInstrument(
                ticker=str(row[0]),
                last_trade_date=row[1],
                last_trade_time=str(row[2]) if row[2] is not None else None,
                system_time=row[3],
                trade_session_date=row[4],
                client_groups=tuple(
                    group for group in str(row[5] or "").split(",") if group
                ),
                net_position=float(row[6]),
                gross_position=float(row[7]),
                long_position=float(row[8]),
                short_position=float(row[9]),
                long_count=int(row[10]),
                short_count=int(row[11]),
                row_count=int(row[12]),
                updated_at=row[13],
            )
            for row in rows
        ]

    def prune_futoi_records(self, cutoff_date: date) -> int:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM moex_futoi_records WHERE trade_date < %s",
                    (cutoff_date,),
                )
                return int(cursor.rowcount)

    def _connect(self) -> Any:
        import psycopg

        return psycopg.connect(self.database_url)


def historical_store_from_env() -> HistoricalDataStore:
    load_env_file()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    store: HistoricalDataStore
    if database_url:
        store = PostgresHistoricalDataStore(database_url)
    else:
        store = InMemoryHistoricalDataStore()
    store.ensure_schema()
    return store


def normalize_candle_series(market: str, symbol: str, interval: str) -> CandleSeries:
    return CandleSeries(
        market=str(market).strip().lower(),
        symbol=normalize_symbol(symbol),
        interval=str(interval).strip(),
    )


def normalize_symbol(symbol: str) -> str:
    return str(symbol).strip().upper()


def futoi_record_key(record: Any) -> tuple[date, str, str, str]:
    return (
        record.trade_date,
        str(record.trade_time),
        normalize_symbol(record.ticker),
        str(record.client_group).strip().upper(),
    )


def normalize_futoi_instrument(
    instrument: Any,
    *,
    updated_at: datetime | None = None,
) -> Any:
    from algo_trading.futoi import FutoiInstrument

    return FutoiInstrument(
        ticker=normalize_symbol(instrument.ticker),
        last_trade_date=instrument.last_trade_date,
        last_trade_time=(
            str(instrument.last_trade_time)
            if instrument.last_trade_time is not None
            else None
        ),
        system_time=instrument.system_time,
        trade_session_date=instrument.trade_session_date,
        client_groups=tuple(sorted({str(group).strip().upper() for group in instrument.client_groups if str(group).strip()})),
        net_position=float(instrument.net_position),
        gross_position=float(instrument.gross_position),
        long_position=float(instrument.long_position),
        short_position=float(instrument.short_position),
        long_count=int(instrument.long_count),
        short_count=int(instrument.short_count),
        row_count=int(instrument.row_count),
        updated_at=updated_at or instrument.updated_at,
    )
