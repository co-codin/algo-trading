from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class SignalType(str, Enum):
    HOLD = "hold"
    ENTER_LONG = "enter_long"
    ENTER_SHORT = "enter_short"
    EXIT_LONG = "exit_long"
    EXIT_SHORT = "exit_short"


class AllowedSide(str, Enum):
    BOTH = "both"
    LONG_ONLY = "long-only"
    SHORT_ONLY = "short-only"


class StrategyName(str, Enum):
    EMA_RSI = "ema-rsi"
    MACD = "macd"
    BOLLINGER_REVERSION = "bollinger-reversion"
    DONCHIAN_BREAKOUT = "donchian-breakout"
    RSI_REVERSAL = "rsi-reversal"
    SUPERTREND = "supertrend"
    VWAP_REVERSION = "vwap-reversion"
    STOCH_RSI_REVERSAL = "stoch-rsi-reversal"
    EMA_RIBBON = "ema-ribbon"
    MOMENTUM_SCALPING = "momentum-scalping"
    KELTNER_BREAKOUT = "keltner-breakout"
    EMA_PULLBACK = "ema-pullback"
    ATR_TRAILING_TREND = "atr-trailing-trend"
    CCI_REVERSAL = "cci-reversal"
    WILLIAMS_R_REVERSAL = "williams-r-reversal"
    BOLLINGER_SQUEEZE_RELEASE = "bollinger-squeeze-release"
    OBV_TREND = "obv-trend"
    VOLUME_BREAKOUT = "volume-breakout"
    VWAP_TREND_CONTINUATION = "vwap-trend-continuation"
    SMA_CROSSOVER = "sma-crossover"
    COMBINED_SIGNALS = "combined-signals"


class StrategyPreset(str, Enum):
    CUSTOM = "custom"
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


@dataclass(frozen=True)
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("candle prices must be positive")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("candle high/low must contain open and close")
        if self.volume < 0:
            raise ValueError("candle volume cannot be negative")


@dataclass(frozen=True)
class StrategyConfig:
    symbol: str = "BTCUSDT"
    interval: str = "1h"
    starting_balance: float = 10000.0
    fee_rate: float = 0.001
    slippage_rate: float = 0.0005
    position_fraction: float = 1.0
    allowed_side: AllowedSide = AllowedSide.BOTH
    strategy: StrategyName = StrategyName.EMA_RSI
    preset: StrategyPreset = StrategyPreset.CUSTOM
    fast_ema: int = 12
    slow_ema: int = 26
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    rsi_midline: float = 50.0
    macd_signal: int = 9
    bollinger_period: int = 20
    bollinger_stddev: float = 2.0
    donchian_period: int = 20
    atr_period: int = 14
    supertrend_multiplier: float = 3.0
    vwap_period: int = 20
    vwap_threshold_pct: float = 0.01
    stoch_rsi_period: int = 14
    stoch_rsi_oversold: float = 20.0
    stoch_rsi_overbought: float = 80.0
    ema_ribbon_fast: int = 8
    ema_ribbon_mid: int = 21
    ema_ribbon_slow: int = 55
    momentum_period: int = 10
    keltner_multiplier: float = 2.0
    cci_period: int = 20
    cci_oversold: float = -100.0
    cci_overbought: float = 100.0
    williams_period: int = 14
    williams_oversold: float = -80.0
    williams_overbought: float = -20.0
    volume_period: int = 20
    volume_multiplier: float = 1.5
    squeeze_threshold_pct: float = 0.05
    combo_strategies: str = "all"
    combo_entry_confirmations: int = 2
    combo_exit_confirmations: int = 2
    combo_lookback: int = 3
    stop_loss_pct: float = 0.03
    take_profit_pct: float = 0.06
    trailing_stop_pct: float = 0.0


@dataclass(frozen=True)
class Signal:
    type: SignalType
    reason: str


@dataclass
class Position:
    side: PositionSide
    quantity: float
    entry_price: float
    entry_time: int
    entry_reason: str
    best_price: float
    entry_fee: float = 0.0
    entry_slippage: float = 0.0


@dataclass(frozen=True)
class Trade:
    side: PositionSide
    entry_time: int
    exit_time: int
    entry_price: float
    exit_price: float
    quantity: float
    realized_pnl: float
    fees: float
    slippage: float
    entry_reason: str
    exit_reason: str


@dataclass(frozen=True)
class EquityPoint:
    time: int
    equity: float
    cash: float
    position_side: str
    position_quantity: float


@dataclass(frozen=True)
class BacktestResult:
    trades: list[Trade]
    equity: list[EquityPoint]
    summary: dict[str, float | int | str]
