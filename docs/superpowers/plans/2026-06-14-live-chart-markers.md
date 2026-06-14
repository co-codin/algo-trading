# Live Chart Markers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dependency-free `Live` chart tab that displays public Binance candles with EMA/RSI long-short signal markers and local simulated paper-trade markers.

**Architecture:** Extend `algo_trading/ui.py` with a testable `live_chart_payload()` service and a `GET /api/live-chart` route. Reuse existing indicator and strategy functions for signal markers, read local `runs/paper/**/trades.csv` for paper markers, and render a compact SVG chart in the existing vanilla JS frontend.

**Tech Stack:** Python standard library, existing `algo_trading` modules, browser SVG through vanilla JavaScript and CSS.

---

### Task 1: Live Chart Backend Tests

**Files:**
- Modify: `tests/test_ui.py`

- [ ] **Step 1: Write failing tests**

Add imports:

```python
from algo_trading.ui import live_chart_payload, paper_trade_markers
```

Add these tests:

```python
def trending_candles() -> list[Candle]:
    prices = [10, 9, 8, 9, 11, 13, 12, 10, 8, 7, 9, 11]
    return [candle(index, price) for index, price in enumerate(prices)]


class LiveChartTests(unittest.TestCase):
    def test_live_chart_payload_returns_candles_and_strategy_signals(self):
        client = FakeClient()
        client.candles = trending_candles()

        payload = live_chart_payload(
            {
                "symbol": "BTCUSDT",
                "interval": "1h",
                "limit": 12,
                "fast_ema": 1,
                "slow_ema": 3,
                "rsi_period": 2,
                "rsi_overbought": 100,
                "rsi_oversold": 0,
            },
            client=client,
        )

        self.assertEqual(payload["symbol"], "BTCUSDT")
        self.assertEqual(len(payload["candles"]), 12)
        signal_types = {marker["type"] for marker in payload["signals"]}
        self.assertIn("long_signal", signal_types)
        self.assertIn("short_signal", signal_types)

    def test_paper_trade_markers_reads_entry_and_exit_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "paper" / "run-a"
            run_dir.mkdir(parents=True)
            (run_dir / "trades.csv").write_text(
                "\n".join(
                    [
                        "side,entry_time,exit_time,entry_price,exit_price,quantity,realized_pnl,fees,slippage,entry_reason,exit_reason",
                        "long,2,5,10,13,1,3,0,0,ema_cross_above,take_profit",
                        "short,7,9,12,9,1,3,0,0,ema_cross_below,ema_cross_above",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            markers = paper_trade_markers("BTCUSDT", 0, 10, Path(tmp))

            self.assertEqual(
                [marker["type"] for marker in markers],
                [
                    "paper_entry_long",
                    "paper_exit_long",
                    "paper_entry_short",
                    "paper_exit_short",
                ],
            )
```

- [ ] **Step 2: Verify red**

Run: `python3 -m unittest tests.test_ui -v`

Expected: import failure for `live_chart_payload` and `paper_trade_markers`.

### Task 2: Live Chart Backend

**Files:**
- Modify: `algo_trading/ui.py`

- [ ] **Step 1: Implement service helpers**

Add:

- `live_chart_payload(params, client=None, output_root="runs")`
- `paper_trade_markers(symbol, start_time, end_time, output_root="runs")`
- `_strategy_signal_markers(candles, config)`
- `_candle_payload(candle)`
- `_query_payload(query)`

Requirements:

- Fetch candles with `MarketDataClient.get_klines`.
- Build `StrategyConfig` from payload.
- Use `ema`, `rsi`, and `signal_for_index`.
- Convert `ENTER_LONG` to `long_signal` and `ENTER_SHORT` to `short_signal`.
- Read paper trades only under `runs/paper`.
- Skip malformed trade rows.

- [ ] **Step 2: Add HTTP route**

In `_handle_get`, add:

```python
if parsed.path == "/api/live-chart":
    self._send_json(
        live_chart_payload(_query_payload(urllib.parse.parse_qs(parsed.query)), client_factory(), output_path)
    )
    return
```

- [ ] **Step 3: Verify backend tests**

Run: `python3 -m unittest tests.test_ui -v`

Expected: PASS.

### Task 3: Live Chart UI

**Files:**
- Modify: `algo_trading/web/index.html`
- Modify: `algo_trading/web/styles.css`
- Modify: `algo_trading/web/app.js`

- [ ] **Step 1: Add Live tab markup**

Add a `Live` tab button and a `live-panel` section with controls for symbol, interval, candle limit, refresh seconds, strategy signals toggle, paper markers toggle, refresh button, chart container, legend, and status.

- [ ] **Step 2: Add chart styles**

Add CSS for chart controls, chart viewport, SVG path, signal markers, paper markers, and responsive layout.

- [ ] **Step 3: Add chart JavaScript**

Add functions:

- `loadLiveChart()`
- `startLivePolling()`
- `stopLivePolling()`
- `renderLiveChart(payload)`
- `drawChart(svg, candles, signals, paperMarkers)`
- helper scale and SVG element functions.

Use SVG only. Draw a price line from candle closes, then overlay marker shapes.

### Task 4: Docs, Verification, Commit, Push

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document Live tab**

Add a short README note that the local UI now includes a Live tab with public Binance candle charts, strategy markers, and simulated paper markers.

- [ ] **Step 2: Run verification**

Run:

```bash
python3 -m unittest discover -v
mypy algo_trading tests
python3 -m compileall -q algo_trading tests
git diff --check
```

Expected: all exit 0.

- [ ] **Step 3: Run server smoke**

Start `python3 -m algo_trading.ui --port 8765` with a temporary output root and verify:

```bash
curl -sf 'http://127.0.0.1:8765/api/live-chart?symbol=BTCUSDT&interval=1m&limit=80'
curl -sf http://127.0.0.1:8765/ | head -n 1
```

Expected: live-chart JSON with candles and page HTML.

- [ ] **Step 4: Commit and push**

Commit with Lore trailers, then run:

```bash
git push origin main
```
