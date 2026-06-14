from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from algo_trading.indicators import ema, rsi
from algo_trading.models import (
    AllowedSide,
    Candle,
    PositionSide,
    Signal,
    SignalType,
    StrategyConfig,
    StrategyName,
    StrategyPreset,
)


@dataclass(frozen=True)
class StrategyContext:
    candles: list[Candle]
    closes: list[float]
    highs: list[float]
    lows: list[float]
    fast: list[float]
    slow: list[float]
    rsi_values: list[float]
    macd: list[float]
    macd_signal: list[float]
    bollinger_mid: list[float]
    bollinger_upper: list[float]
    bollinger_lower: list[float]
    donchian_high: list[float]
    donchian_low: list[float]


class TradingStrategy(Protocol):
    name: StrategyName
    description: str

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        ...

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        ...


def list_strategy_names() -> list[str]:
    return [strategy.value for strategy in StrategyName]


def get_strategy(name: StrategyName | str) -> TradingStrategy:
    strategy_name = name if isinstance(name, StrategyName) else StrategyName(str(name))
    try:
        return _STRATEGIES[strategy_name]
    except KeyError as exc:
        raise ValueError(f"unsupported strategy: {name}") from exc


def apply_strategy_preset(config: StrategyConfig) -> StrategyConfig:
    preset = (
        config.preset
        if isinstance(config.preset, StrategyPreset)
        else StrategyPreset(str(config.preset))
    )
    if preset is StrategyPreset.CUSTOM:
        return config
    if preset is StrategyPreset.CONSERVATIVE:
        return replace(
            config,
            position_fraction=0.5,
            stop_loss_pct=0.02,
            take_profit_pct=0.04,
            trailing_stop_pct=0.015,
            fast_ema=18,
            slow_ema=39,
            rsi_period=21,
            rsi_oversold=35.0,
            rsi_overbought=65.0,
            rsi_midline=50.0,
            macd_signal=12,
            bollinger_period=30,
            bollinger_stddev=2.2,
            donchian_period=30,
        )
    if preset is StrategyPreset.BALANCED:
        return replace(
            config,
            position_fraction=1.0,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            trailing_stop_pct=0.0,
            fast_ema=12,
            slow_ema=26,
            rsi_period=14,
            rsi_oversold=30.0,
            rsi_overbought=70.0,
            rsi_midline=50.0,
            macd_signal=9,
            bollinger_period=20,
            bollinger_stddev=2.0,
            donchian_period=20,
        )
    if preset is StrategyPreset.AGGRESSIVE:
        return replace(
            config,
            position_fraction=1.0,
            stop_loss_pct=0.04,
            take_profit_pct=0.08,
            trailing_stop_pct=0.0,
            fast_ema=6,
            slow_ema=13,
            rsi_period=7,
            rsi_oversold=25.0,
            rsi_overbought=75.0,
            rsi_midline=50.0,
            macd_signal=5,
            bollinger_period=10,
            bollinger_stddev=1.6,
            donchian_period=10,
        )
    raise ValueError(f"unsupported preset: {config.preset}")


def build_strategy_context(candles: list[Candle], config: StrategyConfig) -> StrategyContext:
    closes = [candle.close for candle in candles]
    highs = [candle.high for candle in candles]
    lows = [candle.low for candle in candles]
    fast = ema(closes, config.fast_ema)
    slow = ema(closes, config.slow_ema)
    rsi_values = rsi(closes, config.rsi_period)
    macd = [fast_value - slow_value for fast_value, slow_value in zip(fast, slow)]
    macd_signal = ema(macd, config.macd_signal)
    bollinger_mid = _rolling_mean(closes, config.bollinger_period)
    bollinger_stddev = _rolling_stddev(closes, config.bollinger_period, bollinger_mid)
    bollinger_upper = [
        middle + (stddev * config.bollinger_stddev)
        for middle, stddev in zip(bollinger_mid, bollinger_stddev)
    ]
    bollinger_lower = [
        middle - (stddev * config.bollinger_stddev)
        for middle, stddev in zip(bollinger_mid, bollinger_stddev)
    ]
    return StrategyContext(
        candles=candles,
        closes=closes,
        highs=highs,
        lows=lows,
        fast=fast,
        slow=slow,
        rsi_values=rsi_values,
        macd=macd,
        macd_signal=macd_signal,
        bollinger_mid=bollinger_mid,
        bollinger_upper=bollinger_upper,
        bollinger_lower=bollinger_lower,
        donchian_high=_previous_rolling_high(highs, config.donchian_period),
        donchian_low=_previous_rolling_low(lows, config.donchian_period),
    )


