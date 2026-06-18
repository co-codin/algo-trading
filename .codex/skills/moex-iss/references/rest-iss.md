# Direct ISS REST Reference

## Contents

- [Hosts](#hosts)
- [requests Example](#requests-example)
- [curl Example](#curl-example)
- [Output Formats](#output-formats)
- [Response Parsing](#response-parsing)
- [Pagination](#pagination)
- [Common Endpoint Patterns](#common-endpoint-patterns)
- [Discovery and History Endpoints](#discovery-and-history-endpoints)
- [Useful Query Parameters](#useful-query-parameters)
- [Unsupported or Edge Cases](#unsupported-or-edge-cases)

## Hosts

- Public ISS: `https://iss.moex.com/iss`
- Authenticated ALGOPACK/API gateway: `https://apim.moex.com/iss`

Use `apim.moex.com` plus `Authorization: Bearer ${APIKEY}` for real-time, fully up-to-date, or subscriber-only ALGOPACK datasets. Use `iss.moex.com` for public endpoints when entitlement is not required; public data can be delayed or limited.

## requests Example

```python
import os
import requests
from dotenv import load_dotenv

load_dotenv()
url = "https://apim.moex.com/iss/datashop/algopack/eq/tradestats/SBER.json"
headers = {"Authorization": f"Bearer {os.environ['APIKEY']}"}
params = {"from": "2025-01-01", "till": "2025-01-31", "start": 0}

resp = requests.get(url, headers=headers, params=params, timeout=30)
resp.raise_for_status()
payload = resp.json()
```

## curl Example

```bash
curl -L "https://apim.moex.com/iss/datashop/algopack/eq/tradestats/SBER.json?from=2025-01-01&till=2025-01-31&start=0" \
  -H "Authorization: Bearer ${APIKEY}"
```

## Output Formats

Most ISS routes select response format by suffix: `.json`, `.csv`, `.xml`, or `.html`. Keep examples on `.json` for programmatic parsing unless the user explicitly needs another format. Use `.csv` or normalized JSON tables for data handoff, simple HTML charts for browser output, pandas or Matplotlib plotting for notebook/script output, and the project's existing charting stack inside an app. If an endpoint is documented without a suffix, append `.json` before writing JSON parsing code.

## Response Parsing

ISS JSON blocks usually have `columns` and `data` arrays. Normalize the target block into rows before filtering, joining, writing tables, or charting:

```python
import pandas as pd

block = payload["data"] if "data" in payload else payload["candles"]
df = pd.DataFrame(block["data"], columns=[c.lower() for c in block["columns"]])
```

For standard market data, blocks can include `securities`, `marketdata`, `trades`, `orderbook`, `candles`, or product-specific blocks like `futoi`.

## Pagination

Use the `start` query parameter. Loop until the target block returns no rows:

```python
import pandas as pd
import requests

def fetch_all(url, block_name, headers=None, params=None):
    params = dict(params or {})
    start = int(params.get("start", 0))
    frames = []
    while True:
        params["start"] = start
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        block = resp.json()[block_name]
        rows = block["data"]
        if not rows:
            break
        frames.append(pd.DataFrame(rows, columns=[c.lower() for c in block["columns"]]))
        start += len(rows)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
```

Do not assume a max page size. Local notes mention endpoints returning different limits, and SuperCandles raw endpoints can require pagination for full days/ranges. Keep `limit` route-dependent where supported; do not promise one universal maximum.

## Common Endpoint Patterns

Market data:

- EQ all securities/marketdata: `/iss/engines/stock/markets/shares/boards/TQBR/securities.json`
- FO all securities/marketdata: `/iss/engines/futures/markets/forts/boards/RFUD/securities.json`
- FX all securities/marketdata: `/iss/engines/currency/markets/selt/boards/CETS/securities.json`
- Ticker candles: `/iss/engines/{engine}/markets/{market}/boards/{board}/securities/{ticker}/candles.json`
- Ticker trades: `/iss/engines/{engine}/markets/{market}/boards/{board}/securities/{ticker}/trades.json`
- Ticker orderbook: `/iss/engines/{engine}/markets/{market}/boards/{board}/securities/{ticker}/orderbook.json`

ALGOPACK:

- SuperCandles: `/iss/datashop/algopack/{eq|fo|fx}/{tradestats|orderstats|obstats}[/{ticker}].json`
- HI2: `/iss/datashop/algopack/{eq|fo|fx}/hi2[/{ticker}].json`
- Mega Alerts: `/iss/datashop/algopack/{eq|fo}/alerts[/{ticker}].json`
- FUTOI: `/iss/analyticalproducts/futoi/securities[/{ticker}].json`

## Discovery and History Endpoints

Raw securities and ticker discovery:

- All securities list/search: `/iss/securities.json`
- One security card: `/iss/securities/{ticker}.json`
- Shares securities list: `/iss/engines/stock/markets/shares/securities.json`
- Futures securities list: `/iss/engines/futures/markets/forts/securities.json`
- Currency securities list: `/iss/engines/currency/markets/selt/securities.json`
- Index securities list: `/iss/engines/stock/markets/index/securities.json`

Boardgroup discovery is useful when a board-specific route misses instruments:

- Shares boardgroup: `/iss/engines/stock/markets/shares/boardgroups/57/securities.json?iss.only=securities&iss.json=extended&securities.columns=SECID,SHORTNAME`
- Futures boardgroup: `/iss/engines/futures/markets/forts/boardgroups/45/securities.json?iss.only=securities&iss.json=extended&securities.columns=SECID,SHORTNAME`
- Currency boardgroup: `/iss/engines/currency/markets/selt/boardgroups/13/securities.json?iss.only=securities&iss.json=extended&securities.columns=SECID,SHORTNAME`
- Index boardgroup candles: `/iss/engines/stock/markets/index/boardgroups/9/securities/{ticker}/candles.json`

History routes use the `/iss/history/...` prefix and often expose different blocks/columns than current-session endpoints:

- Futures trades history: `/iss/history/engines/futures/markets/forts/trades.json`
- Bond securities history: `/iss/history/engines/stock/markets/bonds/securities.json`
- Index securities history: `/iss/history/engines/stock/markets/index/securities.json`

## Useful Query Parameters

- `iss.only=block`: return only selected block, such as `marketdata`, `securities`, or `candles`.
- `iss.json=extended`: use extended JSON format when needed by integration code.
- `from`, `till`: historical date range.
- `date`: single-date product query.
- `interval`: candle interval, such as `1`, `10`, `60`, `24`, `7`, `31`.
- `latest=1`: latest product rows where supported.
- `start`: pagination offset.

## Unsupported or Edge Cases

- If `moexalgo` lacks a helper for a calendar/static endpoint, use direct ISS.
- If an endpoint returns 403 with a token, verify product entitlement and endpoint coverage.
- If a documented endpoint returns `text/html` instead of JSON, treat it as a current endpoint/route mismatch and verify against the live ISS reference before building parsing code.
- If an endpoint returns JSON with no rows, check trading calendar and publication cadence before assuming failure.
