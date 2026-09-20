from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from algo_trading.indicators import rsi
from algo_trading.models import Candle

QuantAction = str
TIME_SERIES_MOMENTUM_LOOKBACK = 60
TIME_SERIES_MOMENTUM_THRESHOLD_PCT = 2.0
BREADTH_STRONG = 55.0
BREADTH_WEAK = 45.0


@dataclass(frozen=True)
class QuantStrategyIdea:
    id: str
    title: str
    group: str
    action: QuantAction
    score: float
    confidence: str
    metrics: dict[str, float | int | str]
    reasons: list[str]


def build_quant_strategy_ideas(
    candles: Sequence[Candle],
    *,
    market: str,
    symbol: str,
    breadth_bars_by_symbol: Mapping[str, Sequence[Any]] | None = None,
) -> list[QuantStrategyIdea]:
    normalized_candles = list(candles)
    ideas = [
        _time_series_momentum_idea(normalized_candles),
        _rsi_mean_reversion_idea(normalized_candles),
        _donchian_breakout_idea(normalized_candles),
    ]
    ideas.append(_breadth_confirmation_idea(breadth_bars_by_symbol or {}))
    return ideas


def public_quant_strategy_idea(idea: QuantStrategyIdea) -> dict[str, Any]:
    return {
        "id": idea.id,
        "title": idea.title,
        "group": idea.group,
        "action": idea.action,
        "score": round(idea.score, 4),
        "confidence": idea.confidence,
        "metrics": idea.metrics,
        "reasons": idea.reasons,
    }


def time_series_momentum_return_pct(
    candles: Sequence[Candle],
    *,
    lookback: int = TIME_SERIES_MOMENTUM_LOOKBACK,
    index: int | None = None,
) -> float | None:
    if not candles:
        return None
    end_index = len(candles) - 1 if index is None else index
    if end_index <= 0 or end_index >= len(candles):
        return None
    used_lookback = min(lookback, end_index)
    start = candles[end_index - used_lookback].close
    end = candles[end_index].close
    return _percent_change(start, end)


def rsi_mean_reversion_side(
    rsi_value: float,
    *,
    oversold: float = 30.0,
    overbought: float = 70.0,
) -> int:
    if rsi_value <= oversold:
        return 1
    if rsi_value >= overbought:
        return -1
    return 0


def donchian_breakout_side(close: float, previous_high: float, previous_low: float) -> int:
    if close > previous_high:
        return 1
    if close < previous_low:
        return -1
    return 0


def latest_breadth_closes(
    breadth_bars_by_symbol: Mapping[str, Sequence[Any]] | None,
) -> list[float]:
    if not breadth_bars_by_symbol:
        return []
    return [
        float(bars[-1].close)
        for bars in breadth_bars_by_symbol.values()
        if bars
    ]


def breadth_confirmation_side(
    values: Sequence[float],
    *,
    strong: float = BREADTH_STRONG,
    weak: float = BREADTH_WEAK,
) -> int:
    if not values:
        return 0
    average = sum(values) / len(values)
    if average >= strong:
        return 1
    if average <= weak:
        return -1
    return 0


def _time_series_momentum_idea(candles: list[Candle]) -> QuantStrategyIdea:
    if len(candles) < 2:
        return _neutral_idea(
            "time-series-momentum",
            "Time-series momentum",
            "trend",
            "Need at least two candles for momentum.",
        )

    lookback = min(TIME_SERIES_MOMENTUM_LOOKBACK, len(candles) - 1)
    return_pct = time_series_momentum_return_pct(candles, lookback=lookback)
    if return_pct is None:
        return _neutral_idea(
            "time-series-momentum",
            "Time-series momentum",
            "trend",
            "Need at least two candles for momentum.",
        )
    end = candles[-1].close
    score = _clamp(return_pct, -100.0, 100.0)
    if return_pct >= 2.0:
        action = "bullish"
        reasons = [f"Price is up {return_pct:.2f}% over the last {lookback} candles."]
    elif return_pct <= -2.0:
        action = "bearish"
        reasons = [f"Price is down {abs(return_pct):.2f}% over the last {lookback} candles."]
    else:
        action = "neutral"
        reasons = [f"Momentum is flat at {return_pct:.2f}% over the last {lookback} candles."]

    return QuantStrategyIdea(
        id="time-series-momentum",
        title="Time-series momentum",
        group="trend",
        action=action,
        score=score,
        confidence=_confidence(abs(score), len(candles)),
        metrics={
            "lookback_candles": lookback,
            "lookback_return_pct": round(return_pct, 4),
            "last_close": end,
        },
        reasons=reasons,
    )


