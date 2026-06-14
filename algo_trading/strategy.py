from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from algo_trading.indicators import (
    atr,
    ema,
    momentum,
    previous_rolling_high,
    previous_rolling_low,
    rolling_mean,
    rolling_stddev,
    rolling_vwap,
    rsi,
    stochastic_rsi,
)
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
    atr_values: list[float]
    supertrend_direction: list[int]
    vwap: list[float]
    stoch_rsi_values: list[float]
    ema_ribbon_fast_values: list[float]
    ema_ribbon_mid_values: list[float]
    ema_ribbon_slow_values: list[float]
    momentum_values: list[float]


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
            atr_period=21,
            supertrend_multiplier=3.5,
            vwap_period=30,
            vwap_threshold_pct=0.012,
            stoch_rsi_period=21,
            stoch_rsi_oversold=25.0,
            stoch_rsi_overbought=75.0,
            ema_ribbon_fast=13,
            ema_ribbon_mid=34,
            ema_ribbon_slow=89,
            momentum_period=14,
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
            atr_period=14,
            supertrend_multiplier=3.0,
            vwap_period=20,
            vwap_threshold_pct=0.01,
            stoch_rsi_period=14,
            stoch_rsi_oversold=20.0,
            stoch_rsi_overbought=80.0,
            ema_ribbon_fast=8,
            ema_ribbon_mid=21,
            ema_ribbon_slow=55,
            momentum_period=10,
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
            atr_period=7,
            supertrend_multiplier=2.0,
            vwap_period=10,
            vwap_threshold_pct=0.004,
            stoch_rsi_period=7,
            stoch_rsi_oversold=15.0,
            stoch_rsi_overbought=85.0,
            ema_ribbon_fast=5,
            ema_ribbon_mid=13,
            ema_ribbon_slow=34,
            momentum_period=5,
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
    bollinger_mid = rolling_mean(closes, config.bollinger_period)
    bollinger_stddev = rolling_stddev(closes, config.bollinger_period, bollinger_mid)
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
        donchian_high=previous_rolling_high(highs, config.donchian_period),
        donchian_low=previous_rolling_low(lows, config.donchian_period),
        atr_values=atr(candles, config.atr_period),
        supertrend_direction=_supertrend_direction(candles, config),
        vwap=rolling_vwap(candles, config.vwap_period),
        stoch_rsi_values=stochastic_rsi(rsi_values, config.stoch_rsi_period),
        ema_ribbon_fast_values=ema(closes, config.ema_ribbon_fast),
        ema_ribbon_mid_values=ema(closes, config.ema_ribbon_mid),
        ema_ribbon_slow_values=ema(closes, config.ema_ribbon_slow),
        momentum_values=momentum(closes, config.momentum_period),
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


