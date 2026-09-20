from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from algo_trading.models import Candle, SignalType, StrategyConfig, StrategyName
from algo_trading.quant_strategies import percent_change, time_series_momentum_state

MEAN_REVERSION_STRATEGY_NAMES = frozenset(
    {
        StrategyName.BOLLINGER_REVERSION,
        StrategyName.RSI_REVERSAL,
        StrategyName.VWAP_REVERSION,
        StrategyName.STOCH_RSI_REVERSAL,
        StrategyName.CCI_REVERSAL,
        StrategyName.WILLIAMS_R_REVERSAL,
        StrategyName.MFI_REVERSAL,
        StrategyName.ZSCORE_REVERSION,
        StrategyName.RSI_MEAN_REVERSION,
    }
)
TREND_BREAKOUT_STRATEGY_NAMES = frozenset(
    {
        StrategyName.EMA_RSI,
        StrategyName.MACD,
        StrategyName.DONCHIAN_BREAKOUT,
        StrategyName.SUPERTREND,
        StrategyName.EMA_RIBBON,
        StrategyName.MOMENTUM_SCALPING,
        StrategyName.KELTNER_BREAKOUT,
        StrategyName.EMA_PULLBACK,
        StrategyName.ATR_TRAILING_TREND,
        StrategyName.BOLLINGER_SQUEEZE_RELEASE,
        StrategyName.OBV_TREND,
        StrategyName.VOLUME_BREAKOUT,
        StrategyName.VWAP_TREND_CONTINUATION,
        StrategyName.SMA_CROSSOVER,
        StrategyName.ADX_TREND,
        StrategyName.ICHIMOKU_BREAKOUT,
        StrategyName.PARABOLIC_SAR,
        StrategyName.TIME_SERIES_MOMENTUM,
        StrategyName.VOLATILITY_BREAKOUT,
    }
)
US_CASH_START_MINUTES = 9 * 60 + 30
US_CASH_END_MINUTES = 16 * 60
EUROPE_START_MINUTES = 3 * 60
OVERNIGHT_END_MINUTES = 18 * 60
INTERVAL_UNITS = {"m": 1, "h": 60, "d": 60 * 24, "w": 60 * 24 * 7}


@dataclass(frozen=True)
class ComboEnsembleSnapshot:
    regime: str
    session: str
    higher_tf_bias: int
    relative_strength_bias: int
    member_count: int
    long_votes: list[str]
    short_votes: list[str]
    vote_weights: dict[str, float]


def higher_timeframe_interval(interval: str, multiple: int = 4) -> str:
    amount, unit = _parse_interval(interval)
    scaled = max(1, amount * max(1, multiple))
    if unit == "M":
        return f"{scaled}M"
    minutes = scaled * INTERVAL_UNITS[unit]
    if minutes % (60 * 24 * 7) == 0:
        return f"{minutes // (60 * 24 * 7)}w"
    if minutes % (60 * 24) == 0:
        return f"{minutes // (60 * 24)}d"
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes}m"


def volatility_regime_series(
    metric_values: list[float],
    *,
    lookback: int,
    low_percentile: float,
    high_percentile: float,
) -> list[str]:
    regimes: list[str] = []
    for index in range(len(metric_values)):
        window = metric_values[max(0, index - lookback + 1) : index + 1]
        if lookback <= 0 or len(window) < lookback:
            regimes.append("mid")
            continue
        percentile = _percentile_rank(window, metric_values[index])
        if percentile <= low_percentile:
            regimes.append("low")
        elif percentile >= high_percentile:
            regimes.append("high")
        else:
            regimes.append("mid")
    return regimes


def atr_pct_values(atr_values: list[float], closes: list[float]) -> list[float]:
    return [
        0.0 if close == 0.0 else (atr_value / close) * 100.0
        for atr_value, close in zip(atr_values, closes)
    ]


def directional_bias_from_candles(candles: list[Candle], lookback: int = 20) -> int:
    if len(candles) < 2:
        return 0
    state = time_series_momentum_state(candles, lookback=min(lookback, len(candles) - 1))
    if state.action == "bullish":
        return 1
    if state.action == "bearish":
        return -1
    return 0


def relative_strength_bias_from_candles(
    base_candles: list[Candle],
    pair_candles: list[Candle],
    lookback: int = 20,
) -> int:
    if len(base_candles) < 2 or len(pair_candles) < 2:
        return 0
    base_lookback = min(lookback, len(base_candles) - 1)
    pair_lookback = min(lookback, len(pair_candles) - 1)
    base_return = percent_change(base_candles[-base_lookback - 1].close, base_candles[-1].close)
    pair_return = percent_change(pair_candles[-pair_lookback - 1].close, pair_candles[-1].close)
    if base_return > pair_return:
        return 1
    if base_return < pair_return:
        return -1
    return 0


def session_name(open_time: int, timezone_name: str = "America/New_York") -> str:
    moment = datetime.fromtimestamp(open_time / 1000, tz=UTC).astimezone(ZoneInfo(timezone_name))
    if moment.weekday() >= 5:
        return "overnight"
    minutes = (moment.hour * 60) + moment.minute
    if US_CASH_START_MINUTES <= minutes < US_CASH_END_MINUTES:
        return "us-cash"
    if EUROPE_START_MINUTES <= minutes < US_CASH_START_MINUTES:
        return "europe"
    if US_CASH_END_MINUTES <= minutes < OVERNIGHT_END_MINUTES:
        return "overnight"
    return "asia"


