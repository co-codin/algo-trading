# Strategy Lab Hardening Design

## Goal

Make the strategy lab harder to fool by adding walk-forward validation, comparison benchmarks, richer risk metrics, and CSV export for ranked results.

## Scope

- Add walk-forward validation to the existing `/api/strategy-lab` payload.
- Add benchmark rows for buy-and-hold style comparisons.
- Add richer backtest summary metrics that all runs can reuse.
- Add a CSV export path for current strategy lab rows.
- Keep the app read-only and simulation-only.

## Architecture

The simulator remains the source of trade accounting and summary metrics. Strategy-lab orchestration stays in `algo_trading/ui.py` because the existing lab endpoint already lives there, but small pure helper functions will keep window splitting, benchmark summaries, and CSV formatting testable without running the HTTP server.

Walk-forward validation will split each fetched candle set into rolling test windows. For each strategy and preset, the lab will run the same config against every window and attach aggregate fields to the ranked row: number of windows, average window return, worst window return, best window return, and percent of profitable windows. The first implementation uses out-of-sample-style fixed rolling windows over returned candles; it does not tune parameters on the train slice because the app does not yet have an optimizer.

Benchmark rows will use the same symbol candles and interval as strategy rows. The first benchmark is buy-and-hold for each requested symbol. If the user requests market comparison symbols, the same buy-and-hold calculation can compare S&P 500 futures (`ES=F`) and Nasdaq futures (`NQ=F`) through the existing Yahoo futures client when available.

## Data Flow

1. User opens Strategy Lab.
2. UI requests `/api/strategy-lab` with symbols, strategies, presets, candle limit, and optional walk-forward settings.
3. Backend fetches candles once per symbol.
4. Backend runs selected strategy/preset backtests and appends benchmark rows.
5. Backend ranks all rows by total return, then max drawdown, then trade count.
6. UI stores the returned rows in memory.
7. User clicks CSV export and the browser downloads a CSV generated from the current rows.

## Metrics

Backtest summaries will include:

- `sharpe_ratio`: average equity-period return divided by period-return standard deviation.
- `sortino_ratio`: average equity-period return divided by downside period-return deviation.
- `max_drawdown_duration`: longest consecutive equity points below the prior peak.
- `average_trade_duration`: average exit minus entry time.
- `exposure_pct`: percent of equity points where a position was open.
- `worst_trade`: lowest realized PnL across closed trades.

The metrics are deterministic and use existing equity/trade records only.

## Testing

Use TDD. Add failing simulator metric tests first, then implement metrics. Add failing strategy lab tests for benchmark rows, walk-forward aggregate fields, and CSV formatting before changing backend code. Add frontend source tests for the CSV export button and browser build verification through `make check`.

## Constraints

- No new dependencies.
- No live trading, credentials, or authenticated exchange APIs.
- CSV export uses only already-returned lab rows; it does not trigger new market-data fetches.
