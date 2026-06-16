from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from algo_trading.indicators import (
    atr,
    bollinger_width,
    commodity_channel_index,
    directional_movement_index,
    ema,
    ichimoku_cloud,
    keltner_channels,
    money_flow_index,
    momentum,
    on_balance_volume,
    parabolic_sar,
    previous_rolling_high,
    previous_rolling_low,
    rolling_mean,
    rolling_stddev,
    rolling_volume_mean,
    rolling_vwap,
    rolling_zscore,
    rsi,
    stochastic_rsi,
    williams_r,
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
    fast_sma: list[float]
    slow_sma: list[float]
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
    keltner_mid: list[float]
    keltner_upper: list[float]
    keltner_lower: list[float]
    cci_values: list[float]
    williams_r_values: list[float]
    bollinger_width_values: list[float]
    obv_values: list[float]
    obv_signal_values: list[float]
    volume_mean: list[float]
    plus_di_values: list[float]
    minus_di_values: list[float]
    adx_values: list[float]
    ichimoku_conversion: list[float]
    ichimoku_base: list[float]
    ichimoku_span_a: list[float]
    ichimoku_span_b: list[float]
    mfi_values: list[float]
    parabolic_sar_values: list[float]
    parabolic_sar_trend: list[int]
    zscore_values: list[float]


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


def combo_member_strategy_names(config: StrategyConfig) -> list[StrategyName]:
    value = config.combo_strategies.strip().lower()
    raw_names = list_strategy_names() if value == "all" else _parse_combo_strategy_names(value)
    members: list[StrategyName] = []
    seen: set[StrategyName] = set()
    for raw_name in raw_names:
        try:
            strategy_name = StrategyName(raw_name)
        except ValueError as exc:
            raise ValueError(f"unsupported combo strategy: {raw_name}") from exc
        if strategy_name is StrategyName.COMBINED_SIGNALS or strategy_name in seen:
            continue
        members.append(strategy_name)
        seen.add(strategy_name)
    return members


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
            keltner_multiplier=2.4,
            cci_period=30,
            cci_oversold=-120.0,
            cci_overbought=120.0,
            williams_period=21,
            williams_oversold=-85.0,
            williams_overbought=-15.0,
            volume_period=30,
            volume_multiplier=1.8,
            squeeze_threshold_pct=0.04,
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
            keltner_multiplier=2.0,
            cci_period=20,
            cci_oversold=-100.0,
            cci_overbought=100.0,
            williams_period=14,
            williams_oversold=-80.0,
            williams_overbought=-20.0,
            volume_period=20,
            volume_multiplier=1.5,
            squeeze_threshold_pct=0.05,
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
            keltner_multiplier=1.4,
            cci_period=10,
            cci_oversold=-90.0,
            cci_overbought=90.0,
            williams_period=7,
            williams_oversold=-75.0,
            williams_overbought=-25.0,
            volume_period=10,
            volume_multiplier=1.25,
            squeeze_threshold_pct=0.08,
        )
    raise ValueError(f"unsupported preset: {config.preset}")


