# Live Chart Markers Design

Date: 2026-06-14
Project: algo-trading

## Objective

Add a live market-data chart to the local browser UI with visible markers for both strategy long/short signals and simulated paper-trade entries/exits.

The feature must preserve the project safety boundary: public Binance market data only, local simulated paper/backtest data only, no API keys, no authenticated exchange endpoints, and no real orders.

## Approved Direction

Use Approach A: a built-in simple chart with no new frontend dependency.

The first version will:

- Add a `Live` tab to the existing local UI.
- Fetch recent public Binance candles for one symbol and interval.
- Render a compact local SVG price chart in the browser.
- Overlay strategy signal markers from the current EMA/RSI rules.
- Overlay simulated paper-trade markers from recent local paper runs.
- Poll periodically while the `Live` tab is open.

## Non-Goals

This feature will not:

- Add a TradingView or charting-package dependency.
- Add real-time websocket streaming.
- Place or prepare real orders.
- Run an unbounded paper-trading daemon.
- Promise signal profitability.

## Marker Model

The chart will show two marker layers:

- Strategy signals:
  - `long_signal`: EMA fast crosses above EMA slow and RSI filter allows a long.
  - `short_signal`: EMA fast crosses below EMA slow and RSI filter allows a short.
  - These are intent markers only; they do not imply a fill.
- Paper trades:
  - `paper_entry_long` / `paper_entry_short`: local simulated trade entry from a paper run.
  - `paper_exit_long` / `paper_exit_short`: local simulated trade exit from a paper run.
  - These markers come from `runs/paper/**/trades.csv`.

Signals and paper trades should use distinct marker shapes/colors so the user can separate strategy intent from simulated execution.

## API Design

Add `GET /api/live-chart` with query parameters:

- `symbol`: default `BTCUSDT`
- `interval`: default `1m`
- `limit`: default `180`
- strategy and risk fields matching the existing UI form where relevant:
  - `allowed_side`
  - `fast_ema`
  - `slow_ema`
  - `rsi_period`
  - `rsi_overbought`
  - `rsi_oversold`
  - `stop_loss_pct`
  - `take_profit_pct`
  - `trailing_stop_pct`

Response shape:

```json
{
  "ok": true,
  "symbol": "BTCUSDT",
  "interval": "1m",
  "candles": [
    {"time": 1781438160000, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
  ],
  "signals": [
    {"time": 1781438160000, "price": 1.0, "type": "long_signal", "reason": "ema_cross_above"}
  ],
  "paper_markers": [
    {"time": 1781438160000, "price": 1.0, "type": "paper_entry_short", "reason": "ema_cross_below"}
  ]
}
```

The endpoint should use the existing `MarketDataClient.get_klines` path and current indicator/strategy functions. It should read paper trade markers from local run output only.

## UI Design

The `Live` tab should stay as simple as the approved control panel:

- Reuse the current symbol, interval, side, EMA, and RSI settings where possible.
- Provide controls for symbol, interval, candle limit, refresh seconds, and marker toggles.
- Render one chart area with price line and markers.
- Show a small legend for:
  - long signal
  - short signal
  - paper entry
  - paper exit
- Show the last refresh time and a clear error message on Binance failures.

The chart should be operational and compact rather than decorative. It should not use oversized hero layout, gradients, or a marketing-style page.

## Data Flow

1. User opens the `Live` tab.
2. Browser requests `/api/live-chart`.
3. Server fetches recent Binance candles through the read-only market-data client.
4. Server computes EMA, RSI, and strategy entry signals over those candles.
5. Server reads local paper-trade CSV files and filters markers to the requested symbol and visible time range.
6. Browser draws the price chart and overlays both marker layers.
7. Browser refreshes on a bounded interval while the tab is active.

## Error Handling

The UI must keep existing form values when refresh fails.

Errors should be visible for:

- Binance market-data outage or timeout.
- Invalid symbol, interval, limit, or strategy config.
- Not enough candles for indicator warmup.
- Malformed local paper trade output.

Malformed paper trade rows should be skipped rather than breaking the live chart.

## Testing

Add tests for:

- Live chart payload returns candles and signal markers with a fake market-data client.
- Paper marker extraction reads entry and exit markers from `trades.csv`.
- Path and malformed-row handling does not escape `runs/` or crash the endpoint.
- Existing UI, CLI, simulator, and paper tests still pass.

Manual smoke verification:

- Start the local UI server.
- Open the `Live` tab.
- Load a BTCUSDT chart.
- Confirm price line renders.
- Confirm signal markers appear when the strategy produces them.
- Run a bounded paper session and confirm paper markers are visible on the chart.

## Success Criteria

The feature is complete when:

- The user can view recent live public Binance candles in the browser.
- The chart shows both long/short strategy signals and local simulated paper-trade markers.
- The UI remains localhost-only and read-only.
- No new frontend dependency is required.
- Tests and type checks pass.
- The updated code is pushed to `origin/main`.
