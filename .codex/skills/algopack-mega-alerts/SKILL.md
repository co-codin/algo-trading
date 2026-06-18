---
name: algopack-mega-alerts
description: Direct ALGOPACK Mega Alerts API workflows for market anomaly alerts, alert_type thresholds, reference JSON, documented EQ/FO alert endpoints, curl, JSON/CSV handoff, simple HTML output, ISS columns/data normalization, start pagination, and observed abnormal volume or price signals.
---

# ALGOPACK Mega Alerts

## Overview

Use this skill for direct Mega Alerts endpoint access. Alerts identify unusual market activity and include historical context in the `reference` field.

Access note: `Promo` includes Mega Alerts. `Стартовый / Starter` free-token availability is planned at `T - 1 day`; verify current access before promising it.

## Quick Start

```bash
curl -L "https://apim.moex.com/iss/datashop/algopack/eq/alerts/SBER.json?from=2025-01-01&till=2025-03-30" \
  -H "Authorization: Bearer ${APIKEY}"
```

Use `date=YYYY-MM-DD` for market-wide alerts and `from=YYYY-MM-DD&till=YYYY-MM-DD` for one ticker.

## Core Workflow

1. Choose market `eq` or `fo` unless current entitlement proves more coverage.
2. Fetch alerts and parse the `data` block.
3. Normalize ISS `columns` plus `data` arrays into rows before filtering, writing tables, or charting.
4. Group by `alert_type`, `secid`, and date/time only when the requested analysis needs grouping.
5. Parse `reference` only as historical post-alert context.
6. Match output to the request: CSV/JSON tables for handoff, simple HTML charts for browser output, Matplotlib or pandas plotting for notebook/script output, and the app's existing charting stack inside an app.
7. Avoid forecast language.

## References

Read `references/mega-alerts.md` for endpoints, alert types, fields, `reference` schema, pagination, and output patterns.

## Boundary

Do not present alerts as predictions or recommendations. Phrase results as observed anomalies and historical post-alert statistics.
