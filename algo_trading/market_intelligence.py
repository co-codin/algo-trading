from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any

from algo_trading.models import Candle


@dataclass(frozen=True)
class MarketEvent:
    id: str
    type: str
    market: str
    symbol: str
    title: str
    description: str
    severity: str
    time: int | None
    metrics: dict[str, float | int | str]
    source: str = "market-intelligence"


@dataclass(frozen=True)
class FutoiPositionSnapshot:
    ticker: str
    trade_date: date
    trade_time: str
    net_position: float
    long_position: float
    short_position: float
    gross_position: float
    row_count: int


@dataclass(frozen=True)
class FutoiActivitySummary:
    ticker: str
    snapshots: list[FutoiPositionSnapshot]
    summary: dict[str, Any]
    events: list[MarketEvent]


def build_futoi_position_dashboard(
    records: Sequence[Any],
    instruments: Sequence[Any] = (),
) -> FutoiActivitySummary:
    snapshots = _futoi_snapshots(records)
    latest = snapshots[-1] if snapshots else None
    previous = snapshots[-2] if len(snapshots) >= 2 else None
    previous_week = _previous_week_snapshot(snapshots)
    selected_instrument = _instrument_for_latest(instruments, latest.ticker if latest else "")

    if latest is None:
        summary: dict[str, Any] = {
            "ticker": "",
            "net_position": 0.0,
            "gross_position": 0.0,
            "long_position": 0.0,
            "short_position": 0.0,
            "net_change_1d": 0.0,
            "net_change_1d_pct": 0.0,
            "net_change_1w": 0.0,
            "gross_change_1d_pct": 0.0,
            "row_count": 0,
        }
    else:
        previous_net = previous.net_position if previous else latest.net_position
        previous_gross = previous.gross_position if previous else latest.gross_position
        week_net = previous_week.net_position if previous_week else latest.net_position
        summary = {
            "ticker": latest.ticker,
            "trade_date": latest.trade_date.isoformat(),
            "trade_time": latest.trade_time,
            "net_position": _round_metric(latest.net_position),
            "gross_position": _round_metric(
                float(getattr(selected_instrument, "gross_position", latest.gross_position))
            ),
            "long_position": _round_metric(
                float(getattr(selected_instrument, "long_position", latest.long_position))
            ),
            "short_position": _round_metric(
                float(getattr(selected_instrument, "short_position", latest.short_position))
            ),
            "net_change_1d": _round_metric(latest.net_position - previous_net),
            "net_change_1d_pct": _percent_change(latest.net_position, previous_net),
            "net_change_1w": _round_metric(latest.net_position - week_net),
            "gross_change_1d_pct": _percent_change(latest.gross_position, previous_gross),
            "row_count": int(getattr(selected_instrument, "row_count", latest.row_count)),
        }

    return FutoiActivitySummary(
        ticker=str(summary["ticker"]),
        snapshots=snapshots,
        summary=summary,
        events=build_unusual_futoi_events(records),
    )


def build_unusual_futoi_events(
    records: Sequence[Any],
    *,
    min_net_change_pct: float = 20.0,
    min_gross_change_pct: float = 15.0,
    min_net_change_abs: float = 10_000.0,
) -> list[MarketEvent]:
    snapshots = _futoi_snapshots(records)
    if len(snapshots) < 2:
        return []
    events: list[MarketEvent] = []
    snapshots_by_ticker: dict[str, list[FutoiPositionSnapshot]] = {}
    for snapshot in snapshots:
        snapshots_by_ticker.setdefault(snapshot.ticker, []).append(snapshot)
    for ticker_snapshots in snapshots_by_ticker.values():
        for previous, current in zip(ticker_snapshots, ticker_snapshots[1:]):
            net_change = current.net_position - previous.net_position
            gross_change_pct = _percent_change(current.gross_position, previous.gross_position)
            net_change_pct = _percent_change(current.net_position, previous.net_position)
            if (
                abs(net_change_pct) < min_net_change_pct
                and abs(gross_change_pct) < min_gross_change_pct
                and abs(net_change) < min_net_change_abs
            ):
                continue
            severity = _severity_from_ratio(max(abs(net_change_pct), abs(gross_change_pct)))
            events.append(
                MarketEvent(
                    id=":".join(
                        [
                            "futoi_change",
                            current.ticker,
                            current.trade_date.isoformat(),
                            current.trade_time,
                        ]
                    ),
                    type="futoi_change",
                    market="moex",
                    symbol=current.ticker,
                    title=f"FUTOI positioning changed for {current.ticker}",
                    description=(
                        f"Net position changed by {_round_metric(net_change)} "
                        f"({_round_metric(net_change_pct)}%) versus the previous snapshot."
                    ),
                    severity=severity,
                    time=_date_time_to_millis(current.trade_date, current.trade_time),
                    metrics={
                        "net_position": _round_metric(current.net_position),
                        "net_change": _round_metric(net_change),
                        "net_change_pct": _round_metric(net_change_pct),
                        "gross_position": _round_metric(current.gross_position),
                        "gross_change_pct": _round_metric(gross_change_pct),
                    },
                    source="moex-futoi",
                )
            )
    return events


