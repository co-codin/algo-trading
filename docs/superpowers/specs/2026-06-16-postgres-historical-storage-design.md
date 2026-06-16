# Postgres Historical Storage Design

## Goal

Move historical live candles and US market breadth history out of primary CSV storage and into Postgres, while keeping Redis/RQ as the background execution layer for refresh, pruning, and user-expiry jobs.

## Architecture

Add a small historical storage boundary with in-memory and Postgres implementations. The FastAPI app and RQ worker use the Postgres implementation when `DATABASE_URL` is present; tests and local no-DB runs use the in-memory fallback. CSV helpers stay available for CLI fixture export/import, but Docker app history is no longer persisted through mounted CSV cache files.

## Data Model

`market_candles` stores OHLCV candles by `(market, symbol, interval, open_time)` and tracks last update metadata. `market_breadth_bars` stores breadth OHLCV bars by `(symbol, date)`. `tracked_market_series` records the live chart series that should be refreshed hourly by the worker.

## Data Flow

`/api/live-chart` still fetches fresh provider candles for the requested market, symbol, interval, and limit. It then upserts those candles into Postgres and returns the most recent stored candles for that series, so repeated chart use builds durable history. The hourly Redis job refreshes all tracked series from their provider, merges new candles into Postgres, and daily pruning removes candles outside the retention window.

`MarketBreadthService` reads from the store first. Fresh stored breadth bars are served without calling Barchart/Cboe. Stale or missing symbols are fetched, merged, and upserted back into Postgres. The Cboe put/call ratio keeps full official history; other breadth symbols keep the configured one-year retention.

## Compatibility

Backtest fixture CSV support remains untouched. Existing CSV helper tests remain valid because CSV export is still a user-facing CLI capability. Legacy environment names such as `HISTORICAL_CSV_REFRESH_SECONDS` remain accepted as aliases, but docs and Docker point to DB-backed historical storage.

## Testing

Add unit tests for the storage contract, DB-first live-chart persistence, DB-backed breadth cache reuse, refresh jobs, and infrastructure expectations. Verification includes the full unittest suite, compile check, Docker Compose config, Docker rebuild, container health, and an RQ smoke job.
