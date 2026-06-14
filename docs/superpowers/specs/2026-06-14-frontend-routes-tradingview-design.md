# Frontend Routes And TradingView Chart Design

## Goal

Add direct browser URLs for the local UI views and replace the custom live SVG chart with TradingView Lightweight Charts while preserving the read-only paper trading safety boundary.

## Approved Routes

- `/` and `/backtest` open the backtest workspace.
- `/paper` opens the paper-trading workspace.
- `/live` opens the live market view.
- `/chart` is an alias for the live market view.
- `/runs` and `/history` open saved local runs.

Unknown non-API paths continue returning 404 instead of silently serving the app. API and static routes remain explicit.

## Frontend Behavior

The existing mode tabs remain the primary navigation. Clicking a tab updates browser history to the canonical route for that mode. Browser back and forward events switch the visible mode without reloading the app.

Initial page load derives the active mode from `window.location.pathname`, so direct visits to `/live`, `/chart`, `/paper`, and `/runs` work.

## Chart Design

The live market panel uses TradingView Lightweight Charts for an interactive candlestick chart. The app loads the library from TradingView's published CDN build and initializes the chart only when the live/chart view is active.

The existing `/api/live-chart` payload remains the data contract:

- `candles` become candlestick series data.
- `signals` become green upward long markers and red downward short markers.
- `paper_markers` become distinct entry/exit markers.

If the TradingView library is unavailable, the live panel shows a chart-specific error and does not break the rest of the UI.

## Testing

Backend tests cover the new frontend route allowlist and confirm API routes are not treated as frontend routes. JavaScript syntax checks cover the browser code. Local smoke checks fetch each direct frontend route and `/api/runs`.

## Non-Goals

- No real order placement.
- No Binance credentials.
- No full TradingView Advanced Chart iframe widget.
- No catch-all SPA fallback for arbitrary paths.
