from __future__ import annotations

from algo_trading.models import Candle


def ema(values: list[float], period: int) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    if not values:
        return []

    alpha = 2.0 / (period + 1.0)
    output = [float(values[0])]
    for value in values[1:]:
        output.append((float(value) * alpha) + (output[-1] * (1.0 - alpha)))
    return output


def rsi(values: list[float], period: int = 14) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    if not values:
        return []
    if len(values) <= period:
        return [50.0] * len(values)

    output = [50.0] * period
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, period + 1):
        change = float(values[index]) - float(values[index - 1])
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    output.append(_rsi_from_averages(avg_gain, avg_loss))

    for index in range(period + 1, len(values)):
        change = float(values[index]) - float(values[index - 1])
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        output.append(_rsi_from_averages(avg_gain, avg_loss))

    return output


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0:
        return 100.0
    relative_strength = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def atr(candles: list[Candle], period: int = 14) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    if not candles:
        return []
    ranges: list[float] = []
    previous_close = candles[0].close
    for candle in candles:
        true_range = max(
            candle.high - candle.low,
            abs(candle.high - previous_close),
            abs(candle.low - previous_close),
        )
        ranges.append(true_range)
        previous_close = candle.close
    return rolling_mean(ranges, period)


def rolling_vwap(candles: list[Candle], period: int = 20) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    output: list[float] = []
    for index in range(len(candles)):
        window = candles[max(0, index - period + 1) : index + 1]
        volume = sum(candle.volume for candle in window)
        if volume == 0:
            output.append(sum(_typical_price(candle) for candle in window) / len(window))
            continue
        output.append(
            sum(_typical_price(candle) * candle.volume for candle in window) / volume
        )
    return output


def stochastic_rsi(rsi_values: list[float], period: int = 14) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    output: list[float] = []
    for index, value in enumerate(rsi_values):
        window = rsi_values[max(0, index - period + 1) : index + 1]
        low = min(window)
        high = max(window)
        if high == low:
            output.append(50.0)
        else:
            output.append(((value - low) / (high - low)) * 100.0)
    return output


def momentum(values: list[float], period: int = 10) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    output: list[float] = []
    for index, value in enumerate(values):
        if index < period:
            output.append(0.0)
        else:
            output.append(float(value) - float(values[index - period]))
    return output


def rolling_mean(values: list[float], period: int) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    output: list[float] = []
    for index in range(len(values)):
        window = values[max(0, index - period + 1) : index + 1]
        output.append(sum(window) / len(window))
    return output


def rolling_stddev(values: list[float], period: int, means: list[float]) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    output: list[float] = []
    for index in range(len(values)):
        window = values[max(0, index - period + 1) : index + 1]
        mean = means[index]
        variance = sum((value - mean) ** 2 for value in window) / len(window)
        output.append(variance**0.5)
    return output


def previous_rolling_high(values: list[float], period: int) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    output: list[float] = []
    for index, value in enumerate(values):
        if index == 0:
            output.append(value)
            continue
        window = values[max(0, index - period) : index]
        output.append(max(window))
    return output


def previous_rolling_low(values: list[float], period: int) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    output: list[float] = []
    for index, value in enumerate(values):
        if index == 0:
            output.append(value)
            continue
        window = values[max(0, index - period) : index]
        output.append(min(window))
    return output


def _typical_price(candle: Candle) -> float:
    return (candle.high + candle.low + candle.close) / 3.0
