---
name: moexalgo-supercandles
description: Python moexalgo library workflows for SuperCandles DataFrames, .env session.TOKEN setup, Market.tradestats, Market.orderstats, Market.obstats, Ticker.tradestats, Ticker.orderstats, Ticker.obstats, field interpretation, offset pagination, pivots, groupbys, and EQ/FO/FX analytics.
---

# MOEXAlgo SuperCandles

## Overview

Use this skill when the user wants SuperCandles through the `moexalgo` Python package and DataFrame analysis.

Access note: `Promo` includes SuperCandles. `Стартовый / Starter` free-token availability is planned at `T - 1 day`; verify current access before promising it.

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
trades_all = eq.tradestats(date="2025-01-10")
orders_all = eq.orderstats(date="2025-01-10")
book_latest = eq.obstats(date="2025-01-10", latest=True)

sber = Ticker("SBER")
trades = sber.tradestats(start="2025-01-01", end="2025-01-31")
orders = sber.orderstats(start="2025-01-01", end="2025-01-31")
book = sber.obstats(start="2025-01-01", end="2025-01-31")
```

## Core Workflow

1. Use `Market("EQ"|"FO"|"FX")` for all instruments by date.
2. Use `Ticker(...)` for one instrument over `start` and `end`.
3. Choose `tradestats`, `orderstats`, or `obstats` based on the metric the user needs.
4. Analyze with pandas groupbys, pivots, ratios, or plots according to the user's requested output.
5. Use library `offset` for pagination where supported; do not pass raw REST `start` to library methods.
6. Keep DataFrames as the default; mention `native=True` only when the user explicitly asks for dict iterators.

## References

Read `references/supercandles.md` for method signatures, fields, interpretation notes, and DataFrame analysis examples.

## Boundary

For raw endpoint URLs, curl, JSON/CSV, or no-Python answers, use the direct SuperCandles skill instead.
