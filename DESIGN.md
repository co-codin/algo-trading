# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-06-18
- Primary product surfaces: Vue control panel, `/live` chart, `/breadth` breadth dashboard, `/futoi` MOEX open interest, `/profile`, `/feedback`, `/admin`.
- Evidence reviewed: `README.md`, `frontend/src/App.vue`, `frontend/src/style.css`, `frontend/src/components/TradingViewChart.vue`.

## Brand
- Personality: Practical trading terminal, dense, calm, data-first.
- Trust signals: Local-only simulated trading boundary, visible status states, clear strategy and marker labels.
- Avoid: Marketing hero layouts, decorative illustrations, oversized cards, profit promises, and controls hidden behind command-line workflows.

## Product goals
- Goals: Let a user inspect public market candles, overlay simulated strategy markers, monitor breadth history, review MOEX futures open interest, and manage local user access.
- Non-goals: Real order placement, portfolio allocation, or guaranteed profitability.
- Success signals: `/live` is chart-first, key controls are grouped by market, signal, and refresh intent, marker meaning is clear, breadth charts are easy to inspect, FUTOI instruments are refreshed from MOEX and selectable from a compact catalog, CSV history retention is explicit, and all trading actions remain simulated.

## Personas and jobs
- Primary personas: Crypto trader, index trader, Russian equities watcher, developer evaluating signal logic.
- User jobs: Pick market/timeframe/candle depth, compare strategy signals, inspect breadth history, inspect MOEX FUTOI history, and manage account activation.
- Key contexts of use: Local desktop browser, repeated chart refreshes, quick switching between symbols and strategies.

## Information architecture
- Primary navigation: Live, Breadth, and FUTOI stay in the main tab rail; Profile and Feedback live in the account dropdown; Admin remains a main tab for admins.
- Core routes/screens: `/live`, `/chart`, `/breadth`, `/futoi`, `/profile`, `/feedback`, `/admin`.
- Content hierarchy: Live market chart first; controls remain compact above the chart; breadth charts prioritize large inspection surfaces; FUTOI prioritizes the instrument catalog, selected ticker metrics, and a dense records table; admin prioritizes user status and activation actions.

## Design principles
- Principle 1: Chart-first density. Trading decisions start from the candle chart, not explanatory copy.
- Principle 2: Controls stay immediate. Symbol, interval, candles, strategy, refresh, and marker toggles stay visible together.
- Tradeoffs: Dark terminal styling improves chart focus but requires careful contrast and restrained borders.

## Visual language
- Color: Trading terminal dark charcoal surfaces, blue command actions, green long signals, red short signals, amber busy states.
- Typography: System sans-serif, compact labels, no negative letter spacing.
- Spacing/layout rhythm: Tight 8-14px rhythm with stable grid tracks for controls.
- Shape/radius/elevation: 4-8px radii, minimal shadows, border-defined panels.
- Motion: No decorative motion; chart updates and polling status are the main dynamic feedback.
- Imagery/iconography: TradingView Lightweight Charts is the primary visual asset.

## Components
- Existing components to reuse: `TradingViewChart`, tab navigation, account dropdown, panel, status pill, control inputs, metric rows, tables.
- New/changed components: Live market strip, grouped live controls, searchable strategy picker, all-strategies marker controls, breadth chart grid, FUTOI instrument rail and detail table, locale-aware Russian live symbol labels, admin user table, profile form, standalone feedback form.
- Variants and states: Busy/error status colors, selected tab, marker toggles, empty chart state.
- Token/component ownership: CSS variables in `frontend/src/style.css`; chart palette in `TradingViewChart.vue`.

## Accessibility
- Target standard: Practical keyboard and readable contrast for local tooling.
- Keyboard/focus behavior: Inputs, selects, buttons, tabs, and links must retain visible focus outlines.
- Contrast/readability: Dark surfaces must use high-contrast foreground text and muted labels above WCAG practical thresholds.
- Screen-reader semantics: Existing labels and chart `aria-label` remain required.
- Reduced motion and sensory considerations: Avoid decorative animation.

## Responsive behavior
- Supported breakpoints/devices: Desktop-first, usable down to mobile width.
- Layout adaptations: Live controls collapse to one column below tablet width; FUTOI instrument rail stacks above detail on narrower screens; panels remain full width.
- Touch/hover differences: Do not rely on hover-only controls for core actions.

## Interaction states
- Loading: Status pill says loading/running with amber styling.
- Empty: Dashed empty surfaces explain missing run/chart data.
- Error: Status pill shows returned error message with red styling.
- Success: Status returns to ready or updated timestamp.
- Disabled: No disabled controls are currently required.
- Offline/slow network, if applicable: Market-data errors surface in the status pill.

## Content voice
- Tone: Direct, concise, operational.
- Terminology: Use strategy, marker, live market, breadth, candles, interval, simulated.
- Microcopy rules: Do not imply real trading execution or profit guarantee.

## Implementation constraints
- Framework/styling system: Vue 3 plus plain CSS variables.
- Design-token constraints: Keep tokens centralized in `frontend/src/style.css`; avoid new design-system dependencies.
- Performance constraints: Chart refreshes must stay bounded by selected candle count; historical CSV maintenance refreshes hourly and prunes rows older than one year daily.
- Compatibility constraints: Served by the Python UI and Docker image; no external account credentials.
- Test/screenshot expectations: Static UI tests cover key selectors and terminal palette; `make check` and Docker smoke tests verify integration.

## Open questions
- [ ] Add browser screenshot regression tests / owner: future UI work / impact: stronger visual confidence.
