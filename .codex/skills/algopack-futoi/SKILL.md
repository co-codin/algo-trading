---
name: algopack-futoi
description: Direct ALGOPACK FUTOI API workflows for futures-only open interest, FIZ/YUR segmentation, long and short participant counts, raw futoi endpoints, browser URLs, curl, JSON/CSV handoff, simple HTML output, ISS columns/data normalization, start pagination, and aggregation caveats without Python setup.
---

# ALGOPACK FUTOI

## Overview

Use this skill for direct FUTOI endpoint access. FUTOI is futures open interest split by participant group and published as aggregate snapshots; it is not for equities, FX, options, individual trader data, or exact single-contract FIZ/YUR positioning.

Access note: `Стартовый / Starter` free-token access has FUTOI delayed at `T - 15 days`; `Promo` has fuller/online access, subject to current entitlement.

## Quick Start

```bash
curl -L "https://apim.moex.com/iss/analyticalproducts/futoi/securities/Si.json?from=2025-01-10&till=2025-01-10" \
  -H "Authorization: Bearer ${APIKEY}"
```

Use `/securities.json?date=YYYY-MM-DD` for all instruments and `/securities/{ticker}.json?from=...&till=...` for one instrument or underlying.

## Core Workflow

1. Use `FO` tickers or underlyings only.
2. Fetch rows for a date/range and parse the `futoi` block.
3. Split by `clgroup`: `FIZ` for individuals, `YUR` for legal entities.
4. Normalize ISS `columns` plus `data` arrays into rows before filtering, writing tables, or charting.
5. Match output to the request: CSV/JSON tables for handoff, simple HTML charts for browser output, Matplotlib or pandas plotting for notebook/script output, and the app's existing charting stack inside an app.
6. Explain aggregation caveats before making conclusions about specific contracts or participants.

## References

Read `references/futoi.md` for endpoints, fields, aggregation rules, access caveats, pagination, and output patterns.

## Boundary

Do not infer individual trader behavior, equities/FX/options positioning, or exact single-contract FIZ/YUR positioning from aggregate FUTOI rows.
