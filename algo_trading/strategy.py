from __future__ import annotations

from algo_trading.models import (
    AllowedSide,
    PositionSide,
    Signal,
    SignalType,
    StrategyConfig,
)


def signal_for_index(
    config: StrategyConfig,
    fast: list[float],
    slow: list[float],
    rsi_values: list[float],
    index: int,
) -> Signal:
    if index <= 0 or index >= min(len(fast), len(slow), len(rsi_values)):
        return Signal(SignalType.HOLD, "insufficient_data")

    previous_fast = fast[index - 1]
    previous_slow = slow[index - 1]
    current_fast = fast[index]
    current_slow = slow[index]
    current_rsi = rsi_values[index]

    crossed_above = previous_fast <= previous_slow and current_fast > current_slow
    crossed_below = previous_fast >= previous_slow and current_fast < current_slow

    if (
        crossed_above
        and current_rsi < config.rsi_overbought
        and config.allowed_side in {AllowedSide.BOTH, AllowedSide.LONG_ONLY}
    ):
        return Signal(SignalType.ENTER_LONG, "ema_cross_above")

    if (
        crossed_below
        and current_rsi > config.rsi_oversold
        and config.allowed_side in {AllowedSide.BOTH, AllowedSide.SHORT_ONLY}
    ):
        return Signal(SignalType.ENTER_SHORT, "ema_cross_below")

    return Signal(SignalType.HOLD, "no_signal")


def exit_signal_for_position(
    side: PositionSide,
    fast: list[float],
    slow: list[float],
    index: int,
) -> Signal:
    if index <= 0 or index >= min(len(fast), len(slow)):
        return Signal(SignalType.HOLD, "insufficient_data")

    previous_fast = fast[index - 1]
    previous_slow = slow[index - 1]
    current_fast = fast[index]
    current_slow = slow[index]
    crossed_above = previous_fast <= previous_slow and current_fast > current_slow
    crossed_below = previous_fast >= previous_slow and current_fast < current_slow

    if side is PositionSide.LONG and crossed_below:
        return Signal(SignalType.EXIT_LONG, "ema_cross_below")
    if side is PositionSide.SHORT and crossed_above:
        return Signal(SignalType.EXIT_SHORT, "ema_cross_above")
    return Signal(SignalType.HOLD, "no_signal")
