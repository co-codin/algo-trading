---
name: moex-iss
description: MOEX ISS and ISS+ mechanics for raw REST endpoints, public iss.moex.com access, authenticated apim.moex.com access, output formats, iss.only, iss.json, start pagination by returned row count, response block normalization, discovery and history routes, calendars, boardgroups, and websocket/STOMP concepts.
---

# MOEX ISS

## Overview

Use this skill for generic MOEX ISS/ISS+ mechanics that are not specific to one ALGOPACK dataset. Prefer dataset-specific skills for SuperCandles, FUTOI, HI2, Mega Alerts, and market-data examples.

## Core Workflow

1. Choose host: `https://iss.moex.com/iss` for public ISS or `https://apim.moex.com/iss` for authenticated real-time, fully up-to-date, or subscriber-only routes.
2. Choose format suffix: `.json`, `.csv`, `.xml`, or `.html`.
3. Use `iss.only` and column filters to keep payloads small.
4. Normalize ISS `columns` plus `data` arrays into rows before filtering, joining, writing tables, or charting.
5. Paginate with `start` until the target block returns no rows, advancing by the returned row count.
6. Match output to the request: CSV/JSON tables for handoff, simple HTML charts for browser output, Matplotlib or pandas plotting for notebook/script output, and the app's existing charting stack inside an app.

## Quick Start

```bash
curl -L "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json?iss.only=marketdata&marketdata.columns=SECID,LAST,UPDATETIME"
```

Authenticated:

```bash
curl -L "https://apim.moex.com/iss/datashop/algopack/eq/tradestats/SBER.json?from=2025-01-01&till=2025-01-31&start=0" \
  -H "Authorization: Bearer ${APIKEY}"
```

## References

Read these as needed:

- `references/rest-iss.md` for REST patterns, response parsing, pagination, discovery, history, and query parameters.
- `references/calendars.md` for trading calendars, sessions, suspensions, and settlement-related endpoints.
- `references/issplus.md` for ISS+ websocket/STOMP concepts and local beta client shape.

## Boundary

Never expose real keys in URLs, code samples, logs, screenshots, or responses. Use environment variables or placeholders.
