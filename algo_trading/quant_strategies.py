from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from algo_trading.indicators import rsi
from algo_trading.models import Candle

QuantAction = str
MOMENTUM_THRESHOLD_PCT = 2.0
DEFAULT_MOMENTUM_LOOKBACK = 60
DEFAULT_BREAKOUT_PERIOD = 20
BREADTH_BULLISH = 55.0
BREADTH_BEARISH = 45.0


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


@dataclass(frozen=True)
class TimeSeriesMomentumState:
    action: QuantAction
    lookback: int
    return_pct: float
    last_close: float
    reasons: list[str]


@dataclass(frozen=True)
class RsiMeanReversionState:
    action: QuantAction
    rsi: float
    period: int
    reasons: list[str]


@dataclass(frozen=True)
class VolatilityBreakoutState:
    action: QuantAction
    period: int
    previous_high: float
    previous_low: float
    last_close: float
    reasons: list[str]


@dataclass(frozen=True)
class BreadthConfirmationState:
    action: QuantAction
    average: float | None
    series_count: int
    strong_series: int
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


def time_series_momentum_state(
    candles: Sequence[Candle],
    lookback: int = DEFAULT_MOMENTUM_LOOKBACK,
) -> TimeSeriesMomentumState:
    if len(candles) < 2:
        return TimeSeriesMomentumState(
            action="neutral",
            lookback=0,
            return_pct=0.0,
            last_close=candles[-1].close if candles else 0.0,
            reasons=["Need at least two candles for momentum."],
        )

    used_lookback = min(max(lookback, 1), len(candles) - 1)
    start = candles[-used_lookback - 1].close
    end = candles[-1].close
    return_pct = percent_change(start, end)
    if return_pct >= MOMENTUM_THRESHOLD_PCT:
        action = "bullish"
        reasons = [f"Price is up {return_pct:.2f}% over the last {used_lookback} candles."]
    elif return_pct <= -MOMENTUM_THRESHOLD_PCT:
        action = "bearish"
        reasons = [f"Price is down {abs(return_pct):.2f}% over the last {used_lookback} candles."]
    else:
        action = "neutral"
        reasons = [f"Momentum is flat at {return_pct:.2f}% over the last {used_lookback} candles."]
    return TimeSeriesMomentumState(
        action=action,
        lookback=used_lookback,
        return_pct=return_pct,
        last_close=end,
        reasons=reasons,
    )


def rsi_mean_reversion_state(
    rsi_value: float,
    *,
    period: int = 14,
    oversold: float = 30.0,
    overbought: float = 70.0,
) -> RsiMeanReversionState:
    if rsi_value <= oversold:
        return RsiMeanReversionState(
            action="bullish",
            rsi=rsi_value,
            period=period,
            reasons=[f"RSI is oversold at {rsi_value:.2f}."],
        )
    if rsi_value >= overbought:
        return RsiMeanReversionState(
            action="bearish",
            rsi=rsi_value,
            period=period,
            reasons=[f"RSI is overbought at {rsi_value:.2f}."],
        )
    return RsiMeanReversionState(
        action="neutral",
        rsi=rsi_value,
        period=period,
        reasons=[f"RSI is neutral at {rsi_value:.2f}."],
    )


def volatility_breakout_state(
    candles: Sequence[Candle],
    period: int = DEFAULT_BREAKOUT_PERIOD,
) -> VolatilityBreakoutState:
    if len(candles) <= period:
        last_close = candles[-1].close if candles else 0.0
        return VolatilityBreakoutState(
            action="neutral",
            period=period,
            previous_high=last_close,
            previous_low=last_close,
            last_close=last_close,
            reasons=["Need more than 20 candles for breakout levels."],
        )

    previous = list(candles)[-period - 1 : -1]
    high = max(candle.high for candle in previous)
    low = min(candle.low for candle in previous)
    close = candles[-1].close
    if close > high:
        distance_pct = percent_change(high, close)
        reasons = [f"Close is {distance_pct:.2f}% above the previous {period}-candle high."]
        action = "bullish"
    elif close < low:
        distance_pct = percent_change(low, close)
        reasons = [f"Close is {abs(distance_pct):.2f}% below the previous {period}-candle low."]
        action = "bearish"
    else:
        reasons = [f"Close remains inside the previous {period}-candle range."]
        action = "neutral"
    return VolatilityBreakoutState(
        action=action,
        period=period,
        previous_high=high,
        previous_low=low,
        last_close=close,
        reasons=reasons,
    )