def _rsi_mean_reversion_idea(candles: list[Candle]) -> QuantStrategyIdea:
    if len(candles) < 15:
        return _neutral_idea(
            "rsi-mean-reversion",
            "RSI mean reversion",
            "reversal",
            "Need at least 15 candles for RSI.",
        )

    values = rsi([candle.close for candle in candles], period=14)
    latest = values[-1]
    side = rsi_mean_reversion_side(latest)
    if side > 0:
        action = "bullish"
        score = 30.0 - latest
        reasons = [f"RSI is oversold at {latest:.2f}."]
    elif side < 0:
        action = "bearish"
        score = -(latest - 70.0)
        reasons = [f"RSI is overbought at {latest:.2f}."]
    else:
        action = "neutral"
        score = 0.0
        reasons = [f"RSI is neutral at {latest:.2f}."]

    return QuantStrategyIdea(
        id="rsi-mean-reversion",
        title="RSI mean reversion",
        group="reversal",
        action=action,
        score=score,
        confidence=_confidence(abs(score) * 2.0, len(candles)),
        metrics={"rsi": round(latest, 4), "period": 14},
        reasons=reasons,
    )


def _donchian_breakout_idea(candles: list[Candle]) -> QuantStrategyIdea:
    period = 20
    if len(candles) <= period:
        return _neutral_idea(
            "volatility-breakout",
            "Volatility breakout",
            "breakout",
            "Need more than 20 candles for breakout levels.",
        )

    previous = candles[-period - 1 : -1]
    high = max(candle.high for candle in previous)
    low = min(candle.low for candle in previous)
    close = candles[-1].close
    side = donchian_breakout_side(close, high, low)
    if side > 0:
        action = "bullish"
        distance_pct = _percent_change(high, close)
        score = min(100.0, distance_pct * 10.0)
        reasons = [f"Close is {distance_pct:.2f}% above the previous {period}-candle high."]
    elif side < 0:
        action = "bearish"
        distance_pct = _percent_change(low, close)
        score = max(-100.0, distance_pct * 10.0)
        reasons = [f"Close is {abs(distance_pct):.2f}% below the previous {period}-candle low."]
    else:
        action = "neutral"
        score = 0.0
        reasons = [f"Close remains inside the previous {period}-candle range."]

    return QuantStrategyIdea(
        id="volatility-breakout",
        title="Volatility breakout",
        group="breakout",
        action=action,
        score=score,
        confidence=_confidence(abs(score), len(candles)),
        metrics={
            "period": period,
            "previous_high": round(high, 4),
            "previous_low": round(low, 4),
            "last_close": close,
        },
        reasons=reasons,
    )


def _breadth_confirmation_idea(
    breadth_bars_by_symbol: Mapping[str, Sequence[Any]],
) -> QuantStrategyIdea:
    latest_values = latest_breadth_closes(breadth_bars_by_symbol)
    if not latest_values:
        return _neutral_idea(
            "breadth-confirmation",
            "Breadth confirmation",
            "breadth",
            "No breadth series are available.",
            metrics={"series_count": 0},
        )

    average = sum(latest_values) / len(latest_values)
    side = breadth_confirmation_side(latest_values)
    if side > 0:
        action = "bullish"
        score = min(100.0, (average - 50.0) * 2.0)
        reasons = [f"Average breadth is constructive at {average:.2f}%."]
    elif side < 0:
        action = "bearish"
        score = max(-100.0, (average - 50.0) * 2.0)
        reasons = [f"Average breadth is weak at {average:.2f}%."]
    else:
        action = "neutral"
        score = 0.0
        reasons = [f"Average breadth is mixed at {average:.2f}%."]

    return QuantStrategyIdea(
        id="breadth-confirmation",
        title="Breadth confirmation",
        group="breadth",
        action=action,
        score=score,
        confidence=_confidence(abs(score) * 2.0, len(latest_values) * 20),
        metrics={
            "average_breadth": round(average, 4),
            "series_count": len(latest_values),
            "strong_series": sum(1 for value in latest_values if value >= 50.0),
        },
        reasons=reasons,
    )


def _neutral_idea(
    idea_id: str,
    title: str,
    group: str,
    reason: str,
    *,
    metrics: dict[str, float | int | str] | None = None,
) -> QuantStrategyIdea:
    return QuantStrategyIdea(
        id=idea_id,
        title=title,
        group=group,
        action="neutral",
        score=0.0,
        confidence="low",
        metrics=metrics or {},
        reasons=[reason],
    )


def _percent_change(start: float, end: float) -> float:
    if start == 0.0:
        return 0.0
    return ((end - start) / start) * 100.0


def _confidence(score: float, sample_size: int) -> str:
    if score >= 50.0 and sample_size >= 40:
        return "high"
    if score >= 15.0 and sample_size >= 20:
        return "medium"
    return "low"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
