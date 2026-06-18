---
name: algopack-access
description: ALGOPACK access, free and paid API keys, subscription, API key authorization, entitlement, and troubleshooting guidance for DataShop setup, bearer tokens, moexalgo .env session.TOKEN setup, direct REST headers, free or delayed access, 401, 403, 429, rate limits, and product boundaries.
---

# ALGOPACK Access

## Overview

Use this skill to help users get authenticated ALGOPACK access and diagnose subscription, key, entitlement, and rate-limit failures without exposing secrets.

## Core Workflow

1. Confirm whether the user is using direct REST/curl or the Python library.
2. Explain that Data MOEX/DataShop can provide free API-token access through `Стартовый / Starter`, while `Promo` is paid/subscribed access.
3. Tell users that entitlement, delay, and field coverage are account-plan dependent; real-time or fully up-to-date data requires a valid token and the relevant entitlement.
4. For direct REST, show `Authorization: Bearer ${APIKEY}` against `https://apim.moex.com/iss`.
5. For Python library workflows, store `APIKEY` in `.env`, call `load_dotenv()`, then set `session.TOKEN` from `os.environ["APIKEY"]`.
6. Map the symptom to missing/expired key, no product entitlement, wrong host, market/date coverage, or throttling.
7. State product boundaries: ALGOPACK supplies market data and analytics, not order placement.

## Quick Start

Direct REST:

```bash
curl -L "https://apim.moex.com/iss/datashop/algopack/eq/obstats.json?date=2025-01-10" \
  -H "Authorization: Bearer ${APIKEY}"
```

Python library:

```bash
python -m pip install "moexalgo[dataframe]" python-dotenv
```

```python
import os
from dotenv import load_dotenv
from moexalgo import session, Market

load_dotenv()
session.TOKEN = os.environ["APIKEY"]

eq = Market("EQ")
rows = eq.obstats(date="2025-01-10")
```

## References

Read `references/access-troubleshooting.md` for subscription setup, access levels, error diagnosis, rate limits, and escalation notes.

## Boundary

Do not ask users to paste real API keys. Do not include real keys in code, shell history, notebooks, logs, or responses.
