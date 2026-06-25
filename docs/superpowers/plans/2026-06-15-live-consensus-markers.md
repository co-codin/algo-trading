# Live Consensus Markers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cleaner `/live` all-strategy chart view by showing consensus markers by default instead of every individual strategy arrow.

**Architecture:** Keep the backend `signals` payload unchanged and derive consensus markers in `frontend/src/App.vue`. `TradingViewChart.vue` already accepts marker arrays, so the chart component only needs optional count-aware marker label handling if required by the derived reason text.

**Tech Stack:** Vue 3 composition API, TypeScript, lightweight-charts markers, Python unittest source-contract tests, Vite build.

---

### Task 1: Specify Live Consensus Marker Contract

**Files:**
- Modify: `tests/test_ui.py`
- Read: `frontend/src/App.vue`

- [ ] **Step 1: Write the failing test**

Add this test to `UiTests` in `tests/test_ui.py`:

```python
def test_live_all_strategy_view_collapses_markers_by_consensus(self):
    source = (
        Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.vue"
    ).read_text(encoding="utf-8")

    self.assertIn('type SignalDisplayMode = "consensus" | "individual";', source)
    self.assertIn('const liveSignalDisplayMode = ref<SignalDisplayMode>("consensus");', source)
    self.assertIn("const liveConsensusMinConfirmations = ref(2);", source)
    self.assertIn("const liveSignalDisplayOptions = computed<SelectOption[]>(() => [", source)
    self.assertIn('t("options.consensusSignals")', source)
    self.assertIn('t("options.individualSignals")', source)
    self.assertIn("const consensusSignals = computed", source)
    self.assertIn("const displayedSignals = computed", source)
    self.assertIn('settings.strategy !== "all"', source)
    self.assertIn("liveConsensusMinConfirmations.value", source)
    self.assertIn("groupSignalsByConsensus", source)
    self.assertIn("formatConsensusReason", source)
    self.assertIn(':signals="displayedSignals"', source)
    self.assertIn('v-model="liveSignalDisplayMode"', source)
    self.assertIn('v-model.number="liveConsensusMinConfirmations"', source)
    self.assertNotIn("liveSignalDisplayMode.value", source.split("const liveChartResetKey = computed", 1)[1].split(");", 1)[0])
    self.assertNotIn("liveConsensusMinConfirmations.value", source.split("const liveChartResetKey = computed", 1)[1].split(");", 1)[0])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m pytest tests/test_ui.py::UiTests::test_live_all_strategy_view_collapses_markers_by_consensus -q
```

Expected: fail because `SignalDisplayMode`, consensus controls, and derived marker helpers do not exist yet.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/test_ui.py
git commit -m "Specify live consensus marker behavior" -m "Constraint: All-strategy live charts need clutter reduction without changing backend signal payloads.\nConfidence: high\nScope-risk: narrow\nDirective: Keep live chart reset keys independent from marker display preferences.\nTested: python3 -m pytest tests/test_ui.py::UiTests::test_live_all_strategy_view_collapses_markers_by_consensus -q\nNot-tested: Production implementation is intentionally absent in this red-test commit."
```

### Task 2: Add Consensus Signal State And Labels

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/i18n.ts`

- [ ] **Step 1: Implement state and translated labels**

In `frontend/src/App.vue`, add:

```ts
type SignalDisplayMode = "consensus" | "individual";

const liveSignalDisplayMode = ref<SignalDisplayMode>("consensus");
const liveConsensusMinConfirmations = ref(2);

const liveSignalDisplayOptions = computed<SelectOption[]>(() => [
  { value: "consensus", label: t("options.consensusSignals") },
  { value: "individual", label: t("options.individualSignals") },
]);
```

In `frontend/src/i18n.ts`, add localized message keys:

```ts
"labels.signalView": "Signal view",
"labels.minConfirmations": "Min confirmations",
"options.consensusSignals": "Consensus",
"options.individualSignals": "Individual",
"chart.consensusLong": "Long",
"chart.consensusShort": "Short",
```

- [ ] **Step 2: Run the focused test**

Run:

```bash
python3 -m pytest tests/test_ui.py::UiTests::test_live_all_strategy_view_collapses_markers_by_consensus -q
```

Expected: still fail because the computed consensus markers and controls are not fully wired yet.

### Task 3: Derive Consensus Markers In The Frontend

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Replace direct live signals with displayed signals**

Add helper functions in `frontend/src/App.vue`:

