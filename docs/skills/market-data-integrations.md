# Market Data Integration Skill

## When To Use

Use this when adding or changing Binance, Yahoo Finance, MOEX, commodities, index futures, breadth, or historical CSV flows.

## Checklist

- Keep every provider behind the shared market-data client contract.
- Normalize output to the shared candle shape before it reaches UI or simulator code.
- Read credentials from `.env`; keep only placeholders in `.env.example`.
- Persist only the latest one year of historical CSV rows.
- Prefer provider-specific tests with fake payloads before calling live APIs.
- Surface data source and delay risk in the UI.

## Verification

- Run provider-specific tests in `tests/test_data.py`.
- Run historical retention tests in `tests/test_historical_data.py`.
- Run web payload tests in `tests/test_ui.py`.
