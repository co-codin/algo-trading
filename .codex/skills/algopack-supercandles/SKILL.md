---
name: algopack-supercandles
description: Direct ALGOPACK SuperCandles API workflows for tradestats, orderstats, obstats, 5-minute trade/order/order-book metrics, field meanings, EQ/FO/FX endpoints, curl, JSON/CSV handoff, simple HTML output, ISS columns/data normalization, and start pagination.
---

# ALGOPACK SuperCandles

## Overview

Use this skill for raw SuperCandles endpoints and 5-minute metric fields. Return URLs, `curl`, normalized JSON rows, CSV/JSON handoff guidance, and concise field interpretation.

Access note: `Promo` includes SuperCandles. `Стартовый / Starter` free-token availability is planned at `T - 1 day`; verify current access before promising it.

## Quick Start

```bash
curl -L "https://apim.moex.com/iss/datashop/algopack/eq/tradestats/SBER.json?from=2025-01-01&till=2025-01-31&start=0" \
  -H "Authorization: Bearer ${APIKEY}"
```

Use `date=YYYY-MM-DD` for all instruments and `from=YYYY-MM-DD&till=YYYY-MM-DD` for one ticker.

## Core Workflow

1. Pick the dataset: `tradestats` for trade metrics, `orderstats` for order-flow metrics, or `obstats` for order-book metrics.
2. Pick the market prefix: `eq`, `fo`, or `fx`.
3. Use `latest=1` for the newest rows or `start` pagination for full days/ranges.
4. Normalize raw `secid` to `ticker` in user-facing tables.
5. Normalize ISS `columns` plus `data` arrays into rows before filtering, joining, or charting.
6. Match output to the request: CSV/JSON tables for handoff, simple HTML charts for browser output, Matplotlib or pandas plotting for notebook/script output, and the app's existing charting stack inside an app.

## References

Read `references/supercandles.md` for endpoint maps, fields, interpretation notes, limits, pagination, and output patterns.

## Boundary

Describe SuperCandles as analytics for research and monitoring. Do not turn imbalance or threshold examples into trading advice.
