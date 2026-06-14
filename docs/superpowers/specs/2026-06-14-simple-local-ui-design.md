# Simple Local UI Design

Date: 2026-06-14
Project: algo-trading

## Objective

Build a simple browser UI so the user can run backtests, bounded paper sessions, inspect top traded symbols, and review local results without typing repeated CLI commands.

The UI must preserve the current safety boundary: public read-only market data only, no Binance API keys, no authenticated exchange endpoints, and no real orders.

## Approved Direction

Use a lean local control panel instead of a dense dashboard:

- Two primary modes: `Backtest` and `Paper`.
- One form for symbol, market, strategy, and risk settings.
- One output area for status, summary metrics, equity preview, trade preview, and recent runs.
- A small `Runs` view for local backtest and paper result history.
- A visible read-only safety indicator.

The UI should feel like a utility for repeated strategy iteration, not a trading terminal or marketing page.

## Approach Options Considered

- Workbench dashboard: powerful but too visually dense for the first UI.
- Guided wizard: safer for beginners but too slow for repeated tuning.
- Simple control panel: minimal surface, fast to use, and easy to implement on top of the current code.

The simple control panel is the selected approach.

## Technical Architecture

Use Python's standard library HTTP server stack instead of adding a web framework dependency.

New components:

- `algo_trading/ui.py`: local HTTP server entrypoint and JSON API handler.
- `algo_trading/web/index.html`: static UI shell.
- `algo_trading/web/styles.css`: restrained operational styling.
- `algo_trading/web/app.js`: browser-side form handling, API calls, loading states, and result rendering.

The existing CLI remains supported. The UI should call shared application functions or existing modules directly rather than shelling out to the CLI.

## API Surface

The local server should expose:

- `GET /`: serve the UI.
- `GET /api/symbols?top=10`: return filtered top Binance USDT crypto pairs.
- `POST /api/backtest`: run a backtest with requested symbols and strategy settings.
- `POST /api/paper`: run a bounded paper session with requested settings.
- `GET /api/runs`: list local run summaries from `runs/backtests/` and `runs/paper/`.
- `GET /api/run?path=...`: return one local run's summary, trades, and equity preview.

The first version may run backtest and paper requests synchronously. The browser must show a clear running state while waiting. Paper mode remains bounded by `iterations` and `poll_seconds`; it is not a background trading daemon.

## UI Behavior

Backtest mode:

- Accept `BTCUSDT`, comma-separated symbols, or `top N`.
- Configure interval, candle limit, allowed side, starting balance, fee, slippage, position fraction, EMA, RSI, stop-loss, take-profit, trailing stop, retries, and retry delay.
- Run the backtest and show each symbol's final balance and key metrics.

Paper mode:

- Accept one symbol.
- Configure interval, candle limit, iterations, poll seconds, and the same strategy/risk fields.
- Run a bounded paper session and show the written output path plus summary.

Runs view:

- Show recent backtest and paper runs.
- Let the user inspect summary metrics, recent trades, and equity samples.

Symbols:

- Provide a quick top-symbol lookup inside the UI.
- Exclude stablecoin, fiat, and tokenized-metal bases using the same ranking logic as the CLI.

## Error Handling

The UI must show clear local errors for:

- Binance market-data outages or timeouts.
- Invalid symbols, intervals, limits, or risk settings.
- Not enough candles for indicator warmup.
- Output file read/write failures.

Errors should not clear the user's form inputs.

## Safety

The server must bind to localhost by default and print the URL on startup.

No UI field may accept API keys. No endpoint may place real orders. Paper and short positions remain simulation-only.

## Testing

Add tests for:

- API request routing with fake market-data clients where practical.
- JSON validation and error responses.
- Backtest endpoint writing output and returning summaries.
- Symbol endpoint using ranking filters.
- Run history parsing from local output directories.

Existing CLI, simulator, strategy, data, and paper tests must continue passing.

Manual smoke verification:

- Start the local UI server.
- Open the URL in a browser.
- Load top symbols.
- Run a small backtest.
- Run a bounded paper session with `poll_seconds=0`.
- Inspect the created runs.

## Success Criteria

The UI is complete when:

- The user can start one local server and run backtests or bounded paper sessions from the browser.
- The UI supports the same long/short/both strategy controls as the CLI.
- Top-symbol discovery and run history are available in the browser.
- The CLI still works.
- Tests and type checks pass.
- No code path can execute real Binance trades.
