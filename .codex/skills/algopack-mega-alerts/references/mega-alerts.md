# Direct Mega Alerts Reference

## Scope

Mega Alerts detect abnormal market activity from minute-level data. Local docs describe a rolling historical window for thresholds and documented endpoints for EQ and FO. Some prose mentions FX, but endpoint lists document EQ/FO; verify live rows and entitlement before promising FX coverage.

`Promo` includes Mega Alerts. `Стартовый / Starter` free-token availability is planned at `T - 1 day`; if users see `403`, empty data, non-JSON responses, or missing rows, verify current entitlement and current DataShop terms before promising access.

## Endpoints

Use `https://apim.moex.com/iss` with a bearer token.

```text
/iss/datashop/algopack/eq/alerts.json?date=YYYY-MM-DD
/iss/datashop/algopack/eq/alerts/{ticker}.json?from=YYYY-MM-DD&till=YYYY-MM-DD
/iss/datashop/algopack/fo/alerts.json?date=YYYY-MM-DD
/iss/datashop/algopack/fo/alerts/{ticker}.json?from=YYYY-MM-DD&till=YYYY-MM-DD
```

Examples:

```bash
curl -L "https://apim.moex.com/iss/datashop/algopack/eq/alerts.json?date=2025-01-10" \
  -H "Authorization: Bearer ${APIKEY}"
```

```bash
curl -L "https://apim.moex.com/iss/datashop/algopack/eq/alerts/SBER.csv?from=2025-01-01&till=2025-03-30" \
  -H "Authorization: Bearer ${APIKEY}"
```

## Response Block

Alerts JSON uses the `data` block. Normalize `columns` plus `data` into rows before filtering, writing tables, or charting:

```javascript
const block = payload.data;
const rows = block.data.map((row) =>
  Object.fromEntries(block.columns.map((name, index) => [name.toLowerCase(), row[index]]))
);
```

Raw ISS uses `secid`; user-facing tables can label it `ticker`.

## Pagination

Use `start` if an alerts route caps rows for the requested date or range. Continue until the `data` block returns no rows, and advance `start` by the returned row count:

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
| `tradetime` | Alert time |
| `secid` | Instrument id |
| `alert_type` | Anomaly code |
| `threshold` | Trigger threshold |
| `value` | Observed value |
| `reference` | JSON string with historical post-alert statistics |
| `systime` | Load/system time |

## Alert Types

Volume:

- `vol_s_99_9_pctl`: sell volume exceeded 99.9 percentile.
- `vol_b_99_9_pctl`: buy volume exceeded 99.9 percentile.
- `vol_99_9_pctl`: total volume exceeded 99.9 percentile.
- `vol_s_max`, `vol_b_max`, `vol_max`: recent historical max events.

Net volume:

- `net_vol_99_9_pctl-`: negative net volume exceeded threshold.
- `net_vol_99_9_pctl+`: positive net volume exceeded threshold.
- `net_vol_min`, `net_vol_max`: historical min/max net-volume events.

Price change:

- `pr_change_99_9_pctl-`: unusually large price decrease.
- `pr_change_99_9_pctl+`: unusually large price increase.
- `pr_change_min`, `pr_change_max`: historical min/max price-change events.

Price levels:

- `pr_high_max`: recent high reached.
- `pr_low_min`: recent low reached.

## Reference JSON

`reference` is a JSON string. Local examples show a list containing one object:

```json
[{
  "m_5": ["0.086", "-0.078", "25", "18", "0.017"],
  "m_15": ["0.134", "-0.101", "22", "21", "0.019"],
  "m_30": ["0.161", "-0.138", "22", "20", "0.018"],
  "h_1": ["0.215", "-0.146", "18", "26", "0.002"],
  "vol_b": 442006,
  "vol_s": 53039
}]
```

For `m_5`, `m_15`, `m_30`, and `h_1`, positions are:

1. Average price change when price rose, percent.
2. Average price change when price fell, percent.
3. Count of rising cases.
4. Count of falling cases.
5. Average change across all observations, percent.

Treat this as historical context after similar anomalies, not a forecast.

## Output Patterns

- Produce `.csv` or normalized JSON tables when the user wants data handoff to another tool.
- Create a simple self-contained HTML chart when the user asks for browser output.
- Use pandas or Matplotlib plotting when the user asks for notebook/script output.
- Use the project's existing charting stack when working inside an app.

Let the requested analysis decide whether to show a timeline, frequency table, threshold comparison, or another view.
