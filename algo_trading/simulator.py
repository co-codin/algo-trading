from __future__ import annotations

from dataclasses import replace

from algo_trading.models import (
    BacktestResult,
    Candle,
    EquityPoint,
    Position,
    PositionSide,
    SignalType,
    StrategyConfig,
    StrategyName,
    Trade,
)
from algo_trading.strategy import (
    StrategyContext,
    apply_strategy_preset,
    build_strategy_context,
    combo_member_strategy_names,
    entry_signal_for_index,
    exit_signal_for_position,
)


def run_backtest(candles: list[Candle], config: StrategyConfig) -> BacktestResult:
    if not candles:
        raise ValueError("at least one candle is required")
    config = apply_strategy_preset(config)
    _validate_config(config)
    required_candles = _required_candles(config)
    if len(candles) < required_candles:
        raise ValueError(
            f"not enough candles: need at least {required_candles} for indicator warmup"
        )

    context = build_strategy_context(candles, config)
    account = _Account(config)
    for index, candle in enumerate(candles):
        is_last_candle = index == len(candles) - 1
        account.on_candle(candle, context, index, is_last_candle)

    return account.result()


class _Account:
    def __init__(self, config: StrategyConfig) -> None:
        self.config = config
        self.cash = config.starting_balance
        self.position: Position | None = None
        self.trades: list[Trade] = []
        self.equity: list[EquityPoint] = []

    def on_candle(
        self,
        candle: Candle,
        context: StrategyContext,
        index: int,
        is_last_candle: bool,
    ) -> None:
        if self.position is not None:
            self._update_best_price(candle.close)
            exit_reason = self._risk_exit_reason(candle.close)
            strategy_exit = exit_signal_for_position(
                self.position.side,
                self.config,
                context,
                index,
            )
            if exit_reason is None and strategy_exit.type is not SignalType.HOLD:
                exit_reason = strategy_exit.reason
            if is_last_candle and exit_reason is None:
                exit_reason = "final_candle"
            if exit_reason is not None:
                self._close_position(candle, exit_reason)

        if self.position is None and not is_last_candle:
            signal = entry_signal_for_index(self.config, context, index)
            if signal.type is SignalType.ENTER_LONG:
                self._open_position(PositionSide.LONG, candle, signal.reason)
            elif signal.type is SignalType.ENTER_SHORT:
                self._open_position(PositionSide.SHORT, candle, signal.reason)

        self._record_equity(candle)

    def result(self) -> BacktestResult:
        return BacktestResult(
            trades=self.trades,
            equity=self.equity,
            summary=self._summary(),
        )

    def _open_position(self, side: PositionSide, candle: Candle, reason: str) -> None:
        fill_price = _entry_fill_price(side, candle.close, self.config.slippage_rate)
        notional = max(self.cash, 0.0) * self.config.position_fraction
        if notional <= 0.0:
            return
        quantity = notional / fill_price
        fee = fill_price * quantity * self.config.fee_rate
        slippage = abs(fill_price - candle.close) * quantity
        self.cash -= fee
        self.position = Position(
            side=side,
            quantity=quantity,
            entry_price=fill_price,
            entry_time=candle.open_time,
            entry_reason=reason,
            best_price=candle.close,
            entry_fee=fee,
            entry_slippage=slippage,
        )

    def _close_position(self, candle: Candle, reason: str) -> None:
        if self.position is None:
            return
        position = self.position
        fill_price = _exit_fill_price(position.side, candle.close, self.config.slippage_rate)
        gross_pnl = _gross_pnl(position.side, position.entry_price, fill_price, position.quantity)
        exit_fee = fill_price * position.quantity * self.config.fee_rate
        exit_slippage = abs(fill_price - candle.close) * position.quantity
        total_fees = position.entry_fee + exit_fee
        total_slippage = position.entry_slippage + exit_slippage
        realized_pnl = gross_pnl - total_fees
        self.cash += realized_pnl
        self.trades.append(
            Trade(
                side=position.side,
                entry_time=position.entry_time,
                exit_time=candle.open_time,
                entry_price=position.entry_price,
                exit_price=fill_price,
                quantity=position.quantity,
                realized_pnl=realized_pnl,
                fees=total_fees,
                slippage=total_slippage,
                entry_reason=position.entry_reason,
                exit_reason=reason,
            )
        )
        self.position = None

    def _update_best_price(self, price: float) -> None:
        if self.position is None:
            return
        if self.position.side is PositionSide.LONG:
            self.position.best_price = max(self.position.best_price, price)
        else:
            self.position.best_price = min(self.position.best_price, price)

    def _risk_exit_reason(self, price: float) -> str | None:
        if self.position is None:
            return None
        entry = self.position.entry_price
        side = self.position.side
        if side is PositionSide.LONG:
            if price <= entry * (1.0 - self.config.stop_loss_pct):
                return "stop_loss"
            if price >= entry * (1.0 + self.config.take_profit_pct):
                return "take_profit"
            if self.config.trailing_stop_pct > 0 and price <= self.position.best_price * (
                1.0 - self.config.trailing_stop_pct
            ):
                return "trailing_stop"
        else:
            if price >= entry * (1.0 + self.config.stop_loss_pct):
                return "stop_loss"
            if price <= entry * (1.0 - self.config.take_profit_pct):
                return "take_profit"
            if self.config.trailing_stop_pct > 0 and price >= self.position.best_price * (
                1.0 + self.config.trailing_stop_pct
            ):
                return "trailing_stop"
        return None

    def _record_equity(self, candle: Candle) -> None:
        position_side = ""
        position_quantity = 0.0
        unrealized = 0.0
        if self.position is not None:
            position_side = self.position.side.value
            position_quantity = self.position.quantity
            unrealized = _gross_pnl(
                self.position.side,
                self.position.entry_price,
                candle.close,
                self.position.quantity,
            )
        self.equity.append(
            EquityPoint(
                time=candle.open_time,
                equity=self.cash + unrealized,
                cash=self.cash,
                position_side=position_side,
                position_quantity=position_quantity,
            )
        )

    def _summary(self) -> dict[str, float | int | str]:
        final_balance = self.equity[-1].equity if self.equity else self.cash
        wins = [trade.realized_pnl for trade in self.trades if trade.realized_pnl > 0]
        losses = [trade.realized_pnl for trade in self.trades if trade.realized_pnl < 0]
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor: float | str
        if gross_loss:
            profit_factor = round(gross_win / gross_loss, 8)
        elif gross_win:
            profit_factor = "infinite"
        else:
            profit_factor = 0.0
        return {
            "symbol": self.config.symbol,
            "initial_balance": round(self.config.starting_balance, 8),
            "final_balance": round(final_balance, 8),
            "total_return_pct": round(
                ((final_balance / self.config.starting_balance) - 1.0) * 100.0,
                8,
            ),
            "max_drawdown_pct": round(_max_drawdown(self.equity), 8),
            "trades": len(self.trades),
            "win_rate": round((len(wins) / len(self.trades)) if self.trades else 0.0, 8),
            "average_win": round((gross_win / len(wins)) if wins else 0.0, 8),
            "average_loss": round((sum(losses) / len(losses)) if losses else 0.0, 8),
            "profit_factor": profit_factor,
            "fee_total": round(sum(trade.fees for trade in self.trades), 8),
            "slippage_estimate": round(sum(trade.slippage for trade in self.trades), 8),
            "sharpe_ratio": round(_sharpe_ratio(self.equity), 8),
            "sortino_ratio": round(_sortino_ratio(self.equity), 8),
            "max_drawdown_duration": _max_drawdown_duration(self.equity),
            "average_trade_duration": round(_average_trade_duration(self.trades), 8),
            "exposure_pct": round(_exposure_pct(self.equity), 8),
            "worst_trade": round(min((trade.realized_pnl for trade in self.trades), default=0.0), 8),
        }


