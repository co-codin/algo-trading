# Algo Trading V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local BTCUSDT backtesting and paper-trading CLI with simulated long and short positions and no live-order capability.

**Architecture:** Use a small Python package with pure domain modules for candles, indicators, strategy, risk/accounting, simulation, storage, and CLI orchestration. Backtesting and paper trading share the same strategy and simulator so live polling behaves like historical replay. Binance access is read-only public market data; there are no API-key fields or authenticated execution clients.

**Tech Stack:** Python 3 standard library, `argparse`, `csv`, `json`, `urllib.request`, `unittest`.

---

## File Structure

- Create `pyproject.toml`: package metadata and console script.
- Create `README.md`: short usage and safety notes.
- Create `algo_trading/__init__.py`: package marker.
- Create `algo_trading/models.py`: dataclasses/enums for candles, config, signals, positions, trades, equity, and summaries.
- Create `algo_trading/indicators.py`: EMA and RSI calculations.
- Create `algo_trading/strategy.py`: EMA/RSI long-short signal generation.
- Create `algo_trading/simulator.py`: account state, long/short fills, fees, slippage, stops, drawdown, and summary metrics.
- Create `algo_trading/data.py`: read-only Binance public REST market-data client plus in-memory fake client interface support.
- Create `algo_trading/storage.py`: run directory creation and `config.json`, `trades.csv`, `equity.csv`, `summary.json` writers.
- Create `algo_trading/paper.py`: bounded polling loop for paper trading.
- Create `algo_trading/cli.py`: `backtest` and `paper` subcommands.
- Create `tests/test_indicators.py`: deterministic EMA/RSI tests.
- Create `tests/test_strategy.py`: long, short, and no-signal strategy tests.
- Create `tests/test_simulator.py`: long and short accounting tests.
- Create `tests/test_storage.py`: output file tests.
- Create `tests/test_paper.py`: fake-client paper loop test.
- Create `tests/test_cli.py`: CLI smoke tests using deterministic fixtures.

## Task 1: Project Skeleton and Domain Models

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `algo_trading/__init__.py`
- Create: `algo_trading/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing model tests**

Create `tests/test_models.py`:

```python
import unittest

from algo_trading.models import (
    AllowedSide,
    Candle,
    StrategyConfig,
    PositionSide,
    SignalType,
)


class ModelTests(unittest.TestCase):
    def test_default_config_is_safe_and_both_sided(self):
        config = StrategyConfig()

        self.assertEqual(config.symbol, "BTCUSDT")
        self.assertEqual(config.allowed_side, AllowedSide.BOTH)
        self.assertEqual(config.starting_balance, 10000.0)
        self.assertEqual(config.fee_rate, 0.001)
        self.assertEqual(config.slippage_rate, 0.0005)

    def test_candle_rejects_invalid_prices(self):
        with self.assertRaises(ValueError):
            Candle(open_time=1, open=100.0, high=99.0, low=90.0, close=95.0, volume=1.0)

    def test_enums_capture_long_short_signal_shape(self):
        self.assertEqual(PositionSide.LONG.value, "long")
        self.assertEqual(PositionSide.SHORT.value, "short")
        self.assertEqual(SignalType.ENTER_LONG.value, "enter_long")
        self.assertEqual(SignalType.ENTER_SHORT.value, "enter_short")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the model test and verify it fails**

Run: `python -m unittest tests.test_models -v`

Expected: FAIL because `algo_trading.models` does not exist.

- [ ] **Step 3: Implement the project skeleton and models**

Create `pyproject.toml`:

```toml
[project]
name = "algo-trading"
version = "0.1.0"
description = "Local BTCUSDT backtesting and paper trading simulator"
requires-python = ">=3.11"

[project.scripts]
algo-trading = "algo_trading.cli:main"
```

Create `README.md`:

```markdown
# Algo Trading

Local BTCUSDT backtesting and paper trading.

Safety boundary: this project uses read-only public market data only. It does not accept Binance API keys and cannot place real orders.
```

Create `algo_trading/__init__.py`:

```python
"""Local BTCUSDT backtesting and paper-trading simulator."""
```

Create `algo_trading/models.py`:

```python
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
```

- [ ] **Step 4: Run the model test and verify it passes**

Run: `python -m unittest tests.test_models -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add pyproject.toml README.md algo_trading/__init__.py algo_trading/models.py tests/test_models.py
git commit -m "Add safe trading domain model"
```

## Task 2: Indicators

**Files:**
- Create: `algo_trading/indicators.py`
- Create: `tests/test_indicators.py`

- [ ] **Step 1: Write the failing indicator tests**

Create `tests/test_indicators.py`:

