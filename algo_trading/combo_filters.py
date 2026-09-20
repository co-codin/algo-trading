from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from algo_trading.models import Candle, StrategyConfig, StrategyName

_NY = ZoneInfo("America/New_York")
_REAL_TIMESTAMP_MS = 1_000_000_000_000
_REAL_TIMESTAMP_SECONDS = 1_000_000_000

_INTERVAL_MINUTES: dict[str, int] = {
    "1m": 1,
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "20m": 20,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "6h": 360,
    "8h": 480,
    "12h": 720,
    "1d": 1440,
    "3d": 4320,
    "1w": 10080,
    "1M": 43200,
}

_KNOWN_INTERVALS = tuple(
    sorted(_INTERVAL_MINUTES.items(), key=lambda item: item[1])
)

STRATEGY_FAMILIES: dict[StrategyName, str] = {
    StrategyName.EMA_RSI: "trend",
    StrategyName.MACD: "trend",
    StrategyName.BOLLINGER_REVERSION: "mean_reversion",
    StrategyName.DONCHIAN_BREAKOUT: "breakout",
    StrategyName.RSI_REVERSAL: "mean_reversion",
    StrategyName.SUPERTREND: "trend",
    StrategyName.VWAP_REVERSION: "mean_reversion",
    StrategyName.STOCH_RSI_REVERSAL: "mean_reversion",
    StrategyName.EMA_RIBBON: "trend",
    StrategyName.MOMENTUM_SCALPING: "breakout",
    StrategyName.KELTNER_BREAKOUT: "breakout",
    StrategyName.EMA_PULLBACK: "trend",
    StrategyName.ATR_TRAILING_TREND: "trend",
    StrategyName.CCI_REVERSAL: "mean_reversion",
    StrategyName.WILLIAMS_R_REVERSAL: "mean_reversion",
    StrategyName.BOLLINGER_SQUEEZE_RELEASE: "breakout",
    StrategyName.OBV_TREND: "trend",
    StrategyName.VOLUME_BREAKOUT: "breakout",
    StrategyName.VWAP_TREND_CONTINUATION: "trend",
    StrategyName.SMA_CROSSOVER: "trend",
    StrategyName.ADX_TREND: "trend",
    StrategyName.ICHIMOKU_BREAKOUT: "breakout",
    StrategyName.MFI_REVERSAL: "mean_reversion",
    StrategyName.PARABOLIC_SAR: "trend",
    StrategyName.ZSCORE_REVERSION: "mean_reversion",
    StrategyName.TIME_SERIES_MOMENTUM: "trend",
    StrategyName.VOLATILITY_BREAKOUT: "breakout",
    StrategyName.RSI_MEAN_REVERSION: "mean_reversion",
    StrategyName.BREADTH_CONFIRMATION: "breadth",
}

_TREND_LIKE = {"trend", "breakout"}


def strategy_family(name: StrategyName | str) -> str:
    strategy_name = name if isinstance(name, StrategyName) else StrategyName(str(name))
    return STRATEGY_FAMILIES.get(strategy_name, "trend")


def default_higher_tf_interval(interval: str) -> str:
    minutes = _interval_minutes(interval)
    target = minutes * 4
    for name, value in _KNOWN_INTERVALS:
        if value == target:
            return name
    for name, value in _KNOWN_INTERVALS:
        if value >= target:
            return name
    return "1M"


def classify_vol_regime(
    values: list[float],
    *,
    lookback: int,
    low_pct: float,
    high_pct: float,
) -> str:
    if lookback <= 0 or len(values) < lookback:
        return "unknown"
    window = values[-lookback:]
    current = window[-1]
    rank = sum(1 for value in window if value <= current)
    percentile = (rank / len(window)) * 100.0
    if percentile >= high_pct:
        return "high"
    if percentile <= low_pct:
        return "low"
    return "mid"


def classify_session(open_time: int) -> str | None:
    dt = _datetime_from_open_time(open_time)
    if dt is None:
        return None
    minutes = (dt.hour * 60) + dt.minute
    if 9 * 60 + 30 <= minutes < 16 * 60:
        return "us_cash"
    if 16 * 60 <= minutes < 18 * 60:
        return "overnight"
    if 3 * 60 <= minutes < 9 * 60 + 30:
        return "europe"
    return "asia"


