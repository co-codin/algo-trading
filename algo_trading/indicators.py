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


def keltner_channels(
    candles: list[Candle],
    period: int = 20,
    multiplier: float = 2.0,
) -> tuple[list[float], list[float], list[float]]:
    if multiplier <= 0:
        raise ValueError("multiplier must be positive")
    closes = [candle.close for candle in candles]
    middle = ema(closes, period)
    ranges = atr(candles, period)
    upper = [mid + (multiplier * width) for mid, width in zip(middle, ranges)]
    lower = [mid - (multiplier * width) for mid, width in zip(middle, ranges)]
    return middle, upper, lower


def commodity_channel_index(candles: list[Candle], period: int = 20) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    typical_prices = [_typical_price(candle) for candle in candles]
    output: list[float] = []
    for index, typical_price in enumerate(typical_prices):
        if index < period - 1:
            output.append(0.0)
            continue
        window = typical_prices[index - period + 1 : index + 1]
        mean = sum(window) / period
        mean_deviation = sum(abs(value - mean) for value in window) / period
        if mean_deviation == 0.0:
            output.append(0.0)
        else:
            output.append((typical_price - mean) / (0.015 * mean_deviation))
    return output


def williams_r(candles: list[Candle], period: int = 14) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    output: list[float] = []
    for index, candle in enumerate(candles):
        window = candles[max(0, index - period + 1) : index + 1]
        highest_high = max(item.high for item in window)
        lowest_low = min(item.low for item in window)
        width = highest_high - lowest_low
        if width == 0.0:
            output.append(-50.0)
        else:
            output.append(((highest_high - candle.close) / width) * -100.0)
    return output


def on_balance_volume(candles: list[Candle]) -> list[float]:
    if not candles:
        return []
    output = [0.0]
    for index in range(1, len(candles)):
        previous = candles[index - 1]
        current = candles[index]
        if current.close > previous.close:
            output.append(output[-1] + current.volume)
        elif current.close < previous.close:
            output.append(output[-1] - current.volume)
        else:
            output.append(output[-1])
    return output


def directional_movement_index(
    candles: list[Candle],
    period: int = 14,
) -> tuple[list[float], list[float], list[float]]:
    if period <= 0:
        raise ValueError("period must be positive")
    if not candles:
        return [], [], []

    plus_dm = [0.0]
    minus_dm = [0.0]
    true_ranges = [candles[0].high - candles[0].low]
    previous_close = candles[0].close
    for index in range(1, len(candles)):
        previous = candles[index - 1]
        current = candles[index]
        up_move = current.high - previous.high
        down_move = previous.low - current.low
        plus_dm.append(up_move if up_move > down_move and up_move > 0.0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0.0 else 0.0)
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous_close),
                abs(current.low - previous_close),
            )
        )
        previous_close = current.close

    smoothed_tr = rolling_mean(true_ranges, period)
    smoothed_plus = rolling_mean(plus_dm, period)
    smoothed_minus = rolling_mean(minus_dm, period)
    plus_di: list[float] = []
    minus_di: list[float] = []
    dx_values: list[float] = []
    for true_range, plus_value, minus_value in zip(
        smoothed_tr,
        smoothed_plus,
        smoothed_minus,
    ):
        if true_range == 0.0:
            plus = 0.0
            minus = 0.0
        else:
            plus = (plus_value / true_range) * 100.0
            minus = (minus_value / true_range) * 100.0
        plus_di.append(plus)
        minus_di.append(minus)
        total = plus + minus
        dx_values.append(0.0 if total == 0.0 else (abs(plus - minus) / total) * 100.0)

    return plus_di, minus_di, rolling_mean(dx_values, period)


def ichimoku_cloud(
    candles: list[Candle],
    conversion_period: int = 9,
    base_period: int = 26,
    span_b_period: int = 52,
) -> tuple[list[float], list[float], list[float], list[float]]:
    if min(conversion_period, base_period, span_b_period) <= 0:
        raise ValueError("period must be positive")
    conversion = _rolling_midpoint(candles, conversion_period)
    base = _rolling_midpoint(candles, base_period)
    span_b = _rolling_midpoint(candles, span_b_period)
    span_a = [
        (conversion_value + base_value) / 2.0
        for conversion_value, base_value in zip(conversion, base)
    ]
    return conversion, base, span_a, span_b