def preferred_sessions(config: StrategyConfig) -> set[str]:
    return {
        name.strip().lower()
        for name in config.combo_session_preferred.split(",")
        if name.strip()
    }


def combo_member_vote_weight(
    strategy_name: StrategyName,
    signal_type: SignalType,
    config: StrategyConfig,
    *,
    regime: str,
    higher_tf_bias: int,
    relative_strength_bias: int,
    session: str,
) -> float:
    if signal_type not in {
        SignalType.ENTER_LONG,
        SignalType.ENTER_SHORT,
        SignalType.EXIT_LONG,
        SignalType.EXIT_SHORT,
    }:
        return 0.0

    weight = 1.0
    if config.combo_regime_filter:
        mismatched = (regime == "high" and strategy_name in MEAN_REVERSION_STRATEGY_NAMES) or (
            regime == "low" and strategy_name in TREND_BREAKOUT_STRATEGY_NAMES
        )
        if mismatched:
            weight *= config.combo_regime_mismatch_weight

    is_entry = signal_type in {SignalType.ENTER_LONG, SignalType.ENTER_SHORT}
    if is_entry and config.combo_mtf_filter and higher_tf_bias != 0:
        disagrees = (signal_type is SignalType.ENTER_LONG and higher_tf_bias < 0) or (
            signal_type is SignalType.ENTER_SHORT and higher_tf_bias > 0
        )
        if disagrees:
            weight *= 0.0 if config.combo_mtf_mode == "hard" else config.combo_mtf_soft_weight

    if is_entry and config.combo_rs_filter and relative_strength_bias != 0:
        disagrees = (signal_type is SignalType.ENTER_LONG and relative_strength_bias < 0) or (
            signal_type is SignalType.ENTER_SHORT and relative_strength_bias > 0
        )
        if disagrees:
            weight *= config.combo_rs_soft_weight

    if config.combo_session_filter and session not in preferred_sessions(config):
        weight *= config.combo_session_off_weight
    return weight


def vote_counts(weight: float, min_vote_weight: float) -> bool:
    return weight >= min_vote_weight


def aligned_directional_bias(
    base_candles: list[Candle],
    other_candles: list[Candle] | None,
    *,
    explicit_bias: int | None,
    lookback: int = 20,
) -> list[int]:
    if explicit_bias is not None:
        return [int(explicit_bias)] * len(base_candles)
    if not other_candles:
        return [0] * len(base_candles)
    return [
        directional_bias_from_candles(
            [candle for candle in other_candles if candle.open_time <= base.open_time],
            lookback,
        )
        for base in base_candles
    ]


def aligned_relative_strength_bias(
    base_candles: list[Candle],
    pair_candles: list[Candle] | None,
    *,
    explicit_bias: int | None,
    lookback: int = 20,
) -> list[int]:
    if explicit_bias is not None:
        return [int(explicit_bias)] * len(base_candles)
    if not pair_candles:
        return [0] * len(base_candles)
    return [
        relative_strength_bias_from_candles(
            [candle for candle in base_candles if candle.open_time <= base.open_time],
            [candle for candle in pair_candles if candle.open_time <= base.open_time],
            lookback,
        )
        for base in base_candles
    ]


def aligned_breadth_values(
    candles: list[Candle],
    breadth_bars_by_symbol: Mapping[str, Sequence[Any]] | None,
) -> list[float | None]:
    if not candles:
        return []
    if not breadth_bars_by_symbol:
        return [None] * len(candles)

    series: list[list[tuple[date, float]]] = []
    for bars in breadth_bars_by_symbol.values():
        dated = sorted((bar.date, float(bar.close)) for bar in bars)
        if dated:
            series.append(dated)
    if not series:
        return [None] * len(candles)

    values: list[float | None] = []
    for candle in candles:
        candle_date = datetime.fromtimestamp(candle.open_time / 1000, tz=UTC).date()
        latest_values: list[float] = []
        for dated in series:
            latest = None
            for bar_date, close in dated:
                if bar_date <= candle_date:
                    latest = close
                else:
                    break
            if latest is not None:
                latest_values.append(latest)
        values.append(sum(latest_values) / len(latest_values) if latest_values else None)
    return values


def _percentile_rank(window: list[float], value: float) -> float:
    below = sum(1 for item in window if item < value)
    equal = sum(1 for item in window if item == value)
    return ((below + (0.5 * equal)) / len(window)) * 100.0


def _parse_interval(interval: str) -> tuple[int, str]:
    value = str(interval).strip()
    if not value:
        raise ValueError("interval is required")
    unit = value[-1]
    if unit not in {"m", "h", "d", "w", "M"}:
        raise ValueError(f"unsupported interval: {interval}")
    try:
        amount = int(value[:-1])
    except ValueError as exc:
        raise ValueError(f"unsupported interval: {interval}") from exc
    if amount <= 0:
        raise ValueError(f"unsupported interval: {interval}")
    return amount, unit