def build_volume_spike_events(
    candles: Sequence[Candle],
    *,
    market: str,
    symbol: str,
    interval: str,
    lookback: int = 20,
    min_ratio: float = 2.0,
) -> list[MarketEvent]:
    if lookback <= 0 or len(candles) < lookback + 1:
        return []
    latest = candles[-1]
    reference = candles[-lookback - 1 : -1]
    average_volume = sum(candle.volume for candle in reference) / len(reference)
    if average_volume <= 0:
        return []
    ratio = latest.volume / average_volume
    if ratio < min_ratio:
        return []
    severity = _severity_from_ratio(ratio * 25.0)
    return [
        MarketEvent(
            id=f"volume_spike:{market}:{symbol}:{interval}:{latest.open_time}",
            type="volume_spike",
            market=market,
            symbol=symbol,
            title=f"Volume spike on {symbol}",
            description=(
                f"Latest {interval} volume is {_round_metric(ratio)}x "
                "above the recent average."
            ),
            severity=severity,
            time=latest.open_time,
            metrics={
                "volume": _round_metric(latest.volume),
                "average_volume": _round_metric(average_volume),
                "volume_ratio": _round_metric(ratio),
            },
            source="candles",
        )
    ]


def build_breadth_confirmation_events(
    bars_by_symbol: Mapping[str, Sequence[Any]],
    *,
    bullish_threshold: float = 60.0,
    bearish_threshold: float = 40.0,
) -> list[MarketEvent]:
    latest_values: list[float] = []
    latest_dates: list[date] = []
    for bars in bars_by_symbol.values():
        if not bars:
            continue
        latest = sorted(bars, key=lambda item: item.date)[-1]
        latest_values.append(float(latest.close))
        latest_dates.append(latest.date)
    if not latest_values:
        return []
    average = sum(latest_values) / len(latest_values)
    if average >= bullish_threshold:
        direction = "constructive"
        severity = "medium"
    elif average <= bearish_threshold:
        direction = "weak"
        severity = "medium"
    else:
        return []
    latest_date = max(latest_dates)
    return [
        MarketEvent(
            id=f"breadth_confirmation:{latest_date.isoformat()}:{direction}",
            type="breadth_confirmation",
            market="us_market",
            symbol="BREADTH",
            title="Breadth confirmation",
            description=f"Average breadth is {direction} at {_round_metric(average)}%.",
            severity=severity,
            time=_date_to_millis(latest_date),
            metrics={
                "average_breadth": _round_metric(average),
                "series_count": len(latest_values),
            },
            source="market-breadth",
        )
    ]


def build_algopack_events(records: Sequence[Any]) -> list[MarketEvent]:
    events: list[MarketEvent] = []
    for record in records:
        dataset = str(getattr(record, "dataset", "")).lower()
        if dataset == "alerts":
            events.append(_algopack_alert_event(record))
    return events


def public_futoi_dashboard(dashboard: FutoiActivitySummary) -> dict[str, Any]:
    snapshots = [public_futoi_snapshot(snapshot) for snapshot in dashboard.snapshots]
    events = [public_market_event(event) for event in dashboard.events]
    return {
        "ticker": dashboard.ticker,
        "summary": dashboard.summary,
        "snapshots": snapshots,
        "events": events,
        "latest": list(reversed(snapshots[-5:])),
        "unusual_events": events,
        "instrument_count": len({snapshot.ticker for snapshot in dashboard.snapshots}),
        "snapshot_count": len(snapshots),
    }


def public_futoi_snapshot(snapshot: FutoiPositionSnapshot) -> dict[str, Any]:
    return {
        "ticker": snapshot.ticker,
        "trade_date": snapshot.trade_date.isoformat(),
        "trade_time": snapshot.trade_time,
        "net_position": _round_metric(snapshot.net_position),
        "long_position": _round_metric(snapshot.long_position),
        "short_position": _round_metric(snapshot.short_position),
        "gross_position": _round_metric(snapshot.gross_position),
        "row_count": snapshot.row_count,
    }


def public_market_event(event: MarketEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "type": event.type,
        "market": event.market,
        "symbol": event.symbol,
        "title": event.title,
        "description": event.description,
        "details": event.description,
        "severity": event.severity,
        "time": event.time,
        "metrics": dict(event.metrics),
        "source": event.source,
    }


