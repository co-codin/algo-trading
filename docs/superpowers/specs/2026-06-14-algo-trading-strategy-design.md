# Algo Trading Strategy Design

Date: 2026-06-14
Project: algo-trading

## Objective

Build a local algo-trading project for BTCUSDT that supports backtesting and paper trading against Binance market data. The first version must be useful for strategy iteration while preventing accidental live trading.

## Scope

Version 1 includes:

- Historical backtesting for BTCUSDT candles.
- Live paper trading using current Binance market data.
- One starter strategy: EMA crossover with an RSI filter.
- Long and short simulated positions.
- Synthetic short accounting for backtests and paper trading; shorts do not imply real margin, futures, borrowing, or exchange order support.
- Configurable starting balance, candle interval, fees, slippage, position sizing, stop-loss, take-profit, and trailing stop.
- Local trade logs, equity curve output, and summary metrics.
- A CLI for running backtests and paper trading sessions.

## Non-Goals

Version 1 will not:

- Accept Binance API keys.
- Place real Binance orders.
- Trade real futures, margin, borrowed assets, or leverage.
- Run a production daemon.
- Optimize parameters automatically.
- Promise profitability.

## Safety Boundary

The application must be structurally unable to execute real trades in v1. Market access is read-only. The data adapter may use Binance public market data through the available Binance MCP path or a public REST fallback, but no component may call authenticated trading endpoints. Short positions are simulation-only ledger entries and must not require margin, futures, borrowing, leverage, or exchange credentials.

## Recommended Strategy

The starter strategy is an EMA crossover with an RSI filter:

- Compute a fast EMA and slow EMA from candle close prices.
- Compute RSI over the configured lookback window.
- Enter long when the fast EMA crosses above the slow EMA and RSI is below the configured overbought threshold.
- Enter short when the fast EMA crosses below the slow EMA and RSI is above the configured oversold threshold.
- Exit a long when the fast EMA crosses below the slow EMA, stop-loss is hit, take-profit is hit, or trailing stop is hit.
- Exit a short when the fast EMA crosses above the slow EMA, stop-loss is hit, take-profit is hit, or trailing stop is hit.
- Ignore new entries while already in a position.

This strategy is simple enough to test and reason about, but less naive than a raw moving-average crossover.

## Architecture

The project will be split into small modules:

- `data`: reads Binance symbols, prices, and candles through a read-only market-data client.
- `indicators`: calculates EMA and RSI from candle data.
- `strategy`: converts candles and indicators into entry and exit signals.
- `risk`: applies position side, position sizing, fees, slippage, stop-loss, take-profit, and trailing-stop rules.
- `backtest`: simulates historical execution over downloaded candles.
- `paper`: runs the same strategy over live polling data and records simulated fills.
- `storage`: writes trade logs, equity curves, and run summaries to local files.
- `cli`: exposes user commands and configuration options.

Strategy logic should be shared by backtesting and paper trading so that paper behavior matches backtest behavior as closely as possible.

## Data Flow

Backtest flow:

1. CLI receives symbol, interval, date range, and config.
2. Data client loads historical candles.
3. Indicator module calculates EMA and RSI series.
4. Strategy emits entry and exit intents.
5. Risk and simulator modules produce simulated long or short fills.
6. Storage writes trades, equity curve, and a summary report.

Paper flow:

1. CLI receives symbol, interval, and config.
2. Data client polls the latest completed candles and current price.
3. Strategy evaluates signals using the same logic as the backtester.
4. Risk module updates a simulated account.
5. Storage appends paper trades and equity snapshots locally.

## Configuration

Defaults should be conservative:

- Symbol: `BTCUSDT`
- Interval: `1h` for backtests, `1m` or `5m` for paper trading
- Starting balance: `10000` USDT
- Fee rate: `0.001`
- Slippage rate: `0.0005`
- Position size: fixed fraction of available cash
- Allowed sides: `both`, with `long-only` and `short-only` available for focused tests
- Fast EMA: `12`
- Slow EMA: `26`
- RSI period: `14`
- RSI overbought threshold: `70`
- RSI oversold threshold: `30`
- Stop-loss: configurable percentage
- Take-profit: configurable percentage
- Trailing stop: configurable percentage or disabled

Configuration may start as CLI flags with sensible defaults. A config file can be added later if command length becomes a problem.

## Storage

Backtest output should be written under `runs/backtests/<timestamp>/`.

Paper output should be written under `runs/paper/<timestamp>/`.

Each run should include:

- `config.json`
- `trades.csv`
- `equity.csv`
- `summary.json`

The summary should include total return, final balance, max drawdown, number of trades, win rate, average win, average loss, profit factor, fee total, and slippage estimate.

Trade logs should include the position side, entry reason, exit reason, entry price, exit price, quantity, realized PnL, fees, and slippage estimate.

## Error Handling

The CLI should fail clearly when:

- Binance market data is unavailable.
- A requested symbol or interval is invalid.
- Not enough candles exist to calculate indicators.
- Configuration values are invalid.
- Local output files cannot be written.

Paper trading should keep local simulated account state consistent. If polling fails, it should log the failure and retry rather than inventing prices.

## Testing

Initial tests should cover:

- EMA and RSI calculations on known small datasets.
- Signal generation for long crossover, short crossover, and non-crossover cases.
- Risk rules for stop-loss, take-profit, trailing stop, fees, and slippage.
- Backtest accounting: cash, position side, position quantity, fills, long PnL, short PnL, equity, and drawdown.
- Paper mode using a fake market-data client so no network is required.
- CLI smoke tests for backtest and paper commands with deterministic fixtures.

## Success Criteria

Version 1 is complete when:

- A user can run a BTCUSDT backtest from the CLI and receive reproducible output files.
- A user can run a paper-trading loop that records simulated trades and equity snapshots.
- Long and short simulated trades are both supported by shared strategy and risk logic.
- Backtest and paper modes share the same strategy and risk logic.
- Tests pass for indicators, strategy, risk, simulator accounting, and CLI smoke behavior.
- No code path can place a real Binance order.
