---
name: moexalgo-futoi
description: Python moexalgo library workflows for futures-only FUTOI DataFrames, .env session.TOKEN setup, Market("FO").futoi, Ticker(...).futoi, futures open interest, FIZ/YUR segmentation, pos and pos_long or pos_short fields, participant counts, library parameter caveats, and aggregation caveats.
---

# MOEXAlgo FUTOI

## Overview

Use this skill when the user wants FUTOI through the `moexalgo` Python package and DataFrame analysis.

Access note: `Стартовый / Starter` free-token access has FUTOI delayed at `T - 15 days`; `Promo` has fuller/online access, subject to current entitlement.

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

fo = Market("FO")
all_futoi = fo.futoi(date="2025-01-10")

si = Ticker("SiH5")
si_futoi = si.futoi(start="2025-01-10", end="2025-01-10")
```

## Core Workflow

1. Use `Market("FO").futoi(date=...)` for all futures FUTOI rows.
2. Use `Ticker(...).futoi(start=..., end=...)` for one futures instrument.
3. Split by `clgroup`, usually `FIZ` and `YUR`.
4. Use pandas groupbys, pivots, or plots only when the user asks for that analysis.
5. Remember that FUTOI library methods do not expose `latest` or `offset`; use direct REST if the user needs those raw endpoint controls.
6. Explain that rows are aggregate futures snapshots, not individual trader records or exact single-contract FIZ/YUR positioning.

## References

Read `references/futoi.md` for signatures, fields, aggregation caveats, and DataFrame examples.

## Boundary

For browser URLs, curl, raw JSON/CSV, or no-Python output, use the direct FUTOI skill instead.