def entry_signal_for_index(
    config: StrategyConfig,
    context: StrategyContext,
    index: int,
) -> Signal:
    return get_strategy(config.strategy).entry_signal(config, context, index)


def exit_signal_for_position(
    side: PositionSide,
    config: StrategyConfig,
    context: StrategyContext,
    index: int,
) -> Signal:
    return get_strategy(config.strategy).exit_signal(side, config, context, index)


class EmaRsiStrategy:
    name = StrategyName.EMA_RSI
    description = "EMA crossover filtered by RSI"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index >= min(len(context.fast), len(context.slow), len(context.rsi_values)):
            return Signal(SignalType.HOLD, "insufficient_data")

        crossed_above = _crossed_above(context.fast, context.slow, index)
        crossed_below = _crossed_below(context.fast, context.slow, index)
        current_rsi = context.rsi_values[index]

        if (
            crossed_above
            and current_rsi < config.rsi_overbought
            and _side_allowed(config, PositionSide.LONG)
        ):
            return Signal(SignalType.ENTER_LONG, "ema_cross_above")

        if (
            crossed_below
            and current_rsi > config.rsi_oversold
            and _side_allowed(config, PositionSide.SHORT)
        ):
            return Signal(SignalType.ENTER_SHORT, "ema_cross_below")

        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index >= min(len(context.fast), len(context.slow)):
            return Signal(SignalType.HOLD, "insufficient_data")
        if side is PositionSide.LONG and _crossed_below(context.fast, context.slow, index):
            return Signal(SignalType.EXIT_LONG, "ema_cross_below")
        if side is PositionSide.SHORT and _crossed_above(context.fast, context.slow, index):
            return Signal(SignalType.EXIT_SHORT, "ema_cross_above")
        return Signal(SignalType.HOLD, "no_signal")


class MacdStrategy:
    name = StrategyName.MACD
    description = "MACD line crossing its signal line"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index >= min(len(context.macd), len(context.macd_signal)):
            return Signal(SignalType.HOLD, "insufficient_data")
        if _crossed_above(context.macd, context.macd_signal, index) and _side_allowed(
            config, PositionSide.LONG
        ):
            return Signal(SignalType.ENTER_LONG, "macd_cross_above")
        if _crossed_below(context.macd, context.macd_signal, index) and _side_allowed(
            config, PositionSide.SHORT
        ):
            return Signal(SignalType.ENTER_SHORT, "macd_cross_below")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index >= min(len(context.macd), len(context.macd_signal)):
            return Signal(SignalType.HOLD, "insufficient_data")
        if side is PositionSide.LONG and _crossed_below(context.macd, context.macd_signal, index):
            return Signal(SignalType.EXIT_LONG, "macd_cross_below")
        if side is PositionSide.SHORT and _crossed_above(context.macd, context.macd_signal, index):
            return Signal(SignalType.EXIT_SHORT, "macd_cross_above")
        return Signal(SignalType.HOLD, "no_signal")


class BollingerReversionStrategy:
    name = StrategyName.BOLLINGER_REVERSION
    description = "Mean reversion after reclaiming Bollinger bands"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index < config.bollinger_period or index >= len(context.closes):
            return Signal(SignalType.HOLD, "insufficient_data")
        previous_close = context.closes[index - 1]
        current_close = context.closes[index]
        if (
            previous_close < context.bollinger_lower[index - 1]
            and current_close > context.bollinger_lower[index]
            and _side_allowed(config, PositionSide.LONG)
        ):
            return Signal(SignalType.ENTER_LONG, "bollinger_lower_reclaim")
        if (
            previous_close > context.bollinger_upper[index - 1]
            and current_close < context.bollinger_upper[index]
            and _side_allowed(config, PositionSide.SHORT)
        ):
            return Signal(SignalType.ENTER_SHORT, "bollinger_upper_reject")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index < config.bollinger_period or index >= len(context.closes):
            return Signal(SignalType.HOLD, "insufficient_data")
        current_close = context.closes[index]
        if side is PositionSide.LONG and current_close >= context.bollinger_mid[index]:
            return Signal(SignalType.EXIT_LONG, "bollinger_mean_reversion")
        if side is PositionSide.SHORT and current_close <= context.bollinger_mid[index]:
            return Signal(SignalType.EXIT_SHORT, "bollinger_mean_reversion")
        return Signal(SignalType.HOLD, "no_signal")