```python
import unittest

from algo_trading.indicators import ema, rsi


class IndicatorTests(unittest.TestCase):
    def test_ema_uses_standard_smoothing(self):
        values = [10.0, 11.0, 12.0, 13.0]

        result = ema(values, period=3)

        self.assertEqual(result, [10.0, 10.5, 11.25, 12.125])

    def test_rsi_returns_neutral_until_enough_data(self):
        result = rsi([10.0, 11.0, 10.0], period=14)

        self.assertEqual(result, [50.0, 50.0, 50.0])

    def test_rsi_detects_strong_uptrend(self):
        values = [float(v) for v in range(1, 18)]

        result = rsi(values, period=14)

        self.assertEqual(result[:14], [50.0] * 14)
        self.assertEqual(result[-1], 100.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run indicator tests and verify failure**

Run: `python -m unittest tests.test_indicators -v`

Expected: FAIL because `algo_trading.indicators` does not exist.

- [ ] **Step 3: Implement indicators**

Create `algo_trading/indicators.py`:

```python
from __future__ import annotations


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
```

- [ ] **Step 4: Run indicator tests and verify pass**

Run: `python -m unittest tests.test_indicators -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add algo_trading/indicators.py tests/test_indicators.py
git commit -m "Add deterministic indicators"
```

## Task 3: Strategy Signals

**Files:**
- Create: `algo_trading/strategy.py`
- Create: `tests/test_strategy.py`

- [ ] **Step 1: Write failing strategy tests**

Create `tests/test_strategy.py`:

```python
import unittest

from algo_trading.models import AllowedSide, SignalType, StrategyConfig
from algo_trading.strategy import signal_for_index


class StrategyTests(unittest.TestCase):
    def test_enter_long_on_fast_cross_above_slow(self):
        config = StrategyConfig(rsi_overbought=70.0)

        signal = signal_for_index(config, fast=[9.0, 11.0], slow=[10.0, 10.0], rsi_values=[50.0, 60.0], index=1)

        self.assertEqual(signal.type, SignalType.ENTER_LONG)

    def test_enter_short_on_fast_cross_below_slow(self):
        config = StrategyConfig(rsi_oversold=30.0)

        signal = signal_for_index(config, fast=[11.0, 9.0], slow=[10.0, 10.0], rsi_values=[50.0, 40.0], index=1)

        self.assertEqual(signal.type, SignalType.ENTER_SHORT)

    def test_long_only_blocks_short(self):
        config = StrategyConfig(allowed_side=AllowedSide.LONG_ONLY)

        signal = signal_for_index(config, fast=[11.0, 9.0], slow=[10.0, 10.0], rsi_values=[50.0, 40.0], index=1)

        self.assertEqual(signal.type, SignalType.HOLD)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run strategy tests and verify failure**

Run: `python -m unittest tests.test_strategy -v`

Expected: FAIL because `algo_trading.strategy` does not exist.

- [ ] **Step 3: Implement strategy**

Create `algo_trading/strategy.py`:

```python
from __future__ import annotations

from algo_trading.models import AllowedSide, Signal, SignalType, StrategyConfig


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
```

- [ ] **Step 4: Run strategy tests and verify pass**

Run: `python -m unittest tests.test_strategy -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add algo_trading/strategy.py tests/test_strategy.py
git commit -m "Add long short strategy signals"
```

## Task 4: Backtest Simulator

**Files:**
- Create: `algo_trading/simulator.py`
- Create: `tests/test_simulator.py`

- [ ] **Step 1: Write failing simulator tests**

Create `tests/test_simulator.py`:

```python
import unittest

from algo_trading.models import Candle, PositionSide, StrategyConfig
from algo_trading.simulator import run_backtest


def candle(time: int, close: float) -> Candle:
    return Candle(open_time=time, open=close, high=close + 1.0, low=close - 1.0, close=close, volume=1.0)


class SimulatorTests(unittest.TestCase):
    def test_backtest_produces_trade_and_equity(self):
        candles = [candle(index, price) for index, price in enumerate([10, 11, 12, 11, 10, 9, 8, 9, 10, 11, 12, 13])]
        config = StrategyConfig(fast_ema=2, slow_ema=3, rsi_period=2, position_fraction=0.5)

        result = run_backtest(candles, config)

        self.assertGreaterEqual(len(result.equity), len(candles))
        self.assertIn("final_balance", result.summary)

    def test_short_trade_can_profit_when_price_falls(self):
        candles = [candle(index, price) for index, price in enumerate([10, 12, 11, 10, 9, 8, 7])]
        config = StrategyConfig(fast_ema=1, slow_ema=2, rsi_period=2, fee_rate=0.0, slippage_rate=0.0, position_fraction=1.0)

        result = run_backtest(candles, config)

        short_trades = [trade for trade in result.trades if trade.side is PositionSide.SHORT]
        self.assertTrue(short_trades)
        self.assertTrue(any(trade.realized_pnl > 0 for trade in short_trades))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run simulator tests and verify failure**

Run: `python -m unittest tests.test_simulator -v`

Expected: FAIL because `algo_trading.simulator` does not exist.

- [ ] **Step 3: Implement simulator**

Create `algo_trading/simulator.py` with an `Account` class, fill helpers, stop logic, summary metrics, and `run_backtest(candles, config)`. The implementation must:

- Calculate fast EMA, slow EMA, and RSI from candle closes.
- Open a long or short when strategy signals entry and no position is open.
- Close existing positions on opposite crossover, stop-loss, take-profit, trailing stop, or final candle.
- Apply fees and slippage on entry and exit.
- Calculate long PnL as `(exit_price - entry_price) * quantity`.
- Calculate short PnL as `(entry_price - exit_price) * quantity`.
- Append one `EquityPoint` per candle.

- [ ] **Step 4: Run simulator tests and verify pass**

Run: `python -m unittest tests.test_simulator -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add algo_trading/simulator.py tests/test_simulator.py
git commit -m "Add long short backtest simulator"
```

## Task 5: Storage and CLI Backtest

**Files:**
- Create: `algo_trading/storage.py`
- Create: `algo_trading/data.py`
- Create: `algo_trading/cli.py`
- Create: `tests/test_storage.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing storage and CLI tests**

