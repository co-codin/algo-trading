# Live Chart UX Skill

## When To Use

Use this when changing `/live` chart controls, signal display, indicators, refresh behavior, chart focus, or URL-synced filters.

## Checklist

- Keep the chart readable before exposing raw signal volume.
- Preserve zoom when data refreshes or indicators change.
- Keep market, symbol, strategy, and indicator state reflected in the URL.
- Use consensus display by default for multi-strategy selections.
- Put advanced toggles near the chart, not inside hidden settings pages.
- Keep symbol search case-insensitive and fast.

## Verification

- Run `python3 -m unittest tests.test_ui.UiTests`.
- Run `npm run frontend:check`.
- Rebuild Docker and smoke-check `/live` when static assets change.