def breadth_confirmation_state(latest_values: Sequence[float]) -> BreadthConfirmationState:
    if not latest_values:
        return BreadthConfirmationState(
            action="neutral",
            average=None,
            series_count=0,
            strong_series=0,
            reasons=["No breadth series are available."],
        )

    average = sum(latest_values) / len(latest_values)
    strong_series = sum(1 for value in latest_values if value >= 50.0)
    if average >= BREADTH_BULLISH:
        action = "bullish"
        reasons = [f"Average breadth is constructive at {average:.2f}%."]
    elif average <= BREADTH_BEARISH:
        action = "bearish"
        reasons = [f"Average breadth is weak at {average:.2f}%."]
    else:
        action = "neutral"
        reasons = [f"Average breadth is mixed at {average:.2f}%."]
    return BreadthConfirmationState(
        action=action,
        average=average,
        series_count=len(latest_values),
        strong_series=strong_series,
        reasons=reasons,
    )


def percent_change(start: float, end: float) -> float:
    if start == 0.0:
        return 0.0
    return ((end - start) / start) * 100.0


def _time_series_momentum_idea(candles: list[Candle]) -> QuantStrategyIdea:
    state = time_series_momentum_state(candles)
    if len(candles) < 2:
        return _neutral_idea(
            "time-series-momentum",
            "Time-series momentum",
            "trend",
            state.reasons[0],
        )

    score = _clamp(state.return_pct, -100.0, 100.0)
    return QuantStrategyIdea(
        id="time-series-momentum",
        title="Time-series momentum",
        group="trend",
        action=state.action,
        score=score,
        confidence=_confidence(abs(score), len(candles)),
        metrics={
            "lookback_candles": state.lookback,
            "lookback_return_pct": round(state.return_pct, 4),
            "last_close": state.last_close,
        },
        reasons=state.reasons,
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
    state = rsi_mean_reversion_state(latest)
    if state.action == "bullish":
        score = 30.0 - latest
    elif state.action == "bearish":
        score = -(latest - 70.0)
    else:
        score = 0.0
    return QuantStrategyIdea(
        id="rsi-mean-reversion",
        title="RSI mean reversion",
        group="reversal",
        action=state.action,
        score=score,
        confidence=_confidence(abs(score) * 2.0, len(candles)),
        metrics={"rsi": round(latest, 4), "period": 14},
        reasons=state.reasons,
    )


def _donchian_breakout_idea(candles: list[Candle]) -> QuantStrategyIdea:
    state = volatility_breakout_state(candles)
    if len(candles) <= DEFAULT_BREAKOUT_PERIOD:
        return _neutral_idea(
            "volatility-breakout",
            "Volatility breakout",
            "breakout",
            state.reasons[0],
        )

    if state.action == "bullish":
        score = min(100.0, percent_change(state.previous_high, state.last_close) * 10.0)
    elif state.action == "bearish":
        score = max(-100.0, percent_change(state.previous_low, state.last_close) * 10.0)
    else:
        score = 0.0
    return QuantStrategyIdea(
        id="volatility-breakout",
        title="Volatility breakout",
        group="breakout",
        action=state.action,
        score=score,
        confidence=_confidence(abs(score), len(candles)),
        metrics={
            "period": state.period,
            "previous_high": round(state.previous_high, 4),
            "previous_low": round(state.previous_low, 4),
            "last_close": state.last_close,
        },
        reasons=state.reasons,
    )


def _breadth_confirmation_idea(
    breadth_bars_by_symbol: Mapping[str, Sequence[Any]],
) -> QuantStrategyIdea:
    latest_values = [float(bars[-1].close) for bars in breadth_bars_by_symbol.values() if bars]
    state = breadth_confirmation_state(latest_values)
    if state.average is None:
        return _neutral_idea(
            "breadth-confirmation",
            "Breadth confirmation",
            "breadth",
            state.reasons[0],
            metrics={"series_count": 0},
        )

    if state.action == "bullish":
        score = min(100.0, (state.average - 50.0) * 2.0)
    elif state.action == "bearish":
        score = max(-100.0, (state.average - 50.0) * 2.0)
    else:
        score = 0.0
    return QuantStrategyIdea(
        id="breadth-confirmation",
        title="Breadth confirmation",
        group="breadth",
        action=state.action,
        score=score,
        confidence=_confidence(abs(score) * 2.0, len(latest_values) * 20),
        metrics={
            "average_breadth": round(state.average, 4),
            "series_count": state.series_count,
            "strong_series": state.strong_series,
        },
        reasons=state.reasons,
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


def _confidence(score: float, sample_size: int) -> str:
    if score >= 50.0 and sample_size >= 40:
        return "high"
    if score >= 15.0 and sample_size >= 20:
        return "medium"
    return "low"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