Create tests that:

- Write a fake `BacktestResult` to a temporary directory and assert `config.json`, `trades.csv`, `equity.csv`, and `summary.json` exist.
- Run `cli.main(["backtest", "--fixture", fixture_path, "--output-root", tmpdir])` and assert it returns `0` and writes a summary.

- [ ] **Step 2: Run storage and CLI tests and verify failure**

Run: `python -m unittest tests.test_storage tests.test_cli -v`

Expected: FAIL because storage, data, and CLI modules do not exist.

- [ ] **Step 3: Implement storage, fixture loading, Binance REST client, and backtest CLI**

Implementation requirements:

- `storage.write_run_outputs(kind, config, result, output_root)` writes timestamped run directories.
- `data.load_candles_from_csv(path)` loads deterministic fixture candles.
- `data.BinanceMarketDataClient.get_klines(symbol, interval, limit)` uses `https://api.binance.com/api/v3/klines` with `urllib.request`.
- `cli.main(argv=None)` supports `backtest` with `--symbol`, `--interval`, `--limit`, `--fixture`, `--output-root`, and strategy/risk flags.

- [ ] **Step 4: Run storage and CLI tests and verify pass**

Run: `python -m unittest tests.test_storage tests.test_cli -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add algo_trading/storage.py algo_trading/data.py algo_trading/cli.py tests/test_storage.py tests/test_cli.py
git commit -m "Add backtest CLI outputs"
```

## Task 6: Paper Trading Loop

**Files:**
- Create: `algo_trading/paper.py`
- Modify: `algo_trading/cli.py`
- Create: `tests/test_paper.py`

- [ ] **Step 1: Write failing paper tests**

Create `tests/test_paper.py` with a fake market-data client that returns deterministic candle batches. Assert `run_paper_session(..., iterations=2)` writes paper output and never needs credentials.

- [ ] **Step 2: Run paper tests and verify failure**

Run: `python -m unittest tests.test_paper -v`

Expected: FAIL because `algo_trading.paper` does not exist.

- [ ] **Step 3: Implement bounded paper loop and CLI command**

Implementation requirements:

- `paper.run_paper_session(client, config, output_root, poll_seconds, iterations)` polls read-only candles.
- The loop reuses `run_backtest` against the collected candle history to keep accounting consistent.
- `cli.main()` supports `paper` with `--iterations` for safe test/demo runs.
- No code accepts or reads API keys.

- [ ] **Step 4: Run paper tests and verify pass**

Run: `python -m unittest tests.test_paper -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add algo_trading/paper.py algo_trading/cli.py tests/test_paper.py
git commit -m "Add bounded paper trading loop"
```

## Task 7: Final Verification and Demo

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README usage**

Add commands:

```bash
python -m algo_trading.cli backtest --symbol BTCUSDT --interval 1h --limit 300
python -m algo_trading.cli paper --symbol BTCUSDT --interval 1m --iterations 3
python -m unittest discover -v
```

- [ ] **Step 2: Run full tests**

Run: `python -m unittest discover -v`

Expected: all tests pass.

- [ ] **Step 3: Run live read-only backtest smoke**

Run: `python -m algo_trading.cli backtest --symbol BTCUSDT --interval 1h --limit 120`

Expected: command exits `0`, writes `runs/backtests/<timestamp>/summary.json`, and does not request credentials.

- [ ] **Step 4: Run bounded paper smoke**

Run: `python -m algo_trading.cli paper --symbol BTCUSDT --interval 1m --iterations 2 --poll-seconds 0`

Expected: command exits `0`, writes `runs/paper/<timestamp>/summary.json`, and does not request credentials.

- [ ] **Step 5: Commit README and final verification state**

Run:

```bash
git add README.md
git commit -m "Document safe simulator usage"
```

## Self-Review

Spec coverage:

- Backtesting: Tasks 4, 5, and 7.
- Paper trading: Task 6 and Task 7.
- EMA/RSI long-short strategy: Tasks 2 and 3.
- Long and synthetic short accounting: Task 4.
- Fees, slippage, stops, and summary metrics: Task 4.
- Local run storage: Task 5.
- CLI: Tasks 5 and 6.
- Read-only Binance market data: Task 5.
- No live orders/API keys: Tasks 1, 5, 6, and final smoke checks.

Placeholder scan: no red-flag marker text is present in this plan.

Type consistency: plan uses `StrategyConfig`, `Candle`, `Signal`, `Position`, `Trade`, `EquityPoint`, and `BacktestResult` consistently across tasks.
