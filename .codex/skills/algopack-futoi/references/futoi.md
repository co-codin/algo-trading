# Direct FUTOI Reference

## Scope

FUTOI is futures open interest by participant group. Local docs describe 5-minute snapshots, history from 2020, and FIZ/YUR segmentation for the futures market. It is not equities, FX, options, individual trader data, or exact single-contract FIZ/YUR positioning. `Стартовый / Starter` free-token access has FUTOI delayed at `T - 15 days`; `Promo` has fuller/online access, subject to current entitlement.

## Endpoints

Use `https://apim.moex.com/iss` with a bearer token for authenticated access.

```text
/iss/analyticalproducts/futoi/securities.json?date=YYYY-MM-DD
/iss/analyticalproducts/futoi/securities/{ticker}.json?from=YYYY-MM-DD&till=YYYY-MM-DD
```

Examples:

```bash
curl -L "https://apim.moex.com/iss/analyticalproducts/futoi/securities.json?date=2025-01-10" \
  -H "Authorization: Bearer ${APIKEY}"
```

```bash
curl -L "https://apim.moex.com/iss/analyticalproducts/futoi/securities/Si.json?from=2025-01-10&till=2025-01-10" \
  -H "Authorization: Bearer ${APIKEY}"
```

For chart files, request `.csv` instead of `.json`.

## Response Block

FUTOI JSON uses the `futoi` block. Normalize `columns` plus `data` into rows before filtering, writing tables, or charting:

```javascript
const block = payload.futoi;
const rows = block.data.map((row) =>
  Object.fromEntries(block.columns.map((name, index) => [name.toLowerCase(), row[index]]))
);
```

## Pagination

Use `start` if a FUTOI route caps rows for the requested range. Continue until the `futoi` block returns no rows, and advance `start` by the returned row count:

```text
start = 0
while true:
    request with start
    rows = normalized futoi block rows
    stop when rows is empty
    start = start + len(rows)
```

Keep `limit` route-dependent where supported; do not promise one universal maximum.

## Fields

| Field | Meaning |
| --- | --- |
| `sess_id` | Trading session id |
| `seqnum` | Technical sequence number |
| `tradedate` | Date |
| `trade_session_date` | Trading-session date when present |
| `tradetime` | Snapshot time |
| `ticker` | Underlying or instrument code |
| `clgroup` | `FIZ` for individuals, `YUR` for legal entities |
| `pos` | Net position, long minus short |
| `pos_long` | Gross long open positions in contracts |
| `pos_short` | Gross short open positions in contracts; raw values can be negative |
| `pos_long_num` | Count of participants with long positions |
| `pos_short_num` | Count of participants with short positions |
| `systime` | Load/system time when present |

## Aggregation Caveats

- FUTOI aggregates active contract series by underlying/instrument. A row for `Si` can combine positions across active Si contracts.
- Positions are netted within one trader and one contract before aggregation.
- One participant can count in both long and short participant counts if they are long one contract and short another.
- Zero net positions are excluded from participant counts.
- Rows do not identify individual traders and should not be used to infer individual behavior.

## Output Patterns

- Produce `.csv` or normalized JSON tables when the user wants data handoff to another tool.
- Create a simple self-contained HTML chart when the user asks for browser output.
- Use pandas or Matplotlib plotting when the user asks for notebook/script output.
- Use the project's existing charting stack when working inside an app.

Let the user's requested analysis decide whether to show net position, gross long/short, participant counts, or another field combination. Guard against division by zero and missing rows when deriving ratios.
