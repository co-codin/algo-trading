# Multiple Strategies Design

## Goal

Add selectable trading strategies to the local read-only backtesting, bounded paper-trading, and live chart workflows.

## Scope

The project will support three layers:

- A strategy registry, where each strategy is a separate implementation with a stable name and description.
- A curated starter pack of strategies: `ema-rsi`, `macd`, `bollinger-reversion`, `donchian-breakout`, and `rsi-reversal`.
- Strategy presets: `custom`, `conservative`, `balanced`, and `aggressive`.

The existing EMA/RSI behavior remains the default through `strategy=ema-rsi` and `preset=custom`.

## Safety Boundary

The system remains public-data and simulation-only. No Binance credentials, authenticated endpoints, account state, or real order placement are added. The existing `allowed_side` control continues to gate long-only, short-only, and both-sided signals for every strategy.

## Architecture

Create a small strategy module that owns:

- `StrategyContext`: precomputed candle-derived series used by strategies.
- `TradingStrategy`: protocol/base shape for entry and exit signal methods.
- A registry that maps strategy names to implementations.
- Preset application that returns a new `StrategyConfig` with tuned parameters.

`run_backtest`, paper trading, and live chart marker generation will ask the registry for a selected strategy and use the same entry/exit signal methods. This keeps CLI, UI, and live chart behavior aligned.

## Strategies

`ema-rsi` keeps the existing behavior:

- Enter long on fast EMA crossing above slow EMA when RSI is below overbought.
- Enter short on fast EMA crossing below slow EMA when RSI is above oversold.
- Exit long/short on the opposite EMA cross.

`macd`:

- Calculate MACD as EMA(fast) minus EMA(slow), with a signal EMA over MACD.
- Enter long when MACD crosses above signal.
- Enter short when MACD crosses below signal.
- Exit on the opposite MACD/signal cross.

`bollinger-reversion`:

- Calculate a moving average and bands using a configurable standard deviation multiplier.
- Enter long when close crosses back above the lower band after being below it.
- Enter short when close crosses back below the upper band after being above it.
- Exit long near/above the moving average; exit short near/below the moving average.

`donchian-breakout`:

- Use the previous N-candle high and low as breakout levels.
- Enter long when close breaks above the previous channel high.
- Enter short when close breaks below the previous channel low.
- Exit long when close breaks below the previous channel low; exit short when close breaks above the previous channel high.

`rsi-reversal`:

- Enter long when RSI crosses upward out of oversold.
- Enter short when RSI crosses downward out of overbought.
- Exit long when RSI crosses down through the midpoint.
- Exit short when RSI crosses up through the midpoint.

## Presets

`custom` leaves user-supplied parameters unchanged.

`conservative` uses slower periods and lower position size:

- position fraction `0.5`
- stop loss `0.02`
- take profit `0.04`
- trailing stop `0.015`
- slower strategy-specific lookbacks

`balanced` uses the current defaults where possible:

- position fraction `1.0`
- stop loss `0.03`
- take profit `0.06`
- trailing stop `0`

`aggressive` uses faster periods and wider position-taking behavior:

- position fraction `1.0`
- stop loss `0.04`
- take profit `0.08`
- trailing stop `0`
- faster strategy-specific lookbacks

Preset values are deterministic and recorded in `config.json` for each run.

## UI And CLI

CLI additions:

- `--strategy` with choices from the strategy registry.
- `--preset` with choices `custom`, `conservative`, `balanced`, `aggressive`.
- Strategy-specific optional parameters for MACD, Bollinger, Donchian, and RSI midpoint.

UI additions:

- Strategy dropdown.
- Preset dropdown.
- Additional compact fields for strategy-specific parameters.
- Live chart requests include selected strategy and preset.

## Testing

Tests will cover:

- Registry lists all strategies and rejects unknown names.
- Each strategy produces at least one expected long or short entry on deterministic candles/series.
- `allowed_side` blocks disallowed entries across strategies.
- Presets alter config deterministically.
- Backtest/paper/live paths use selected strategy.
- CLI/UI payload parsing includes strategy and preset.

## Out Of Scope

- Real order execution.
- Portfolio-level multi-strategy allocation.
- Strategy optimization/grid search.
- Exchange websocket streaming.
- External charting libraries.