def _futoi_snapshots(records: Sequence[Any]) -> list[FutoiPositionSnapshot]:
    grouped: dict[tuple[str, date, str], list[Any]] = {}
    for record in records:
        ticker = str(getattr(record, "ticker", "")).strip().upper()
        trade_date = getattr(record, "trade_date", None)
        trade_time = str(getattr(record, "trade_time", "") or "")
        if not ticker or not isinstance(trade_date, date):
            continue
        grouped.setdefault((ticker, trade_date, trade_time), []).append(record)
    snapshots = [
        _snapshot_from_records(ticker, trade_date, trade_time, grouped_records)
        for (ticker, trade_date, trade_time), grouped_records in grouped.items()
    ]
    return sorted(snapshots, key=lambda item: (item.ticker, item.trade_date, item.trade_time))


def _snapshot_from_records(
    ticker: str,
    trade_date: date,
    trade_time: str,
    records: Sequence[Any],
) -> FutoiPositionSnapshot:
    long_position = sum(abs(float(getattr(record, "position_long", 0.0) or 0.0)) for record in records)
    short_position = sum(abs(float(getattr(record, "position_short", 0.0) or 0.0)) for record in records)
    return FutoiPositionSnapshot(
        ticker=ticker,
        trade_date=trade_date,
        trade_time=trade_time,
        net_position=sum(float(getattr(record, "position", 0.0) or 0.0) for record in records),
        long_position=long_position,
        short_position=short_position,
        gross_position=long_position + short_position,
        row_count=len(records),
    )


def _previous_week_snapshot(
    snapshots: Sequence[FutoiPositionSnapshot],
) -> FutoiPositionSnapshot | None:
    if len(snapshots) < 2:
        return None
    latest = snapshots[-1]
    candidates = [
        snapshot
        for snapshot in snapshots[:-1]
        if snapshot.ticker == latest.ticker and snapshot.trade_date <= latest.trade_date
    ]
    if not candidates:
        return None
    cutoff = latest.trade_date.toordinal() - 7
    older = [snapshot for snapshot in candidates if snapshot.trade_date.toordinal() <= cutoff]
    return older[-1] if older else candidates[0]


def _instrument_for_latest(instruments: Sequence[Any], ticker: str) -> Any | None:
    normalized = ticker.upper()
    for instrument in instruments:
        if str(getattr(instrument, "ticker", "")).upper() == normalized:
            return instrument
    return None


def _algopack_alert_event(record: Any) -> MarketEvent:
    metrics = dict(getattr(record, "metrics", {}) or {})
    alert_type = str(metrics.get("alert_type") or getattr(record, "record_key", "") or "MegaAlert")
    return MarketEvent(
        id=":".join(
            [
                "mega_alert",
                str(getattr(record, "ticker", "")),
                str(getattr(record, "trade_date", "")),
                str(getattr(record, "trade_time", "")),
                alert_type,
            ]
        ),
        type="mega_alert",
        market=str(getattr(record, "market", "moex")),
        symbol=str(getattr(record, "ticker", "")),
        title=f"MegaAlert: {getattr(record, 'ticker', '')}",
        description=f"AlgoPack MegaAlert {alert_type}",
        severity="high",
        time=_algopack_record_time(record),
        metrics=_numeric_metrics(metrics),
        source="moex-algopack",
    )


def _numeric_metrics(metrics: Mapping[str, Any]) -> dict[str, float | int | str]:
    public_metrics: dict[str, float | int | str] = {}
    for key, value in metrics.items():
        if isinstance(value, bool):
            public_metrics[str(key)] = int(value)
            continue
        if isinstance(value, int | float):
            public_metrics[str(key)] = _round_metric(float(value))
            continue
        try:
            public_metrics[str(key)] = _round_metric(float(str(value)))
        except (TypeError, ValueError):
            public_metrics[str(key)] = str(value)
    return public_metrics


def _algopack_record_time(record: Any) -> int | None:
    trade_date = getattr(record, "trade_date", None)
    trade_time = str(getattr(record, "trade_time", "") or "")
    if not isinstance(trade_date, date):
        return None
    return _date_time_to_millis(trade_date, trade_time)


def _percent_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    return _round_metric(((current - previous) / abs(previous)) * 100.0)


def _severity_from_ratio(value: float) -> str:
    if value >= 50.0:
        return "high"
    if value >= 20.0:
        return "medium"
    return "low"


def _date_time_to_millis(trade_date: date, trade_time: str) -> int | None:
    try:
        parsed_time = time.fromisoformat(trade_time)
    except ValueError:
        return _date_to_millis(trade_date)
    return int(datetime.combine(trade_date, parsed_time, tzinfo=timezone.utc).timestamp() * 1000)


def _date_to_millis(value: date) -> int:
    return int(datetime.combine(value, time.min, tzinfo=timezone.utc).timestamp() * 1000)


def _round_metric(value: float) -> float:
    return round(float(value), 4)
