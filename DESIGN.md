# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-06-15
- Primary product surfaces: Vue control panel, `/live` chart, backtest, paper trading, runs, strategy lab.
- Evidence reviewed: `README.md`, `frontend/src/App.vue`, `frontend/src/style.css`, `frontend/src/components/TradingViewChart.vue`.

## Brand
- Personality: Practical trading terminal, dense, calm, data-first.
- Trust signals: Local-only simulated trading boundary, visible status states, clear strategy and marker labels.
- Avoid: Marketing hero layouts, decorative illustrations, oversized cards, profit promises, and controls hidden behind command-line workflows.

## Product goals
- Goals: Let a user inspect public Binance candles, overlay simulated strategy markers, run backtests, run bounded paper sessions, and compare strategies without shell commands.
- Non-goals: Real order placement, account management, portfolio allocation, or guaranteed profitability.
- Success signals: `/live` is chart-first, key controls are visible at a glance, marker meaning is clear, and all actions remain simulated.

## Personas and jobs
- Primary personas: Crypto trader, strategy tinkerer, developer evaluating signal logic.
- User jobs: Pick market/timeframe/candle depth, compare strategy signals, review simulated trades, run strategy research loops.
- Key contexts of use: Local desktop browser, repeated chart refreshes, quick switching between symbols and strategies.

## Information architecture
- Primary navigation: Backtest, Paper, Live, Runs, Strategy Lab.
- Core routes/screens: `/backtest`, `/paper`, `/live`, `/chart`, `/runs`, `/history`, `/lab`.
- Content hierarchy: Live market chart first; controls remain compact above the chart; run and lab views prioritize tables and metrics.

## Design principles
- Principle 1: Chart-first density. Trading decisions start from the candle chart, not explanatory copy.
- Principle 2: Controls stay immediate. Symbol, interval, candles, strategy, refresh, and marker toggles stay visible together.
- Tradeoffs: Dark terminal styling improves chart focus but requires careful contrast and restrained borders.

## Visual language
- Color: Trading terminal dark charcoal surfaces, blue command actions, green long signals, red short signals, amber busy states, violet paper exits.
- Typography: System sans-serif, compact labels, no negative letter spacing.
- Spacing/layout rhythm: Tight 8-14px rhythm with stable grid tracks for controls.
- Shape/radius/elevation: 4-8px radii, minimal shadows, border-defined panels.
- Motion: No decorative motion; chart updates and polling status are the main dynamic feedback.
- Imagery/iconography: TradingView Lightweight Charts is the primary visual asset.

## Components
- Existing components to reuse: `TradingViewChart`, tab navigation, panel, status pill, control inputs, metric rows, tables.
- New/changed components: Live market strip, all-strategies selector option, dark chart theme.
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
- Layout adaptations: Live controls collapse to one column below tablet width; panels remain full width.
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
- Terminology: Use strategy, marker, live market, paper marker, candles, interval, simulated.
- Microcopy rules: Do not imply real trading execution or profit guarantee.

## Implementation constraints
- Framework/styling system: Vue 3 plus plain CSS variables.
- Design-token constraints: Keep tokens centralized in `frontend/src/style.css`; avoid new design-system dependencies.
- Performance constraints: Chart refreshes must stay bounded by selected candle count.
- Compatibility constraints: Served by the Python UI and Docker image; no external account credentials.
- Test/screenshot expectations: Static UI tests cover key selectors and terminal palette; `make check` and Docker smoke tests verify integration.

## Open questions
- [ ] Add browser screenshot regression tests / owner: future UI work / impact: stronger visual confidence.