def relative_strength_bias(
    symbol_candles: list[Candle],
    pair_candles: list[Candle],
    *,
    lookback: int,
    index: int,
) -> int | None:
    if not pair_candles or lookback <= 0 or index <= 0:
        return None
    symbol_return = _aligned_return(symbol_candles, lookback, index)
    pair_index = _aligned_index(pair_candles, symbol_candles[index].open_time, index)
    pair_return = _aligned_return(pair_candles, lookback, pair_index)
    if symbol_return is None or pair_return is None:
        return None
    delta = symbol_return - pair_return
    if delta > 0:
        return 1
    if delta < 0:
        return -1
    return 0


def higher_tf_bias_from_candles(candles: list[Candle], config: StrategyConfig) -> int | None:
    if len(candles) < 2:
        return None
    start = candles[0].close
    end = candles[-1].close
    if start == 0:
        return 0
    change = ((end - start) / start) * 100.0
    if change > 0:
        return 1
    if change < 0:
        return -1
    return 0


def vote_weight(
    config: StrategyConfig,
    *,
    family: str,
    direction: int,
    regime: str,
    higher_tf_bias: int | None,
    session: str | None,
    rs_bias: int | None,
) -> float:
    weight = 1.0
    if config.combo_regime_filter:
        if regime == "high" and family == "mean_reversion":
            weight *= config.combo_regime_damp_weight
        elif regime == "low" and family in _TREND_LIKE:
            weight *= config.combo_regime_damp_weight
    weight *= _mtf_weight(config, direction, higher_tf_bias)
    if config.combo_session_filter and session:
        weight *= _session_weight(config, session)
    if config.combo_rs_enabled and rs_bias is not None and rs_bias != 0:
        if (direction > 0 and rs_bias < 0) or (direction < 0 and rs_bias > 0):
            weight *= config.combo_rs_disagree_weight
    return weight


def vote_counts(weight: float, threshold: float) -> bool:
    return weight >= threshold


def _mtf_weight(config: StrategyConfig, direction: int, higher_tf_bias: int | None) -> float:
    mode = str(config.combo_mtf_mode).strip().lower()
    if mode in {"", "off"} or higher_tf_bias in {None, 0}:
        return 1.0
    if direction == higher_tf_bias:
        return 1.0
    if mode == "hard":
        return 0.0
    if mode == "soft":
        return config.combo_mtf_disagree_weight
    return 1.0


def _session_weight(config: StrategyConfig, session: str) -> float:
    if session == "us_cash":
        return config.combo_session_us_cash_weight
    if session == "europe":
        return config.combo_session_europe_weight
    if session == "asia":
        return config.combo_session_asia_weight
    if session == "overnight":
        return config.combo_session_overnight_weight
    return 1.0


def _interval_minutes(interval: str) -> int:
    value = interval.strip()
    if value in _INTERVAL_MINUTES:
        return _INTERVAL_MINUTES[value]
    if len(value) < 2:
        raise ValueError(f"unsupported interval: {interval}")
    amount = int(value[:-1])
    unit = value[-1]
    if amount <= 0:
        raise ValueError(f"unsupported interval: {interval}")
    if unit == "m":
        return amount
    if unit == "h":
        return amount * 60
    if unit == "d":
        return amount * 1440
    if unit == "w":
        return amount * 10080
    if unit == "M":
        return amount * 43200
    raise ValueError(f"unsupported interval: {interval}")


def _datetime_from_open_time(open_time: int) -> datetime | None:
    if open_time >= _REAL_TIMESTAMP_MS:
        return datetime.fromtimestamp(open_time / 1000, tz=_NY)
    if open_time >= _REAL_TIMESTAMP_SECONDS:
        return datetime.fromtimestamp(open_time, tz=_NY)
    return None


def _aligned_index(candles: list[Candle], open_time: int, fallback_index: int) -> int:
    if len(candles) == 0:
        return fallback_index
    for index in range(len(candles) - 1, -1, -1):
        if candles[index].open_time <= open_time:
            return index
    return min(fallback_index, len(candles) - 1)


def _aligned_return(candles: list[Candle], lookback: int, index: int) -> float | None:
    if index < 0 or index >= len(candles):
        return None
    start_index = max(0, index - lookback)
    if start_index >= index:
        return None
    start = candles[start_index].close
    end = candles[index].close
    if start == 0:
        return None
    return ((end - start) / start) * 100.0