```ts
function groupSignalsByConsensus(signals: Marker[], minimumConfirmations: number): Marker[] {
  const groups = new Map<string, Marker[]>();
  for (const signal of signals) {
    const key = `${signal.time}:${signal.type}`;
    groups.set(key, [...(groups.get(key) ?? []), signal]);
  }
  return [...groups.values()]
    .filter((group) => group.length >= minimumConfirmations)
    .map((group) => consensusMarkerFromGroup(group))
    .sort((left, right) => Number(left.time) - Number(right.time));
}

function consensusMarkerFromGroup(group: Marker[]): Marker {
  const first = group[0];
  return {
    time: first.time,
    price: first.price,
    type: first.type,
    reason: formatConsensusReason(first.type, group),
  };
}

function formatConsensusReason(type: string, group: Marker[]): string {
  const label = type === "short_signal" ? chartLabels.value.shortSignal : chartLabels.value.longSignal;
  const strategyNames = distinctStrategyNames(group).join(", ");
  return strategyNames ? `${label} ${group.length}: ${strategyNames}` : `${label} ${group.length}`;
}

function distinctStrategyNames(group: Marker[]): string[] {
  return [...new Set(group.map((marker) => String(marker.reason).split(":", 1)[0]).filter(Boolean))];
}
```

Add computed values:

```ts
const consensusSignals = computed(() =>
  groupSignalsByConsensus(livePayload.value?.signals ?? [], liveConsensusMinConfirmations.value),
);
const displayedSignals = computed(() => {
  const rawSignals = livePayload.value?.signals ?? [];
  if (settings.strategy !== "all" || liveSignalDisplayMode.value === "individual") {
    return rawSignals;
  }
  return consensusSignals.value;
});
```

Change the chart prop from:

```vue
:signals="filteredSignals"
```

to:

```vue
:signals="displayedSignals"
```

- [ ] **Step 2: Run the focused test**

Run:

```bash
python3 -m pytest tests/test_ui.py::UiTests::test_live_all_strategy_view_collapses_markers_by_consensus -q
```

Expected: still fail only if the template controls are missing.

### Task 4: Add Live Chart Controls

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: Add controls to the live toolbar**

In the `/live` toolbar near marker toggles, add:

```vue
<label v-if="settings.strategy === 'all'">
  <span>{{ t("labels.signalView") }}</span>
  <select v-model="liveSignalDisplayMode">
    <option
      v-for="option in liveSignalDisplayOptions"
      :key="option.value"
      :value="option.value"
    >
      {{ option.label }}
    </option>
  </select>
</label>
<label v-if="settings.strategy === 'all' && liveSignalDisplayMode === 'consensus'">
  <span>{{ t("labels.minConfirmations") }}</span>
  <input v-model.number="liveConsensusMinConfirmations" type="number" min="1" max="20">
</label>
```

In `frontend/src/style.css`, add a compact width rule if needed:

```css
.live-market-strip input[type="number"] {
  min-width: 76px;
}
```

- [ ] **Step 2: Verify focused test passes**

Run:

```bash
python3 -m pytest tests/test_ui.py::UiTests::test_live_all_strategy_view_collapses_markers_by_consensus -q
```

Expected: pass.

### Task 5: Validate Full Project And Commit

**Files:**
- Modify generated assets under `algo_trading/web/dist/`

- [ ] **Step 1: Run full verification**

Run:

```bash
make check
git diff --check
```

Expected:

- `Ran 126 tests ... OK` or more, depending on existing suite count.
- `mypy` success.
- `vue-tsc --noEmit && vite build` success.
- `git diff --check` empty output and exit code `0`.

- [ ] **Step 2: Commit implementation**

```bash
git add -A
git commit -m "Reduce all-strategy live chart clutter" -m "Constraint: All-strategy live charts produced too many overlapping individual arrows.\nRejected: Backend aggregation | unnecessary API contract change for this UI-only view.\nConfidence: high\nScope-risk: moderate\nDirective: Preserve raw individual signals and keep chart reset keys independent from display filters.\nTested: make check; git diff --check\nNot-tested: Manual browser hover/click interaction for marker detail popovers because popovers are out of scope."
```

## Self-Review

- Spec coverage: The plan covers default consensus view, individual fallback, minimum confirmation filtering, translated labels, preserved backend payloads, and reset-key stability.
- Placeholder scan: No placeholder tokens or unassigned implementation steps remain.
- Type consistency: `SignalDisplayMode`, `liveSignalDisplayMode`, `liveConsensusMinConfirmations`, `consensusSignals`, and `displayedSignals` are consistently named across tests and implementation steps.