class DonchianBreakoutStrategy:
    name = StrategyName.DONCHIAN_BREAKOUT
    description = "Breakout above or below the previous Donchian channel"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index < config.donchian_period or index >= len(context.closes):
            return Signal(SignalType.HOLD, "insufficient_data")
        current_close = context.closes[index]
        if current_close > context.donchian_high[index] and _side_allowed(config, PositionSide.LONG):
            return Signal(SignalType.ENTER_LONG, "donchian_breakout_high")
        if current_close < context.donchian_low[index] and _side_allowed(config, PositionSide.SHORT):
            return Signal(SignalType.ENTER_SHORT, "donchian_breakout_low")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index < config.donchian_period or index >= len(context.closes):
            return Signal(SignalType.HOLD, "insufficient_data")
        current_close = context.closes[index]
        if side is PositionSide.LONG and current_close < context.donchian_low[index]:
            return Signal(SignalType.EXIT_LONG, "donchian_breakout_low")
        if side is PositionSide.SHORT and current_close > context.donchian_high[index]:
            return Signal(SignalType.EXIT_SHORT, "donchian_breakout_high")
        return Signal(SignalType.HOLD, "no_signal")


class RsiReversalStrategy:
    name = StrategyName.RSI_REVERSAL
    description = "RSI leaving extreme levels and reverting toward the midpoint"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index >= len(context.rsi_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        previous_rsi = context.rsi_values[index - 1]
        current_rsi = context.rsi_values[index]
        if (
            previous_rsi <= config.rsi_oversold
            and current_rsi > config.rsi_oversold
            and _side_allowed(config, PositionSide.LONG)
        ):
            return Signal(SignalType.ENTER_LONG, "rsi_reversal_long")
        if (
            previous_rsi >= config.rsi_overbought
            and current_rsi < config.rsi_overbought
            and _side_allowed(config, PositionSide.SHORT)
        ):
            return Signal(SignalType.ENTER_SHORT, "rsi_reversal_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index >= len(context.rsi_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        previous_rsi = context.rsi_values[index - 1]
        current_rsi = context.rsi_values[index]
        if (
            side is PositionSide.LONG
            and previous_rsi >= config.rsi_midline
            and current_rsi < config.rsi_midline
        ):
            return Signal(SignalType.EXIT_LONG, "rsi_midline_cross_down")
        if (
            side is PositionSide.SHORT
            and previous_rsi <= config.rsi_midline
            and current_rsi > config.rsi_midline
        ):
            return Signal(SignalType.EXIT_SHORT, "rsi_midline_cross_up")
        return Signal(SignalType.HOLD, "no_signal")


def _side_allowed(config: StrategyConfig, side: PositionSide) -> bool:
    if side is PositionSide.LONG:
        return config.allowed_side in {AllowedSide.BOTH, AllowedSide.LONG_ONLY}
    return config.allowed_side in {AllowedSide.BOTH, AllowedSide.SHORT_ONLY}


def _crossed_above(first: list[float], second: list[float], index: int) -> bool:
    return first[index - 1] <= second[index - 1] and first[index] > second[index]


def _crossed_below(first: list[float], second: list[float], index: int) -> bool:
    return first[index - 1] >= second[index - 1] and first[index] < second[index]


def _rolling_mean(values: list[float], period: int) -> list[float]:
    output: list[float] = []
    for index in range(len(values)):
        window = values[max(0, index - period + 1) : index + 1]
        output.append(sum(window) / len(window))
    return output


def _rolling_stddev(values: list[float], period: int, means: list[float]) -> list[float]:
    output: list[float] = []
    for index in range(len(values)):
        window = values[max(0, index - period + 1) : index + 1]
        mean = means[index]
        variance = sum((value - mean) ** 2 for value in window) / len(window)
        output.append(variance**0.5)
    return output


def _previous_rolling_high(values: list[float], period: int) -> list[float]:
    output: list[float] = []
    for index, value in enumerate(values):
        if index == 0:
            output.append(value)
            continue
        window = values[max(0, index - period) : index]
        output.append(max(window))
    return output


def _previous_rolling_low(values: list[float], period: int) -> list[float]:
    output: list[float] = []
    for index, value in enumerate(values):
        if index == 0:
            output.append(value)
            continue
        window = values[max(0, index - period) : index]
        output.append(min(window))
    return output


_STRATEGIES: dict[StrategyName, TradingStrategy] = {
    StrategyName.EMA_RSI: EmaRsiStrategy(),
    StrategyName.MACD: MacdStrategy(),
    StrategyName.BOLLINGER_REVERSION: BollingerReversionStrategy(),
    StrategyName.DONCHIAN_BREAKOUT: DonchianBreakoutStrategy(),
    StrategyName.RSI_REVERSAL: RsiReversalStrategy(),
}
