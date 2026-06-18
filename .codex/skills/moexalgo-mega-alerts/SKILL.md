---
name: moexalgo-mega-alerts
description: Python moexalgo library workflows for Mega Alerts DataFrames, .env session.TOKEN setup, Market.alerts, Ticker.alerts, alert_type analysis, threshold and value comparison, reference JSON parsing, EQ/FO anomaly alerts, offset pagination, groupbys, pivots, and historical post-alert context.
---

# MOEXAlgo Mega Alerts

## Overview

Use this skill when the user wants Mega Alerts through the `moexalgo` Python package and DataFrame analysis.

Access note: `Promo` includes Mega Alerts. `Стартовый / Starter` free-token availability is planned at `T - 1 day`; verify current access before promising it.

## Quick Start

```bash
python -m pip install "moexalgo[dataframe]" python-dotenv
```

```python
import json
import os
from dotenv import load_dotenv
from moexalgo import session, Market, Ticker

load_dotenv()
session.TOKEN = os.environ["APIKEY"]

eq = Market("EQ")
alerts = eq.alerts(date="2025-01-10")

sber = Ticker("SBER")
sber_alerts = sber.alerts(start="2025-01-01", end="2025-03-30")
parsed = sber_alerts["reference"].dropna().map(json.loads)
```

## Core Workflow

1. Use `Market("EQ"|"FO").alerts(date=...)` for market-wide alerts.
2. Use `Ticker(...).alerts(start=..., end=...)` for one instrument.
3. Group by `alert_type`, `ticker`, and date/time.
4. Use library `offset` for pagination where supported; do not pass raw REST `start` to library methods.
5. Parse `reference` only when historical post-alert context is needed.
6. Avoid forecast language and recommendations.

## References

Read `references/mega-alerts.md` for signatures, alert types, fields, reference parsing, and DataFrame examples.

## Boundary

For raw endpoint URLs, curl, JSON/CSV, or no-Python workflows, use the direct Mega Alerts skill instead.
