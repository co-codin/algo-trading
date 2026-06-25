# Project Skills

This project benefits from a small set of repeatable engineering skills. Use these when changing the app.

Detailed playbooks live in:

- `docs/skills/live-chart-ux.md`
- `docs/skills/market-data-integrations.md`
- `docs/skills/auth-admin-ops.md`
- `docs/skills/refactoring.md`

## Market Data Integration

- Keep every market source behind `MarketDataClient`.
- Add tests with fake responses before touching live APIs.
- Preserve the shared candle shape: `open_time`, `open`, `high`, `low`, `close`, `volume`.
- Route market-specific defaults in `algo_trading.ui`, not in Vue components.
- Read optional provider tokens from environment variables; keep real values in ignored `.env` and placeholders in tracked `.env.example`.

## Live Chart UX

- Default to readable charts over raw signal volume.
- For noisy views like `All strategies`, aggregate or cap markers first, then expose an opt-in detailed mode.
- Do not reset zoom on polling refresh unless the selected market, symbol, interval, or candle limit changes.
- Verify with frontend checks and, when possible, a browser smoke test.

## Auth And Admin

- Treat `is_active` as feature access and `is_admin` as admin access.
- Do not hard-code admin UI visibility by email.
- Keep the admin seeder idempotent and test password changes/promotions.
- Ensure public user payloads expose only safe account metadata.

## Frontend Changes

- Keep UI state in `frontend/src/App.vue` aligned with `frontend/src/types.ts`.
- Update English and Chinese translations together.
- Prefer compact controls and predictable tab behavior on `/live`, `/breadth`, `/profile`, and `/admin`.
- Remove dead route state, API callers, and translation keys when a page is removed.

## Verification

- Start with targeted failing tests for new behavior.
- Run the smallest relevant tests first, then the full suite.
- Run `npm run frontend:check` after Vue or translation changes.
- Rebuild Docker and smoke-check the running app before pushing runtime changes.

## Git Discipline

- Work on `main` unless the user asks for another branch.
- Keep historical data out of `.gitignore` unless explicitly requested.
- Use Lore-style commit messages with tested and not-tested trailers.
- Push only after tests and runtime checks are complete.