class SuperTrendStrategy:
    name = StrategyName.SUPERTREND
    description = "ATR SuperTrend-style trend flip"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index < config.atr_period or index >= len(context.supertrend_direction):
            return Signal(SignalType.HOLD, "insufficient_data")
        previous = context.supertrend_direction[index - 1]
        current = context.supertrend_direction[index]
        if previous <= 0 < current and _side_allowed(config, PositionSide.LONG):
            return Signal(SignalType.ENTER_LONG, "supertrend_flip_long")
        if previous >= 0 > current and _side_allowed(config, PositionSide.SHORT):
            return Signal(SignalType.ENTER_SHORT, "supertrend_flip_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index >= len(context.supertrend_direction):
            return Signal(SignalType.HOLD, "insufficient_data")
        current = context.supertrend_direction[index]
        if side is PositionSide.LONG and current < 0:
            return Signal(SignalType.EXIT_LONG, "supertrend_flip_short")
        if side is PositionSide.SHORT and current > 0:
            return Signal(SignalType.EXIT_SHORT, "supertrend_flip_long")
        return Signal(SignalType.HOLD, "no_signal")


class VwapReversionStrategy:
    name = StrategyName.VWAP_REVERSION
    description = "Mean reversion after reclaiming rolling VWAP"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index < config.vwap_period or index >= len(context.vwap):
            return Signal(SignalType.HOLD, "insufficient_data")
        previous_close = context.closes[index - 1]
        current_close = context.closes[index]
        previous_vwap = context.vwap[index - 1]
        current_vwap = context.vwap[index]
        threshold = config.vwap_threshold_pct
        if (
            previous_close < previous_vwap * (1.0 - threshold)
            and current_close >= current_vwap
            and _side_allowed(config, PositionSide.LONG)
        ):
            return Signal(SignalType.ENTER_LONG, "vwap_reclaim_long")
        if (
            previous_close > previous_vwap * (1.0 + threshold)
            and current_close <= current_vwap
            and _side_allowed(config, PositionSide.SHORT)
        ):
            return Signal(SignalType.ENTER_SHORT, "vwap_reject_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index >= len(context.vwap):
            return Signal(SignalType.HOLD, "insufficient_data")
        current_close = context.closes[index]
        current_vwap = context.vwap[index]
        if side is PositionSide.LONG and current_close >= current_vwap:
            return Signal(SignalType.EXIT_LONG, "vwap_mean_reversion")
        if side is PositionSide.SHORT and current_close <= current_vwap:
            return Signal(SignalType.EXIT_SHORT, "vwap_mean_reversion")
        return Signal(SignalType.HOLD, "no_signal")


class StochRsiReversalStrategy:
    name = StrategyName.STOCH_RSI_REVERSAL
    description = "Stochastic RSI leaving extreme levels"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index >= len(context.stoch_rsi_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        previous = context.stoch_rsi_values[index - 1]
        current = context.stoch_rsi_values[index]
        if (
            previous <= config.stoch_rsi_oversold
            and current > config.stoch_rsi_oversold
            and _side_allowed(config, PositionSide.LONG)
        ):
            return Signal(SignalType.ENTER_LONG, "stoch_rsi_reversal_long")
        if (
            previous >= config.stoch_rsi_overbought
            and current < config.stoch_rsi_overbought
            and _side_allowed(config, PositionSide.SHORT)
        ):
            return Signal(SignalType.ENTER_SHORT, "stoch_rsi_reversal_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index >= len(context.stoch_rsi_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        current = context.stoch_rsi_values[index]
        if side is PositionSide.LONG and current >= 50.0:
            return Signal(SignalType.EXIT_LONG, "stoch_rsi_midline")
        if side is PositionSide.SHORT and current <= 50.0:
            return Signal(SignalType.EXIT_SHORT, "stoch_rsi_midline")
        return Signal(SignalType.HOLD, "no_signal")


class EmaRibbonStrategy:
    name = StrategyName.EMA_RIBBON
    description = "EMA ribbon alignment trend following"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index >= len(context.ema_ribbon_slow_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        was_bullish = _ribbon_bullish(context, index - 1)
        is_bullish = _ribbon_bullish(context, index)
        was_bearish = _ribbon_bearish(context, index - 1)
        is_bearish = _ribbon_bearish(context, index)
        if not was_bullish and is_bullish and _side_allowed(config, PositionSide.LONG):
            return Signal(SignalType.ENTER_LONG, "ema_ribbon_bullish")
        if not was_bearish and is_bearish and _side_allowed(config, PositionSide.SHORT):
            return Signal(SignalType.ENTER_SHORT, "ema_ribbon_bearish")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index >= len(context.ema_ribbon_slow_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        if side is PositionSide.LONG and not _ribbon_bullish(context, index):
            return Signal(SignalType.EXIT_LONG, "ema_ribbon_bullish_lost")
        if side is PositionSide.SHORT and not _ribbon_bearish(context, index):
            return Signal(SignalType.EXIT_SHORT, "ema_ribbon_bearish_lost")
        return Signal(SignalType.HOLD, "no_signal")


class MomentumScalpingStrategy:
    name = StrategyName.MOMENTUM_SCALPING
    description = "Short-term momentum with RSI and MACD confirmation"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index < config.momentum_period or index >= len(context.momentum_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        bullish = (
            context.momentum_values[index - 1] <= 0 < context.momentum_values[index]
            and context.rsi_values[index] >= config.rsi_midline
            and context.macd[index] > context.macd_signal[index]
        )
        bearish = (
            context.momentum_values[index - 1] >= 0 > context.momentum_values[index]
            and context.rsi_values[index] <= config.rsi_midline
            and context.macd[index] < context.macd_signal[index]
        )
        if bullish and _side_allowed(config, PositionSide.LONG):
            return Signal(SignalType.ENTER_LONG, "momentum_scalping_long")
        if bearish and _side_allowed(config, PositionSide.SHORT):
            return Signal(SignalType.ENTER_SHORT, "momentum_scalping_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index >= len(context.momentum_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        if side is PositionSide.LONG and context.momentum_values[index] < 0:
            return Signal(SignalType.EXIT_LONG, "momentum_faded")
        if side is PositionSide.SHORT and context.momentum_values[index] > 0:
            return Signal(SignalType.EXIT_SHORT, "momentum_faded")
        return Signal(SignalType.HOLD, "no_signal")


def _side_allowed(config: StrategyConfig, side: PositionSide) -> bool:
    if side is PositionSide.LONG:
        return config.allowed_side in {AllowedSide.BOTH, AllowedSide.LONG_ONLY}
    return config.allowed_side in {AllowedSide.BOTH, AllowedSide.SHORT_ONLY}


def _crossed_above(first: list[float], second: list[float], index: int) -> bool:
    return first[index - 1] <= second[index - 1] and first[index] > second[index]


def _crossed_below(first: list[float], second: list[float], index: int) -> bool:
    return first[index - 1] >= second[index - 1] and first[index] < second[index]


def _ribbon_bullish(context: StrategyContext, index: int) -> bool:
    return (
        context.ema_ribbon_fast_values[index]
        > context.ema_ribbon_mid_values[index]
        > context.ema_ribbon_slow_values[index]
    )


def _ribbon_bearish(context: StrategyContext, index: int) -> bool:
    return (
        context.ema_ribbon_fast_values[index]
        < context.ema_ribbon_mid_values[index]
        < context.ema_ribbon_slow_values[index]
    )


def _supertrend_direction(candles: list[Candle], config: StrategyConfig) -> list[int]:
    if not candles:
        return []
    atr_values = atr(candles, config.atr_period)
    final_upper: list[float] = []
    final_lower: list[float] = []
    direction: list[int] = []
    for index, candle in enumerate(candles):
        midpoint = (candle.high + candle.low) / 2.0
        basic_upper = midpoint + (config.supertrend_multiplier * atr_values[index])
        basic_lower = midpoint - (config.supertrend_multiplier * atr_values[index])
        if index == 0:
            final_upper.append(basic_upper)
            final_lower.append(basic_lower)
            direction.append(0)
            continue

        previous_candle = candles[index - 1]
        upper = (
            basic_upper
            if basic_upper < final_upper[index - 1]
            or previous_candle.close > final_upper[index - 1]
            else final_upper[index - 1]
        )
        lower = (
            basic_lower
            if basic_lower > final_lower[index - 1]
            or previous_candle.close < final_lower[index - 1]
            else final_lower[index - 1]
        )
        final_upper.append(upper)
        final_lower.append(lower)

        if candle.close > final_upper[index - 1]:
            direction.append(1)
        elif candle.close < final_lower[index - 1]:
            direction.append(-1)
        else:
            direction.append(direction[index - 1])
    return direction


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
    StrategyName.SUPERTREND: SuperTrendStrategy(),
    StrategyName.VWAP_REVERSION: VwapReversionStrategy(),
    StrategyName.STOCH_RSI_REVERSAL: StochRsiReversalStrategy(),
    StrategyName.EMA_RIBBON: EmaRibbonStrategy(),
    StrategyName.MOMENTUM_SCALPING: MomentumScalpingStrategy(),
}
