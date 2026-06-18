---
name: moexalgo-hi2
description: Python moexalgo library workflows for HI2 DataFrames, .env session.TOKEN setup, Market.hi2, Ticker.hi2, Herfindahl-Hirschman concentration, hhi_* metrics, daily EQ/FO/FX concentration analysis, offset pagination, pivots, groupbys, interpretation bands, and missing-row caveats.
---

# MOEXAlgo HI2

## Overview

Use this skill when the user wants HI2 through the `moexalgo` Python package and DataFrame analysis.

Access note: `Promo` includes HI2. `Стартовый / Starter` free-token availability is planned at `T - 1 day`; verify current access before promising it.

## Quick Start

```bash
python -m pip install "moexalgo[dataframe]" python-dotenv
```

```python
import os
from dotenv import load_dotenv
from moexalgo import session, Market, Ticker

load_dotenv()
session.TOKEN = os.environ["APIKEY"]

eq = Market("EQ")
market_hi2 = eq.hi2(date="2025-01-10")

sber = Ticker("SBER")
sber_hi2 = sber.hi2(start="2025-01-01", end="2025-01-31")
```

## Core Workflow

1. Use `Market("EQ"|"FO"|"FX").hi2(date=...)` for all instruments.
2. Use `Ticker(...).hi2(start=..., end=...)` for one instrument.
3. Filter or pivot by `metric`.
4. Use library `offset` for pagination where supported; do not pass raw REST `start` to library methods.
5. Apply broad concentration bands when useful.
6. Explain missing rows as possible coverage, entitlement, date, or participant-threshold issues.

## References

Read `references/hi2.md` for signatures, metric names, fields, interpretation bands, and DataFrame examples.

## Boundary

For raw endpoint URLs, curl, JSON/CSV, or no-Python workflows, use the direct HI2 skill instead.
