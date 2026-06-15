# Live Consensus Marker Design

## Goal

Reduce `/live` chart clutter when the strategy selector is set to `All strategies` while preserving access to individual strategy signals.

## Approved Behavior

- Single-strategy mode keeps the current chart behavior.
- `All strategies` mode defaults to a consensus view.
- Consensus view collapses raw strategy arrows into one marker per candle and direction.
- Consensus marker labels show the side and strategy count, for example `Long 4` or `Short 2`.
- Users can switch the live chart signal display between:
  - `Consensus`
  - `Individual`
- Users can filter consensus markers with a minimum confirmation count.
- The default minimum confirmation count is `2` so the chart emphasizes agreement instead of every isolated signal.
- The raw backend payload remains compatible: the existing `signals` array still contains individual marker records.

## UI Shape

The live chart control strip gets two small controls near the existing marker toggles:

- `Signal view` select: `Consensus` / `Individual`
- `Min confirmations` number input: minimum `1`, default `2`

The min-confirmation input is useful only for consensus view and only affects the frontend view. The existing `Strategy markers` checkbox still controls whether strategy markers are displayed at all.

## Data Flow

The frontend derives consensus markers from `livePayload.signals`.

For each marker:

1. Use `time` and `type` as the grouping key.
2. Count markers in the group.
3. Keep groups whose count is at least `liveConsensusMinConfirmations`.
4. Emit one chart marker with:
   - same `time`
   - same `type`
   - representative `price`
   - reason text containing the count and distinct strategy names when available

Individual view returns the raw `livePayload.signals`.

## Scope

In scope:

- `/live` chart only.
- Frontend aggregation and controls.
- Tests for the derived consensus marker contract and chart props.
- English/Russian labels for new controls.

Out of scope:

- Backend response shape changes.
- New API query parameters.
- Strategy algorithm changes.
- Combination signal engine changes.
- Tooltip/detail popovers.

## Testing

- Source-level UI tests verify the controls, default mode, default minimum confirmation count, and derived marker computation.
- Existing live chart zoom-preservation behavior remains unchanged because the reset key must not include signal display mode or minimum confirmation settings.
- Full `make check` validates backend tests, type checks, compile checks, and frontend build.
