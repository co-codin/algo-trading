---
name: algopack-hi2
description: Direct ALGOPACK HI2 API workflows for Herfindahl-Hirschman market concentration, hhi_* metrics, daily EQ/FO/FX concentration rows, raw hi2 endpoints, curl, JSON/CSV handoff, simple HTML output, ISS columns/data normalization, start pagination, and interpretation bands.
---

# ALGOPACK HI2

## Overview

Use this skill for direct HI2 endpoint access and concentration analysis. HI2 is a Herfindahl-Hirschman style metric calculated for supported EQ, FO, and FX instruments.

Access note: `Promo` includes HI2. `Стартовый / Starter` free-token availability is planned at `T - 1 day`; verify current access before promising it.

## Quick Start

```bash
curl -L "https://apim.moex.com/iss/datashop/algopack/eq/hi2/SBER.json?from=2025-01-01&till=2025-01-31" \
  -H "Authorization: Bearer ${APIKEY}"
```

Use `date=YYYY-MM-DD` for all instruments and `from=YYYY-MM-DD&till=YYYY-MM-DD` for one ticker.

## Core Workflow

1. Choose market `eq`, `fo`, or `fx`.
2. Fetch all instruments by `date` or one ticker by `from`/`till`.
3. Normalize ISS `columns` plus `data` arrays into rows before filtering, writing tables, or charting.
4. Filter by the requested `metric` or inspect returned metric values.
5. Apply broad bands when useful: below `1500`, `1500-2500`, above `2500`.
6. Match output to the request: CSV/JSON tables for handoff, simple HTML charts for browser output, Matplotlib or pandas plotting for notebook/script output, and the app's existing charting stack inside an app.
7. Explain missing rows as possible coverage, date, entitlement, or participant-threshold issues.

## References

Read `references/hi2.md` for formula, endpoints, metrics, fields, interpretation bands, pagination, and output patterns.

## Boundary

Treat HI2 as a screening and market-structure metric, not as a buy/sell signal.