def money_flow_index(candles: list[Candle], period: int = 14) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    if not candles:
        return []

    typical_prices = [_typical_price(candle) for candle in candles]
    output: list[float] = []
    for index in range(len(typical_prices)):
        if index < period:
            output.append(50.0)
            continue
        positive_flow = 0.0
        negative_flow = 0.0
        for flow_index in range(index - period + 1, index + 1):
            raw_flow = typical_prices[flow_index] * candles[flow_index].volume
            if typical_prices[flow_index] > typical_prices[flow_index - 1]:
                positive_flow += raw_flow
            elif typical_prices[flow_index] < typical_prices[flow_index - 1]:
                negative_flow += raw_flow
        if negative_flow == 0.0:
            output.append(100.0 if positive_flow > 0.0 else 50.0)
        elif positive_flow == 0.0:
            output.append(0.0)
        else:
            money_ratio = positive_flow / negative_flow
            output.append(100.0 - (100.0 / (1.0 + money_ratio)))
    return output


def parabolic_sar(
    candles: list[Candle],
    step: float = 0.02,
    max_step: float = 0.2,
) -> tuple[list[float], list[int]]:
    if step <= 0 or max_step <= 0:
        raise ValueError("step values must be positive")
    if not candles:
        return [], []

    is_uptrend = len(candles) == 1 or candles[1].close >= candles[0].close
    sar = [candles[0].low if is_uptrend else candles[0].high]
    trend = [1 if is_uptrend else -1]
    extreme_point = candles[0].high if is_uptrend else candles[0].low
    acceleration = step

    for index in range(1, len(candles)):
        current = candles[index]
        previous = candles[index - 1]
        current_sar = sar[-1] + acceleration * (extreme_point - sar[-1])

        if is_uptrend:
            current_sar = min(current_sar, previous.low)
            if index > 1:
                current_sar = min(current_sar, candles[index - 2].low)
            if current.low < current_sar:
                is_uptrend = False
                current_sar = extreme_point
                extreme_point = current.low
                acceleration = step
            elif current.high > extreme_point:
                extreme_point = current.high
                acceleration = min(max_step, acceleration + step)
        else:
            current_sar = max(current_sar, previous.high)
            if index > 1:
                current_sar = max(current_sar, candles[index - 2].high)
            if current.high > current_sar:
                is_uptrend = True
                current_sar = extreme_point
                extreme_point = current.high
                acceleration = step
            elif current.low < extreme_point:
                extreme_point = current.low
                acceleration = min(max_step, acceleration + step)

        sar.append(current_sar)
        trend.append(1 if is_uptrend else -1)

    return sar, trend


def rolling_zscore(values: list[float], period: int) -> list[float]:
    means = rolling_mean(values, period)
    stddevs = rolling_stddev(values, period, means)
    output: list[float] = []
    for value, mean, stddev in zip(values, means, stddevs):
        output.append(0.0 if stddev == 0.0 else (value - mean) / stddev)
    return output


def rolling_volume_mean(candles: list[Candle], period: int = 20) -> list[float]:
    return rolling_mean([candle.volume for candle in candles], period)


def bollinger_width(
    upper: list[float],
    lower: list[float],
    middle: list[float],
) -> list[float]:
    output: list[float] = []
    for upper_value, lower_value, middle_value in zip(upper, lower, middle):
        if middle_value == 0.0:
            output.append(0.0)
        else:
            output.append((upper_value - lower_value) / middle_value)
    return output


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


def _rolling_midpoint(candles: list[Candle], period: int) -> list[float]:
    output: list[float] = []
    for index in range(len(candles)):
        window = candles[max(0, index - period + 1) : index + 1]
        high = max(candle.high for candle in window)
        low = min(candle.low for candle in window)
        output.append((high + low) / 2.0)
    return output