def _entry_fill_price(side: PositionSide, price: float, slippage_rate: float) -> float:
    if side is PositionSide.LONG:
        return price * (1.0 + slippage_rate)
    return price * (1.0 - slippage_rate)


def _exit_fill_price(side: PositionSide, price: float, slippage_rate: float) -> float:
    if side is PositionSide.LONG:
        return price * (1.0 - slippage_rate)
    return price * (1.0 + slippage_rate)


def _gross_pnl(side: PositionSide, entry_price: float, exit_price: float, quantity: float) -> float:
    if side is PositionSide.LONG:
        return (exit_price - entry_price) * quantity
    return (entry_price - exit_price) * quantity


def _max_drawdown(equity: list[EquityPoint]) -> float:
    peak = 0.0
    max_drawdown = 0.0
    for point in equity:
        peak = max(peak, point.equity)
        if peak > 0.0:
            max_drawdown = max(max_drawdown, ((peak - point.equity) / peak) * 100.0)
    return max_drawdown


def _period_returns(equity: list[EquityPoint]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(equity, equity[1:]):
        if previous.equity > 0.0:
            returns.append((current.equity / previous.equity) - 1.0)
    return returns


def _sharpe_ratio(equity: list[EquityPoint]) -> float:
    returns = _period_returns(equity)
    if not returns:
        return 0.0
    average = sum(returns) / len(returns)
    stddev = _population_stddev(returns, average)
    return (average / stddev) if stddev else 0.0


def _sortino_ratio(equity: list[EquityPoint]) -> float:
    returns = _period_returns(equity)
    if not returns:
        return 0.0
    average = sum(returns) / len(returns)
    downside = [min(value, 0.0) for value in returns]
    downside_stddev = _population_stddev(downside, 0.0)
    return (average / downside_stddev) if downside_stddev else 0.0


def _population_stddev(values: list[float], mean: float) -> float:
    if not values:
        return 0.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return variance**0.5


def _max_drawdown_duration(equity: list[EquityPoint]) -> int:
    peak = 0.0
    current_duration = 0
    longest_duration = 0
    for point in equity:
        if point.equity >= peak:
            peak = point.equity
            current_duration = 0
        else:
            current_duration += 1
            longest_duration = max(longest_duration, current_duration)
    return longest_duration


def _average_trade_duration(trades: list[Trade]) -> float:
    if not trades:
        return 0.0
    return sum(trade.exit_time - trade.entry_time for trade in trades) / len(trades)


def _exposure_pct(equity: list[EquityPoint]) -> float:
    if not equity:
        return 0.0
    exposed = sum(1 for point in equity if point.position_side)
    return (exposed / len(equity)) * 100.0


def _validate_config(config: StrategyConfig) -> None:
    if config.starting_balance <= 0:
        raise ValueError("starting_balance must be positive")
    if not 0 < config.position_fraction <= 1:
        raise ValueError("position_fraction must be in the range (0, 1]")
    if config.fee_rate < 0 or config.slippage_rate < 0:
        raise ValueError("fees and slippage cannot be negative")
    if config.fast_ema <= 0 or config.slow_ema <= 0 or config.rsi_period <= 0:
        raise ValueError("indicator periods must be positive")
    if config.fast_ema >= config.slow_ema:
        raise ValueError("fast_ema must be less than slow_ema")
    if (
        config.macd_signal <= 0
        or config.bollinger_period <= 0
        or config.bollinger_stddev <= 0
        or config.donchian_period <= 0
        or config.atr_period <= 0
        or config.supertrend_multiplier <= 0
        or config.vwap_period <= 0
        or config.stoch_rsi_period <= 0
        or config.momentum_period <= 0
        or config.cci_period <= 0
        or config.williams_period <= 0
        or config.volume_period <= 0
    ):
        raise ValueError("strategy periods must be positive")
    if config.keltner_multiplier <= 0 or config.volume_multiplier <= 0:
        raise ValueError("strategy multipliers must be positive")
    if config.vwap_threshold_pct < 0:
        raise ValueError("strategy vwap_threshold_pct cannot be negative")
    if config.squeeze_threshold_pct < 0:
        raise ValueError("strategy squeeze_threshold_pct cannot be negative")
    if not 0 <= config.stoch_rsi_oversold < config.stoch_rsi_overbought <= 100:
        raise ValueError("strategy stochastic rsi thresholds must satisfy 0 <= oversold < overbought <= 100")
    if config.cci_oversold >= config.cci_overbought:
        raise ValueError("strategy cci thresholds must satisfy oversold < overbought")
    if not -100 <= config.williams_oversold < config.williams_overbought <= 0:
        raise ValueError("strategy williams thresholds must satisfy -100 <= oversold < overbought <= 0")
    if not 0 < config.ema_ribbon_fast < config.ema_ribbon_mid < config.ema_ribbon_slow:
        raise ValueError("strategy ema ribbon periods must satisfy fast < mid < slow")
    if not 0 <= config.rsi_midline <= 100:
        raise ValueError("strategy rsi_midline must be between 0 and 100")
    if (
        config.combo_entry_confirmations <= 0
        or config.combo_exit_confirmations <= 0
        or config.combo_lookback <= 0
    ):
        raise ValueError("strategy combo confirmations and lookback must be positive")
    try:
        combo_members = combo_member_strategy_names(config)
    except ValueError as exc:
        raise ValueError(str(exc).replace("combo", "strategy combo")) from exc
    if not combo_members:
        raise ValueError("strategy combo_strategies must include at least one standalone strategy")
    if config.combo_entry_confirmations > len(combo_members):
        raise ValueError("strategy combo_entry_confirmations cannot exceed combo member count")
    if config.combo_exit_confirmations > len(combo_members):
        raise ValueError("strategy combo_exit_confirmations cannot exceed combo member count")
    if config.combo_regime_lookback <= 0 or config.combo_rs_lookback <= 0:
        raise ValueError("strategy combo lookbacks must be positive")
    if not 0 <= config.combo_regime_low_pct < config.combo_regime_high_pct <= 100:
        raise ValueError("strategy combo regime percentiles must satisfy 0 <= low < high <= 100")
    if str(config.combo_mtf_mode).strip().lower() not in {"off", "soft", "hard"}:
        raise ValueError("strategy combo_mtf_mode must be off, soft, or hard")
    if str(config.combo_regime_metric).strip().lower() not in {"atr_pct", "bb_width"}:
        raise ValueError("strategy combo_regime_metric must be atr_pct or bb_width")
    for name, value in [
        ("combo_regime_damp_weight", config.combo_regime_damp_weight),
        ("combo_mtf_disagree_weight", config.combo_mtf_disagree_weight),
        ("combo_session_us_cash_weight", config.combo_session_us_cash_weight),
        ("combo_session_europe_weight", config.combo_session_europe_weight),
        ("combo_session_asia_weight", config.combo_session_asia_weight),
        ("combo_session_overnight_weight", config.combo_session_overnight_weight),
        ("combo_rs_disagree_weight", config.combo_rs_disagree_weight),
        ("combo_vote_weight_threshold", config.combo_vote_weight_threshold),
    ]:
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    for name, value in [
        ("stop_loss_pct", config.stop_loss_pct),
        ("take_profit_pct", config.take_profit_pct),
        ("trailing_stop_pct", config.trailing_stop_pct),
    ]:
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    if not 0 <= config.rsi_oversold < config.rsi_overbought <= 100:
        raise ValueError("rsi thresholds must satisfy 0 <= oversold < overbought <= 100")


def _required_candles(config: StrategyConfig) -> int:
    strategy = (
        config.strategy
        if isinstance(config.strategy, StrategyName)
        else StrategyName(str(config.strategy))
    )
    if strategy is StrategyName.MACD:
        return max(config.slow_ema, config.macd_signal + 1)
    if strategy is StrategyName.BOLLINGER_REVERSION:
        return config.bollinger_period + 1
    if strategy is StrategyName.DONCHIAN_BREAKOUT:
        return config.donchian_period + 1
    if strategy is StrategyName.RSI_REVERSAL:
        return config.rsi_period + 2
    if strategy is StrategyName.SUPERTREND:
        return config.atr_period + 2
    if strategy is StrategyName.VWAP_REVERSION:
        return config.vwap_period + 2
    if strategy is StrategyName.STOCH_RSI_REVERSAL:
        return config.rsi_period + config.stoch_rsi_period + 2
    if strategy is StrategyName.EMA_RIBBON:
        return config.ema_ribbon_slow + 2
    if strategy is StrategyName.MOMENTUM_SCALPING:
        return max(config.slow_ema, config.macd_signal + 1, config.rsi_period + 1, config.momentum_period + 2)
    if strategy is StrategyName.KELTNER_BREAKOUT:
        return config.atr_period + 1
    if strategy is StrategyName.EMA_PULLBACK:
        return config.slow_ema + 1
    if strategy is StrategyName.ATR_TRAILING_TREND:
        return config.atr_period + 2
    if strategy is StrategyName.CCI_REVERSAL:
        return config.cci_period + 2
    if strategy is StrategyName.WILLIAMS_R_REVERSAL:
        return config.williams_period + 2
    if strategy is StrategyName.BOLLINGER_SQUEEZE_RELEASE:
        return config.bollinger_period + 2
    if strategy is StrategyName.OBV_TREND:
        return max(config.slow_ema, config.volume_period) + 1
    if strategy is StrategyName.VOLUME_BREAKOUT:
        return max(config.donchian_period, config.volume_period) + 1
    if strategy is StrategyName.VWAP_TREND_CONTINUATION:
        return max(config.slow_ema, config.vwap_period) + 1
    if strategy is StrategyName.SMA_CROSSOVER:
        return config.slow_ema + 1
    if strategy is StrategyName.ADX_TREND:
        return (config.atr_period * 2) + 1
    if strategy is StrategyName.ICHIMOKU_BREAKOUT:
        return 53
    if strategy is StrategyName.MFI_REVERSAL:
        return config.rsi_period + 2
    if strategy is StrategyName.PARABOLIC_SAR:
        return 3
    if strategy is StrategyName.ZSCORE_REVERSION:
        return config.bollinger_period + 2
    if strategy is StrategyName.TIME_SERIES_MOMENTUM:
        return 3
    if strategy is StrategyName.VOLATILITY_BREAKOUT:
        return max(config.donchian_period, config.atr_period) + 2
    if strategy is StrategyName.RSI_MEAN_REVERSION:
        return config.rsi_period + 1
    if strategy is StrategyName.BREADTH_CONFIRMATION:
        return 1
    if strategy is StrategyName.COMBINED_SIGNALS:
        return max(
            _required_candles(replace(config, strategy=member))
            for member in combo_member_strategy_names(config)
        )
    return max(config.slow_ema, config.rsi_period + 1)
