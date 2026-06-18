# Direct HI2 Reference

## Meaning and Cadence

HI2 is a Herfindahl-Hirschman style concentration index:

```text
HI2 = sum(s_i ** 2)
```

where `s_i` is a participant share in percent. Shares of 50, 30, and 20 produce `2500 + 900 + 400 = 3800`.

Local docs describe daily calculation near the end of the trading day for supported shares, futures, and currency instruments. If too few participants trade an instrument, HI2 may not be calculated for that date.

`Promo` includes HI2. `Стартовый / Starter` free-token availability is planned at `T - 1 day`; if users see `403`, empty data, non-JSON responses, or missing rows, verify current entitlement and current DataShop terms before promising access.

## Endpoints

Use `https://apim.moex.com/iss` with a bearer token.

```text
/iss/datashop/algopack/eq/hi2.json?date=YYYY-MM-DD
/iss/datashop/algopack/eq/hi2/{ticker}.json?from=YYYY-MM-DD&till=YYYY-MM-DD
/iss/datashop/algopack/fo/hi2.json?date=YYYY-MM-DD
/iss/datashop/algopack/fo/hi2/{ticker}.json?from=YYYY-MM-DD&till=YYYY-MM-DD
/iss/datashop/algopack/fx/hi2.json?date=YYYY-MM-DD
/iss/datashop/algopack/fx/hi2/{ticker}.json?from=YYYY-MM-DD&till=YYYY-MM-DD
```

Examples:

```bash
curl -L "https://apim.moex.com/iss/datashop/algopack/eq/hi2.json?date=2025-01-10" \
  -H "Authorization: Bearer ${APIKEY}"
```

```bash
curl -L "https://apim.moex.com/iss/datashop/algopack/eq/hi2/SBER.csv?from=2025-01-01&till=2025-01-31" \
  -H "Authorization: Bearer ${APIKEY}"
```

## Response Block

HI2 JSON uses the `data` block. Normalize `columns` plus `data` into rows before filtering, writing tables, or charting:

```javascript
const block = payload.data;
const rows = block.data.map((row) =>
  Object.fromEntries(block.columns.map((name, index) => [name.toLowerCase(), row[index]]))
);
```

Raw ISS uses `secid`; user-facing tables can label it `ticker`.

## Pagination

Use `start` if a HI2 route caps rows for the requested date or range. Continue until the `data` block returns no rows, and advance `start` by the returned row count:

```text
start = 0
while true:
    request with start
    rows = normalized data block rows
    stop when rows is empty
    start = start + len(rows)
```

Keep `limit` route-dependent where supported; do not promise one universal maximum.

## Fields

| Field | Meaning |
| --- | --- |
| `tradedate` | Date |
| `tradetime` | Metric time |
| `secid` | Instrument id |
| `metric` | HI2 metric name |
| `value` | HHI value |
| `reference` | Additional context, often null |
| `systime` | Load/system time |

## Metric Names

Use actual returned metric values when possible. Common names:

- `hhi_volume`: concentration by trading volume.
- `hhi_buy`: concentration by buy volume.
- `hhi_sell`: concentration by sell volume.
- `hhi_netflow_buy`: concentration by positive net flow.
- `hhi_netflow_sell`: concentration by negative net flow.
- `hhi_passive`: concentration by passive/maker volume.
- `hhi_active` or `hhi_aggressive`: concentration by active/taker volume.
- `hhi_passive_buy`, `hhi_passive_sell`.
- `hhi_active_buy`, `hhi_active_sell` or `hhi_aggressive_buy`, `hhi_aggressive_sell`.

## Interpretation Bands

| Value | Interpretation |
| --- | --- |
| `< 1500` | Lower concentration |
| `1500-2500` | Moderate concentration |
| `> 2500` | High concentration |

These are broad market-structure bands, not trading rules.

## Output Patterns

- Produce `.csv` or normalized JSON tables when the user wants data handoff to another tool.
- Create a simple self-contained HTML chart when the user asks for browser output.
- Use pandas or Matplotlib plotting when the user asks for notebook/script output.
- Use the project's existing charting stack when working inside an app.

Let the requested analysis decide whether to show a time series, market snapshot, banded table, or another view.
