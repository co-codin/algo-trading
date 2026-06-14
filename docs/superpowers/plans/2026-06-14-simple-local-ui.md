# Simple Local UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a localhost browser UI for running read-only backtests, bounded paper sessions, top-symbol lookup, and local run inspection without repeated CLI commands.

**Architecture:** Add a standard-library HTTP server in `algo_trading/ui.py` with small JSON endpoints backed by existing data, simulator, paper, storage, and symbol modules. Serve static files from `algo_trading/web/` and keep the CLI untouched except for documentation and package script wiring.

**Tech Stack:** Python standard library `http.server`, `json`, `csv`, `urllib.parse`; existing `algo_trading` modules; browser HTML/CSS/vanilla JavaScript.

---

### Task 1: Add UI API Tests

**Files:**
- Create: `tests/test_ui.py`

- [ ] **Step 1: Write failing tests for API service behavior**

Create `tests/test_ui.py` with tests that import the not-yet-created UI functions:

```python
import json
import tempfile
import unittest
from pathlib import Path

from algo_trading.models import Candle
from algo_trading.ui import (
    load_run_details,
    list_runs,
    run_backtest_payload,
    top_symbols_payload,
)


def candle(time: int, close: float) -> Candle:
    return Candle(
        open_time=time,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1.0,
    )


class FakeClient:
    def __init__(self) -> None:
        self.kline_symbols: list[str] = []

    def get_24h_tickers(self) -> list[dict[str, object]]:
        return [
            {"symbol": "BTCUSDT", "quoteVolume": "500", "lastPrice": "65000"},
            {"symbol": "ETHUSDT", "quoteVolume": "250", "lastPrice": "1700"},
            {"symbol": "USDCUSDT", "quoteVolume": "999", "lastPrice": "1"},
        ]

    def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        self.kline_symbols.append(symbol)
        return [candle(index, price) for index, price in enumerate([10, 12, 13, 14])]


class UiTests(unittest.TestCase):
    def test_top_symbols_payload_filters_and_ranks(self):
        payload = top_symbols_payload(FakeClient(), top=2)

        self.assertEqual([item["symbol"] for item in payload["symbols"]], ["BTCUSDT", "ETHUSDT"])

    def test_run_backtest_payload_writes_one_run_per_symbol(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as tmp:
            payload = run_backtest_payload(
                {
                    "symbols": "BTCUSDT,ETHUSDT",
                    "interval": "1h",
                    "limit": 4,
                    "fast_ema": 1,
                    "slow_ema": 2,
                    "rsi_period": 2,
                    "fee_rate": 0,
                    "slippage_rate": 0,
                },
                client=client,
                output_root=Path(tmp),
            )

            self.assertEqual(client.kline_symbols, ["BTCUSDT", "ETHUSDT"])
            self.assertEqual([run["symbol"] for run in payload["runs"]], ["BTCUSDT", "ETHUSDT"])
            self.assertEqual(len(list(Path(tmp).glob("backtests/*/summary.json"))), 2)

    def test_list_runs_reads_recent_summaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "backtests" / "20260614T010203Z"
            run_dir.mkdir(parents=True)
            (run_dir / "summary.json").write_text(
                json.dumps({"symbol": "BTCUSDT", "final_balance": 10100}),
                encoding="utf-8",
            )

            runs = list_runs(Path(tmp))

            self.assertEqual(runs[0]["mode"], "backtest")
            self.assertEqual(runs[0]["symbol"], "BTCUSDT")

    def test_load_run_details_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                load_run_details("../outside", output_root=Path(tmp))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_ui -v`

Expected: FAIL with `ModuleNotFoundError` or import errors for `algo_trading.ui`.

### Task 2: Implement UI Backend

**Files:**
- Create: `algo_trading/ui.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Implement the backend API helpers and server**

Create `algo_trading/ui.py` with:

- `top_symbols_payload(client, top)`
- `run_backtest_payload(payload, client=None, output_root=Path("runs"))`
- `run_paper_payload(payload, client=None, output_root=Path("runs"))`
- `list_runs(output_root=Path("runs"), limit=20)`
- `load_run_details(run_path, output_root=Path("runs"))`
- `create_handler(output_root=Path("runs"), client_factory=BinanceMarketDataClient)`
- `serve(host="127.0.0.1", port=8765, output_root=Path("runs"))`
- `main(argv=None)`

Implementation requirements:

- Convert JSON payload fields into `StrategyConfig` using existing defaults.
- Use `ranked_usdt_symbols` and `parse_symbol_list` for symbol handling.
- Use `run_backtest`, `write_run_outputs`, and `run_paper_session` directly.
- Catch endpoint exceptions and return JSON `{ "ok": false, "error": "..." }` with status 400 or 500.
- Restrict `load_run_details` to paths under the configured output root.
- Serve `/`, `/index.html`, `/styles.css`, and `/app.js` from `algo_trading/web/`.
- Bind to localhost by default and print the URL.

- [ ] **Step 2: Add package script**

Add this to `pyproject.toml` under `[project.scripts]`:

```toml
algo-trading-ui = "algo_trading.ui:main"
```

- [ ] **Step 3: Run UI tests**

Run: `python3 -m unittest tests.test_ui -v`

Expected: PASS.

### Task 3: Add Static Browser UI

**Files:**
- Create: `algo_trading/web/index.html`
- Create: `algo_trading/web/styles.css`
- Create: `algo_trading/web/app.js`

- [ ] **Step 1: Create the HTML shell**

Create `algo_trading/web/index.html` containing:

- Header with `Algo Trading` and `Read-only paper/backtest mode`.
- Tabs for `Backtest`, `Paper`, and `Runs`.
- One compact settings form.
- A top-symbol lookup row.
- A status/result area.
- A recent runs area.

- [ ] **Step 2: Create restrained CSS**

Create `algo_trading/web/styles.css` with:

- Dense operational layout.
- No decorative gradients or oversized landing page treatment.
- Responsive two-column desktop layout and single-column mobile layout.
- Stable dimensions for buttons, tabs, result cards, and form fields.

- [ ] **Step 3: Create browser logic**

Create `algo_trading/web/app.js` with:

- Tab switching.
- Form serialization into API payloads.
- `GET /api/symbols?top=N`.
- `POST /api/backtest`.
- `POST /api/paper`.
- `GET /api/runs`.
- `GET /api/run?path=...`.
- Loading and error states that do not clear form inputs.
- Summary, trade, and equity previews.

### Task 4: Add Documentation and CLI Safety Notes

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the UI startup command**

Add a UI section with:

```bash
python3 -m algo_trading.ui --port 8765
```

Also mention:

- Open `http://127.0.0.1:8765`.
- The UI is localhost-only by default.
- It uses read-only public market data.
- It cannot place real orders.

### Task 5: Verify and Commit

**Files:**
- All changed files.

- [ ] **Step 1: Run full local verification**

Run:

```bash
python3 -m unittest discover -v
mypy algo_trading tests
python3 -m compileall -q algo_trading tests
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 2: Run local server smoke checks**

Start the server:

```bash
python3 -m algo_trading.ui --port 8765
```

In another command, verify:

```bash
curl -s http://127.0.0.1:8765/api/runs
curl -s http://127.0.0.1:8765/
```

Expected: JSON for `/api/runs` and HTML for `/`.

- [ ] **Step 3: Commit implementation**

Use a Lore protocol commit message that records:

- Localhost standard-library UI.
- No web framework dependency.
- No authenticated exchange access.
- Verification commands and any live smoke gaps.