def build_strategy_context(candles: list[Candle], config: StrategyConfig) -> StrategyContext:
    closes = [candle.close for candle in candles]
    highs = [candle.high for candle in candles]
    lows = [candle.low for candle in candles]
    fast = ema(closes, config.fast_ema)
    slow = ema(closes, config.slow_ema)
    fast_sma = rolling_mean(closes, config.fast_ema)
    slow_sma = rolling_mean(closes, config.slow_ema)
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
    keltner_mid, keltner_upper, keltner_lower = keltner_channels(
        candles,
        config.atr_period,
        config.keltner_multiplier,
    )
    obv_values = on_balance_volume(candles)
    plus_di_values, minus_di_values, adx_values = directional_movement_index(
        candles,
        config.atr_period,
    )
    ichimoku_conversion, ichimoku_base, ichimoku_span_a, ichimoku_span_b = ichimoku_cloud(candles)
    parabolic_sar_values, parabolic_sar_trend = parabolic_sar(candles)
    return StrategyContext(
        candles=candles,
        closes=closes,
        highs=highs,
        lows=lows,
        fast=fast,
        slow=slow,
        fast_sma=fast_sma,
        slow_sma=slow_sma,
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
        keltner_mid=keltner_mid,
        keltner_upper=keltner_upper,
        keltner_lower=keltner_lower,
        cci_values=commodity_channel_index(candles, config.cci_period),
        williams_r_values=williams_r(candles, config.williams_period),
        bollinger_width_values=bollinger_width(
            bollinger_upper,
            bollinger_lower,
            bollinger_mid,
        ),
        obv_values=obv_values,
        obv_signal_values=rolling_mean(obv_values, config.volume_period),
        volume_mean=rolling_volume_mean(candles, config.volume_period),
        plus_di_values=plus_di_values,
        minus_di_values=minus_di_values,
        adx_values=adx_values,
        ichimoku_conversion=ichimoku_conversion,
        ichimoku_base=ichimoku_base,
        ichimoku_span_a=ichimoku_span_a,
        ichimoku_span_b=ichimoku_span_b,
        mfi_values=money_flow_index(candles, config.rsi_period),
        parabolic_sar_values=parabolic_sar_values,
        parabolic_sar_trend=parabolic_sar_trend,
        zscore_values=rolling_zscore(closes, config.bollinger_period),
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


class KeltnerBreakoutStrategy:
    name = StrategyName.KELTNER_BREAKOUT
    description = "Keltner channel breakout using ATR width"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index < config.atr_period or index >= len(context.keltner_upper):
            return Signal(SignalType.HOLD, "insufficient_data")
        previous_close = context.closes[index - 1]
        current_close = context.closes[index]
        if (
            previous_close <= context.keltner_upper[index - 1]
            and current_close > context.keltner_upper[index]
            and _side_allowed(config, PositionSide.LONG)
        ):
            return Signal(SignalType.ENTER_LONG, "keltner_breakout_long")
        if (
            previous_close >= context.keltner_lower[index - 1]
            and current_close < context.keltner_lower[index]
            and _side_allowed(config, PositionSide.SHORT)
        ):
            return Signal(SignalType.ENTER_SHORT, "keltner_breakout_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index >= len(context.keltner_mid):
            return Signal(SignalType.HOLD, "insufficient_data")
        current_close = context.closes[index]
        if side is PositionSide.LONG and current_close <= context.keltner_mid[index]:
            return Signal(SignalType.EXIT_LONG, "keltner_midline_cross")
        if side is PositionSide.SHORT and current_close >= context.keltner_mid[index]:
            return Signal(SignalType.EXIT_SHORT, "keltner_midline_cross")
        return Signal(SignalType.HOLD, "no_signal")


class EmaPullbackStrategy:
    name = StrategyName.EMA_PULLBACK
    description = "Trend continuation when price reclaims the fast EMA"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index < config.slow_ema or index >= len(context.fast):
            return Signal(SignalType.HOLD, "insufficient_data")
        bullish_trend = context.fast[index] > context.slow[index]
        bearish_trend = context.fast[index] < context.slow[index]
        if (
            bullish_trend
            and context.closes[index - 1] < context.fast[index - 1]
            and context.closes[index] >= context.fast[index]
            and _side_allowed(config, PositionSide.LONG)
        ):
            return Signal(SignalType.ENTER_LONG, "ema_pullback_long")
        if (
            bearish_trend
            and context.closes[index - 1] > context.fast[index - 1]
            and context.closes[index] <= context.fast[index]
            and _side_allowed(config, PositionSide.SHORT)
        ):
            return Signal(SignalType.ENTER_SHORT, "ema_pullback_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index >= min(len(context.fast), len(context.slow)):
            return Signal(SignalType.HOLD, "insufficient_data")
        if side is PositionSide.LONG and context.fast[index] <= context.slow[index]:
            return Signal(SignalType.EXIT_LONG, "ema_pullback_trend_lost")
        if side is PositionSide.SHORT and context.fast[index] >= context.slow[index]:
            return Signal(SignalType.EXIT_SHORT, "ema_pullback_trend_lost")
        return Signal(SignalType.HOLD, "no_signal")


class AtrTrailingTrendStrategy:
    name = StrategyName.ATR_TRAILING_TREND
    description = "ATR trailing trend following on direction flips"

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
            return Signal(SignalType.ENTER_LONG, "atr_trailing_trend_long")
        if previous >= 0 > current and _side_allowed(config, PositionSide.SHORT):
            return Signal(SignalType.ENTER_SHORT, "atr_trailing_trend_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index >= len(context.supertrend_direction):
            return Signal(SignalType.HOLD, "insufficient_data")
        current = context.supertrend_direction[index]
        if side is PositionSide.LONG and current < 0:
            return Signal(SignalType.EXIT_LONG, "atr_trailing_trend_short")
        if side is PositionSide.SHORT and current > 0:
            return Signal(SignalType.EXIT_SHORT, "atr_trailing_trend_long")
        return Signal(SignalType.HOLD, "no_signal")


class CciReversalStrategy:
    name = StrategyName.CCI_REVERSAL
    description = "CCI reversal after leaving extreme levels"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index < config.cci_period or index >= len(context.cci_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        previous = context.cci_values[index - 1]
        current = context.cci_values[index]
        if previous <= config.cci_oversold < current and _side_allowed(config, PositionSide.LONG):
            return Signal(SignalType.ENTER_LONG, "cci_reversal_long")
        if previous >= config.cci_overbought > current and _side_allowed(config, PositionSide.SHORT):
            return Signal(SignalType.ENTER_SHORT, "cci_reversal_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index >= len(context.cci_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        current = context.cci_values[index]
        if side is PositionSide.LONG and current >= 0.0:
            return Signal(SignalType.EXIT_LONG, "cci_zero_line")
        if side is PositionSide.SHORT and current <= 0.0:
            return Signal(SignalType.EXIT_SHORT, "cci_zero_line")
        return Signal(SignalType.HOLD, "no_signal")


class WilliamsRReversalStrategy:
    name = StrategyName.WILLIAMS_R_REVERSAL
    description = "Williams %R reversal after leaving extreme levels"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index < config.williams_period or index >= len(context.williams_r_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        previous = context.williams_r_values[index - 1]
        current = context.williams_r_values[index]
        if previous <= config.williams_oversold < current and _side_allowed(
            config,
            PositionSide.LONG,
        ):
            return Signal(SignalType.ENTER_LONG, "williams_r_reversal_long")
        if previous >= config.williams_overbought > current and _side_allowed(
            config,
            PositionSide.SHORT,
        ):
            return Signal(SignalType.ENTER_SHORT, "williams_r_reversal_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index >= len(context.williams_r_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        current = context.williams_r_values[index]
        if side is PositionSide.LONG and current >= -50.0:
            return Signal(SignalType.EXIT_LONG, "williams_r_midline")
        if side is PositionSide.SHORT and current <= -50.0:
            return Signal(SignalType.EXIT_SHORT, "williams_r_midline")
        return Signal(SignalType.HOLD, "no_signal")


class BollingerSqueezeReleaseStrategy:
    name = StrategyName.BOLLINGER_SQUEEZE_RELEASE
    description = "Bollinger squeeze expansion breakout"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index < config.bollinger_period or index >= len(context.bollinger_width_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        previous_width = context.bollinger_width_values[index - 1]
        current_width = context.bollinger_width_values[index]
        current_close = context.closes[index]
        squeeze_released = previous_width <= config.squeeze_threshold_pct and current_width > previous_width
        if (
            squeeze_released
            and current_close > context.bollinger_upper[index]
            and _side_allowed(config, PositionSide.LONG)
        ):
            return Signal(SignalType.ENTER_LONG, "bollinger_squeeze_release_long")
        if (
            squeeze_released
            and current_close < context.bollinger_lower[index]
            and _side_allowed(config, PositionSide.SHORT)
        ):
            return Signal(SignalType.ENTER_SHORT, "bollinger_squeeze_release_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index >= len(context.bollinger_mid):
            return Signal(SignalType.HOLD, "insufficient_data")
        current_close = context.closes[index]
        if side is PositionSide.LONG and current_close <= context.bollinger_mid[index]:
            return Signal(SignalType.EXIT_LONG, "bollinger_squeeze_midline")
        if side is PositionSide.SHORT and current_close >= context.bollinger_mid[index]:
            return Signal(SignalType.EXIT_SHORT, "bollinger_squeeze_midline")
        return Signal(SignalType.HOLD, "no_signal")


class ObvTrendStrategy:
    name = StrategyName.OBV_TREND
    description = "OBV trend confirmation with price trend"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index < config.volume_period or index >= len(context.obv_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        if (
            _crossed_above(context.obv_values, context.obv_signal_values, index)
            and context.closes[index] > context.slow[index]
            and _side_allowed(config, PositionSide.LONG)
        ):
            return Signal(SignalType.ENTER_LONG, "obv_trend_long")
        if (
            _crossed_below(context.obv_values, context.obv_signal_values, index)
            and context.closes[index] < context.slow[index]
            and _side_allowed(config, PositionSide.SHORT)
        ):
            return Signal(SignalType.ENTER_SHORT, "obv_trend_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index >= len(context.obv_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        if side is PositionSide.LONG and context.obv_values[index] < context.obv_signal_values[index]:
            return Signal(SignalType.EXIT_LONG, "obv_trend_lost")
        if side is PositionSide.SHORT and context.obv_values[index] > context.obv_signal_values[index]:
            return Signal(SignalType.EXIT_SHORT, "obv_trend_lost")
        return Signal(SignalType.HOLD, "no_signal")


class VolumeBreakoutStrategy:
    name = StrategyName.VOLUME_BREAKOUT
    description = "Donchian breakout confirmed by above-average volume"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index < max(config.donchian_period, config.volume_period) or index >= len(context.closes):
            return Signal(SignalType.HOLD, "insufficient_data")
        current_close = context.closes[index]
        current_volume = context.candles[index].volume
        volume_confirmed = current_volume > context.volume_mean[index] * config.volume_multiplier
        if (
            volume_confirmed
            and current_close > context.donchian_high[index]
            and _side_allowed(config, PositionSide.LONG)
        ):
            return Signal(SignalType.ENTER_LONG, "volume_breakout_long")
        if (
            volume_confirmed
            and current_close < context.donchian_low[index]
            and _side_allowed(config, PositionSide.SHORT)
        ):
            return Signal(SignalType.ENTER_SHORT, "volume_breakout_short")
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
            return Signal(SignalType.EXIT_LONG, "volume_breakout_low")
        if side is PositionSide.SHORT and current_close > context.donchian_high[index]:
            return Signal(SignalType.EXIT_SHORT, "volume_breakout_high")
        return Signal(SignalType.HOLD, "no_signal")


class VwapTrendContinuationStrategy:
    name = StrategyName.VWAP_TREND_CONTINUATION
    description = "VWAP trend continuation with EMA confirmation"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index < max(config.slow_ema, config.vwap_period) or index >= len(context.vwap):
            return Signal(SignalType.HOLD, "insufficient_data")
        bullish_trend = context.fast[index] > context.slow[index]
        bearish_trend = context.fast[index] < context.slow[index]
        if (
            bullish_trend
            and context.closes[index - 1] <= context.vwap[index - 1]
            and context.closes[index] > context.vwap[index]
            and _side_allowed(config, PositionSide.LONG)
        ):
            return Signal(SignalType.ENTER_LONG, "vwap_trend_continuation_long")
        if (
            bearish_trend
            and context.closes[index - 1] >= context.vwap[index - 1]
            and context.closes[index] < context.vwap[index]
            and _side_allowed(config, PositionSide.SHORT)
        ):
            return Signal(SignalType.ENTER_SHORT, "vwap_trend_continuation_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index >= len(context.vwap):
            return Signal(SignalType.HOLD, "insufficient_data")
        current_close = context.closes[index]
        if side is PositionSide.LONG and current_close < context.vwap[index]:
            return Signal(SignalType.EXIT_LONG, "vwap_trend_lost")
        if side is PositionSide.SHORT and current_close > context.vwap[index]:
            return Signal(SignalType.EXIT_SHORT, "vwap_trend_lost")
        return Signal(SignalType.HOLD, "no_signal")


class SmaCrossoverStrategy:
    name = StrategyName.SMA_CROSSOVER
    description = "Simple moving average crossover baseline"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index < config.slow_ema or index >= min(len(context.fast_sma), len(context.slow_sma)):
            return Signal(SignalType.HOLD, "insufficient_data")
        if _crossed_above(context.fast_sma, context.slow_sma, index) and _side_allowed(
            config,
            PositionSide.LONG,
        ):
            return Signal(SignalType.ENTER_LONG, "sma_cross_above")
        if _crossed_below(context.fast_sma, context.slow_sma, index) and _side_allowed(
            config,
            PositionSide.SHORT,
        ):
            return Signal(SignalType.ENTER_SHORT, "sma_cross_below")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index >= min(len(context.fast_sma), len(context.slow_sma)):
            return Signal(SignalType.HOLD, "insufficient_data")
        if side is PositionSide.LONG and _crossed_below(context.fast_sma, context.slow_sma, index):
            return Signal(SignalType.EXIT_LONG, "sma_cross_below")
        if side is PositionSide.SHORT and _crossed_above(context.fast_sma, context.slow_sma, index):
            return Signal(SignalType.EXIT_SHORT, "sma_cross_above")
        return Signal(SignalType.HOLD, "no_signal")


class AdxTrendStrategy:
    name = StrategyName.ADX_TREND
    description = "ADX trend strength with directional movement confirmation"
    trend_threshold = 20.0

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index < config.atr_period or index >= len(context.adx_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        trend_confirmed = context.adx_values[index] >= self.trend_threshold
        if (
            trend_confirmed
            and _crossed_above(context.plus_di_values, context.minus_di_values, index)
            and _side_allowed(config, PositionSide.LONG)
        ):
            return Signal(SignalType.ENTER_LONG, "adx_trend_long")
        if (
            trend_confirmed
            and _crossed_below(context.plus_di_values, context.minus_di_values, index)
            and _side_allowed(config, PositionSide.SHORT)
        ):
            return Signal(SignalType.ENTER_SHORT, "adx_trend_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index >= len(context.adx_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        if side is PositionSide.LONG and context.plus_di_values[index] < context.minus_di_values[index]:
            return Signal(SignalType.EXIT_LONG, "adx_direction_lost")
        if side is PositionSide.SHORT and context.minus_di_values[index] < context.plus_di_values[index]:
            return Signal(SignalType.EXIT_SHORT, "adx_direction_lost")
        return Signal(SignalType.HOLD, "no_signal")


class IchimokuBreakoutStrategy:
    name = StrategyName.ICHIMOKU_BREAKOUT
    description = "Ichimoku cloud breakout with conversion/base confirmation"
    span_b_period = 52

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index < self.span_b_period or index >= len(context.closes):
            return Signal(SignalType.HOLD, "insufficient_data")
        previous_close = context.closes[index - 1]
        current_close = context.closes[index]
        previous_cloud_top = _ichimoku_cloud_top(context, index - 1)
        previous_cloud_bottom = _ichimoku_cloud_bottom(context, index - 1)
        current_cloud_top = _ichimoku_cloud_top(context, index)
        current_cloud_bottom = _ichimoku_cloud_bottom(context, index)
        bullish_confirmation = context.ichimoku_conversion[index] >= context.ichimoku_base[index]
        bearish_confirmation = context.ichimoku_conversion[index] <= context.ichimoku_base[index]
        if (
            previous_close <= previous_cloud_top
            and current_close > current_cloud_top
            and bullish_confirmation
            and _side_allowed(config, PositionSide.LONG)
        ):
            return Signal(SignalType.ENTER_LONG, "ichimoku_breakout_long")
        if (
            previous_close >= previous_cloud_bottom
            and current_close < current_cloud_bottom
            and bearish_confirmation
            and _side_allowed(config, PositionSide.SHORT)
        ):
            return Signal(SignalType.ENTER_SHORT, "ichimoku_breakout_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index >= len(context.closes):
            return Signal(SignalType.HOLD, "insufficient_data")
        current_close = context.closes[index]
        if side is PositionSide.LONG and current_close < _ichimoku_cloud_bottom(context, index):
            return Signal(SignalType.EXIT_LONG, "ichimoku_cloud_lost")
        if side is PositionSide.SHORT and current_close > _ichimoku_cloud_top(context, index):
            return Signal(SignalType.EXIT_SHORT, "ichimoku_cloud_lost")
        return Signal(SignalType.HOLD, "no_signal")


class MfiReversalStrategy:
    name = StrategyName.MFI_REVERSAL
    description = "Money Flow Index reversal after leaving extreme levels"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index < config.rsi_period or index >= len(context.mfi_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        previous = context.mfi_values[index - 1]
        current = context.mfi_values[index]
        if previous <= config.rsi_oversold < current and _side_allowed(config, PositionSide.LONG):
            return Signal(SignalType.ENTER_LONG, "mfi_reversal_long")
        if previous >= config.rsi_overbought > current and _side_allowed(config, PositionSide.SHORT):
            return Signal(SignalType.ENTER_SHORT, "mfi_reversal_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index >= len(context.mfi_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        current = context.mfi_values[index]
        if side is PositionSide.LONG and current >= config.rsi_midline:
            return Signal(SignalType.EXIT_LONG, "mfi_midline")
        if side is PositionSide.SHORT and current <= config.rsi_midline:
            return Signal(SignalType.EXIT_SHORT, "mfi_midline")
        return Signal(SignalType.HOLD, "no_signal")


class ParabolicSarStrategy:
    name = StrategyName.PARABOLIC_SAR
    description = "Parabolic SAR trend flip"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index >= len(context.parabolic_sar_trend):
            return Signal(SignalType.HOLD, "insufficient_data")
        previous = context.parabolic_sar_trend[index - 1]
        current = context.parabolic_sar_trend[index]
        if previous <= 0 < current and _side_allowed(config, PositionSide.LONG):
            return Signal(SignalType.ENTER_LONG, "parabolic_sar_flip_long")
        if previous >= 0 > current and _side_allowed(config, PositionSide.SHORT):
            return Signal(SignalType.ENTER_SHORT, "parabolic_sar_flip_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index >= len(context.parabolic_sar_trend):
            return Signal(SignalType.HOLD, "insufficient_data")
        current = context.parabolic_sar_trend[index]
        if side is PositionSide.LONG and current < 0:
            return Signal(SignalType.EXIT_LONG, "parabolic_sar_flip_short")
        if side is PositionSide.SHORT and current > 0:
            return Signal(SignalType.EXIT_SHORT, "parabolic_sar_flip_long")
        return Signal(SignalType.HOLD, "no_signal")


class ZscoreReversionStrategy:
    name = StrategyName.ZSCORE_REVERSION
    description = "Rolling z-score mean reversion from statistical extremes"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index <= 0 or index < config.bollinger_period or index >= len(context.zscore_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        previous = context.zscore_values[index - 1]
        current = context.zscore_values[index]
        threshold = config.bollinger_stddev
        if previous <= -threshold < current and _side_allowed(config, PositionSide.LONG):
            return Signal(SignalType.ENTER_LONG, "zscore_reversion_long")
        if previous >= threshold > current and _side_allowed(config, PositionSide.SHORT):
            return Signal(SignalType.ENTER_SHORT, "zscore_reversion_short")
        return Signal(SignalType.HOLD, "no_signal")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        if index >= len(context.zscore_values):
            return Signal(SignalType.HOLD, "insufficient_data")
        current = context.zscore_values[index]
        if side is PositionSide.LONG and current >= 0.0:
            return Signal(SignalType.EXIT_LONG, "zscore_mean_reversion")
        if side is PositionSide.SHORT and current <= 0.0:
            return Signal(SignalType.EXIT_SHORT, "zscore_mean_reversion")
        return Signal(SignalType.HOLD, "no_signal")


class CombinedSignalsStrategy:
    name = StrategyName.COMBINED_SIGNALS
    description = "Configurable strategy confirmation ensemble"

    def entry_signal(
        self,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        members = combo_member_strategy_names(config)
        long_names, short_names = _combo_entry_vote_names(config, context, index, members)
        required = config.combo_entry_confirmations
        if (
            len(long_names) >= required
            and len(long_names) > len(short_names)
            and _side_allowed(config, PositionSide.LONG)
        ):
            return Signal(
                SignalType.ENTER_LONG,
                _combo_reason("combined_long", long_names, members),
            )
        if (
            len(short_names) >= required
            and len(short_names) > len(long_names)
            and _side_allowed(config, PositionSide.SHORT)
        ):
            return Signal(
                SignalType.ENTER_SHORT,
                _combo_reason("combined_short", short_names, members),
            )
        if len(long_names) >= required and len(short_names) >= required:
            return Signal(SignalType.HOLD, "conflicting_combo_confirmations")
        return Signal(SignalType.HOLD, "insufficient_combo_confirmations")

    def exit_signal(
        self,
        side: PositionSide,
        config: StrategyConfig,
        context: StrategyContext,
        index: int,
    ) -> Signal:
        members = combo_member_strategy_names(config)
        exit_names, opposite_names = _combo_exit_vote_names(config, context, index, side, members)
        required = config.combo_exit_confirmations
        if len(exit_names) >= required:
            if side is PositionSide.LONG:
                return Signal(
                    SignalType.EXIT_LONG,
                    _combo_reason("combined_exit_long", exit_names, members),
                )
            return Signal(
                SignalType.EXIT_SHORT,
                _combo_reason("combined_exit_short", exit_names, members),
            )
        if len(opposite_names) >= required:
            if side is PositionSide.LONG:
                return Signal(
                    SignalType.EXIT_LONG,
                    _combo_reason("combined_opposite_short", opposite_names, members),
                )
            return Signal(
                SignalType.EXIT_SHORT,
                _combo_reason("combined_opposite_long", opposite_names, members),
            )
        return Signal(SignalType.HOLD, "insufficient_combo_exit_confirmations")


def _side_allowed(config: StrategyConfig, side: PositionSide) -> bool:
    if side is PositionSide.LONG:
        return config.allowed_side in {AllowedSide.BOTH, AllowedSide.LONG_ONLY}
    return config.allowed_side in {AllowedSide.BOTH, AllowedSide.SHORT_ONLY}


def _crossed_above(first: list[float], second: list[float], index: int) -> bool:
    return first[index - 1] <= second[index - 1] and first[index] > second[index]


def _crossed_below(first: list[float], second: list[float], index: int) -> bool:
    return first[index - 1] >= second[index - 1] and first[index] < second[index]


def _parse_combo_strategy_names(value: str) -> list[str]:
    return [name.strip().lower() for name in value.split(",") if name.strip()]


def _combo_entry_vote_names(
    config: StrategyConfig,
    context: StrategyContext,
    index: int,
    members: list[StrategyName],
) -> tuple[list[str], list[str]]:
    long_names: list[str] = []
    short_names: list[str] = []
    for member in members:
        signal = _latest_entry_signal(replace(config, strategy=member), context, index)
        if signal.type is SignalType.ENTER_LONG:
            long_names.append(member.value)
        elif signal.type is SignalType.ENTER_SHORT:
            short_names.append(member.value)
    return long_names, short_names


def _combo_exit_vote_names(
    config: StrategyConfig,
    context: StrategyContext,
    index: int,
    side: PositionSide,
    members: list[StrategyName],
) -> tuple[list[str], list[str]]:
    exit_names: list[str] = []
    opposite_names: list[str] = []
    for member in members:
        member_config = replace(config, strategy=member)
        exit_signal = _latest_exit_signal(member_config, context, index, side)
        if side is PositionSide.LONG and exit_signal.type is SignalType.EXIT_LONG:
            exit_names.append(member.value)
        elif side is PositionSide.SHORT and exit_signal.type is SignalType.EXIT_SHORT:
            exit_names.append(member.value)

        opposite_config = replace(member_config, allowed_side=AllowedSide.BOTH)
        entry_signal = _latest_entry_signal(opposite_config, context, index)
        if side is PositionSide.LONG and entry_signal.type is SignalType.ENTER_SHORT:
            opposite_names.append(member.value)
        elif side is PositionSide.SHORT and entry_signal.type is SignalType.ENTER_LONG:
            opposite_names.append(member.value)
    return exit_names, opposite_names


def _latest_entry_signal(
    config: StrategyConfig,
    context: StrategyContext,
    index: int,
) -> Signal:
    strategy = get_strategy(config.strategy)
    latest = Signal(SignalType.HOLD, "no_signal")
    for signal_index in _combo_lookback_indexes(config, index):
        signal = strategy.entry_signal(config, context, signal_index)
        if signal.type in {SignalType.ENTER_LONG, SignalType.ENTER_SHORT}:
            latest = signal
    return latest


def _latest_exit_signal(
    config: StrategyConfig,
    context: StrategyContext,
    index: int,
    side: PositionSide,
) -> Signal:
    strategy = get_strategy(config.strategy)
    expected_type = SignalType.EXIT_LONG if side is PositionSide.LONG else SignalType.EXIT_SHORT
    latest = Signal(SignalType.HOLD, "no_signal")
    for signal_index in _combo_lookback_indexes(config, index):
        signal = strategy.exit_signal(side, config, context, signal_index)
        if signal.type is expected_type:
            latest = signal
    return latest


def _combo_lookback_indexes(config: StrategyConfig, index: int) -> range:
    start = max(0, index - config.combo_lookback + 1)
    return range(start, index + 1)


def _combo_reason(prefix: str, names: list[str], members: list[StrategyName]) -> str:
    return f"{prefix}:{len(names)}/{len(members)}:{','.join(names)}"


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


def _ichimoku_cloud_top(context: StrategyContext, index: int) -> float:
    return max(context.ichimoku_span_a[index], context.ichimoku_span_b[index])


def _ichimoku_cloud_bottom(context: StrategyContext, index: int) -> float:
    return min(context.ichimoku_span_a[index], context.ichimoku_span_b[index])


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
    StrategyName.KELTNER_BREAKOUT: KeltnerBreakoutStrategy(),
    StrategyName.EMA_PULLBACK: EmaPullbackStrategy(),
    StrategyName.ATR_TRAILING_TREND: AtrTrailingTrendStrategy(),
    StrategyName.CCI_REVERSAL: CciReversalStrategy(),
    StrategyName.WILLIAMS_R_REVERSAL: WilliamsRReversalStrategy(),
    StrategyName.BOLLINGER_SQUEEZE_RELEASE: BollingerSqueezeReleaseStrategy(),
    StrategyName.OBV_TREND: ObvTrendStrategy(),
    StrategyName.VOLUME_BREAKOUT: VolumeBreakoutStrategy(),
    StrategyName.VWAP_TREND_CONTINUATION: VwapTrendContinuationStrategy(),
    StrategyName.SMA_CROSSOVER: SmaCrossoverStrategy(),
    StrategyName.ADX_TREND: AdxTrendStrategy(),
    StrategyName.ICHIMOKU_BREAKOUT: IchimokuBreakoutStrategy(),
    StrategyName.MFI_REVERSAL: MfiReversalStrategy(),
    StrategyName.PARABOLIC_SAR: ParabolicSarStrategy(),
    StrategyName.ZSCORE_REVERSION: ZscoreReversionStrategy(),
    StrategyName.COMBINED_SIGNALS: CombinedSignalsStrategy(),
}
