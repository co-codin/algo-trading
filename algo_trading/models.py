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
    fast_ema: int = 12
    slow_ema: int = 26
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
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
