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
