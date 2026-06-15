# Multilingual UI Design

## Goal

Add English and Russian language support to the Vue trading control panel, with a compact flag-based switcher. The switcher should translate browser UI text and strategy descriptions shown in dropdowns while preserving existing trading behavior, routes, API contracts, and backend error text.

## Scope

Included:

- English and Russian locales.
- A topbar language switcher using national flag labels: `🇺🇸 EN` and `🇷🇺 RU`.
- Persistent locale selection via `localStorage`.
- Translation of visible Vue UI copy: navigation tabs, headings, labels, buttons, status messages, empty states, metric labels, chart legends, and table headers.
- Translation of strategy descriptions shown in UI dropdowns by mapping strategy IDs to localized descriptions on the frontend.
- Translated chart marker prefixes and empty chart text in `TradingViewChart.vue`.

Excluded:

- Backend/API localization.
- Translation of raw backend/API error messages.
- Translation of strategy IDs, symbols, preset values, run paths, CSV field names, or API payload fields.
- Any visual redesign beyond the language switcher and text-length-safe layout adjustments.

## Architecture

Create `frontend/src/i18n.ts` as the single frontend localization source. It will define:

- `Locale = "en" | "ru"`.
- Locale metadata for display labels and flags.
- Message dictionaries for common UI text.
- Strategy description mappings keyed by strategy name.
- Lightweight helper functions for resolving messages and strategy descriptions.

`frontend/src/App.vue` will own the active locale state, initialize it from `localStorage`, persist changes, and expose a `t(key)` helper plus computed translated option arrays. Existing state and API calls remain unchanged.

`frontend/src/components/TradingViewChart.vue` will accept translated label props for chart accessibility, empty state text, and marker prefixes. English defaults should remain so the component is safe if reused without props.

## UI Behavior

The switcher appears in the topbar next to the simulation safety badge. It uses two compact buttons:

- `🇺🇸 EN`
- `🇷🇺 RU`

The active language has the same restrained trading-terminal visual language as existing tabs and buttons: clear active state, no decorative card, no route change. The switcher must remain usable on mobile without overlapping the title, subtitle, or safety badge.

Changing language immediately updates visible labels without refetching data, restarting polling, changing the selected mode, or resetting chart zoom.

## Data Flow

1. On mount, read `algoTradingLocale` from `localStorage`.
2. If the stored value is unsupported, fall back to English.
3. Render all UI text from the active locale dictionary.
4. On switch, update the locale ref and persist it.
5. API payloads continue to send stable strategy IDs, preset values, symbols, and market identifiers.

Strategy descriptions returned by `/api/strategies` remain the fallback. The frontend mapping overrides the displayed description only when a translation exists.

## Error Handling

If a translation key is missing, the UI should fall back to English for that key. If the key is missing in English too, show the key string so gaps are visible during development.

Backend/API errors are intentionally displayed unchanged. This avoids changing server behavior and keeps technical failure text exact for debugging.

## Testing

Update existing UI source tests and add coverage for:

- The i18n module defines English and Russian locales.
- The topbar renders a flag language switcher.
- Locale is loaded from and saved to `localStorage`.
- Route tab labels and combination/strategy-lab labels are translated through i18n rather than fixed English literals.
- Strategy descriptions can be localized by strategy ID.
- `TradingViewChart.vue` accepts translated label props while keeping English defaults.

Run the existing validation suite after implementation:

- Python tests covering UI/backend contracts.
- Frontend production build.

## Acceptance Criteria

- A user can switch between English and Russian from any page.
- The selected language persists after browser refresh.
- Browser UI labels and strategy dropdown descriptions are translated.
- Backend/API errors remain English.
- Live chart refresh and language switching do not reset chart zoom.
- Existing routes and API contracts remain compatible.
