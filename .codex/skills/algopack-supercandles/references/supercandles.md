# Direct SuperCandles Reference

## Scope and Cadence

SuperCandles are calculated 5-minute metrics based on trades, order-flow events, and order-book snapshots.

- `tradestats`: OHLC, VWAP, volume, trade counts, buy/sell split, imbalance.
- `orderstats`: placed and cancelled orders, order volumes/values, order-flow VWAP.
- `obstats`: visible liquidity, spreads, levels, book VWAP, imbalance.

Markets are `eq`, `fo`, and `fx`. Local docs describe history from 2020 and publication several seconds after each 5-minute interval closes.

`Promo` includes SuperCandles. `Стартовый / Starter` free-token availability is planned at `T - 1 day`; if users see `403`, empty data, non-JSON responses, or missing rows, verify current entitlement and current DataShop terms before promising access.

## Endpoint Map

Use `https://apim.moex.com/iss` with a bearer token.

| Market | All instruments | One instrument |
| --- | --- | --- |
| EQ TradeStats | `/iss/datashop/algopack/eq/tradestats.json` | `/iss/datashop/algopack/eq/tradestats/{ticker}.json` |
| EQ OrderStats | `/iss/datashop/algopack/eq/orderstats.json` | `/iss/datashop/algopack/eq/orderstats/{ticker}.json` |
| EQ OBStats | `/iss/datashop/algopack/eq/obstats.json` | `/iss/datashop/algopack/eq/obstats/{ticker}.json` |
| FO TradeStats | `/iss/datashop/algopack/fo/tradestats.json` | `/iss/datashop/algopack/fo/tradestats/{ticker}.json` |
| FO OrderStats | `/iss/datashop/algopack/fo/orderstats.json` | `/iss/datashop/algopack/fo/orderstats/{ticker}.json` |
| FO OBStats | `/iss/datashop/algopack/fo/obstats.json` | `/iss/datashop/algopack/fo/obstats/{ticker}.json` |
| FX TradeStats | `/iss/datashop/algopack/fx/tradestats.json` | `/iss/datashop/algopack/fx/tradestats/{ticker}.json` |
| FX OrderStats | `/iss/datashop/algopack/fx/orderstats.json` | `/iss/datashop/algopack/fx/orderstats/{ticker}.json` |
| FX OBStats | `/iss/datashop/algopack/fx/obstats.json` | `/iss/datashop/algopack/fx/obstats/{ticker}.json` |

Parameters:

- All instruments: `date=YYYY-MM-DD`, optional `latest=1`, `start=N`, `limit=N`.
- One instrument: `from=YYYY-MM-DD`, `till=YYYY-MM-DD`, optional `latest=1`, `start=N`, `limit=N`.

## curl Examples

Latest EQ order-book metrics:

```bash
curl -L "https://apim.moex.com/iss/datashop/algopack/eq/obstats.json?date=2025-01-10&latest=1" \
  -H "Authorization: Bearer ${APIKEY}"
```

SBER TradeStats as CSV:

```bash
curl -L "https://apim.moex.com/iss/datashop/algopack/eq/tradestats/SBER.csv?from=2025-01-01&till=2025-01-31" \
  -H "Authorization: Bearer ${APIKEY}"
```

SiH5 futures OBStats:

```bash
curl -L "https://apim.moex.com/iss/datashop/algopack/fo/obstats/SiH5.json?from=2025-01-10&till=2025-01-10&start=0" \
  -H "Authorization: Bearer ${APIKEY}"
```

## Response Block

SuperCandles JSON usually stores rows in the `data` block. Normalize `columns` plus `data` into rows before filtering, writing tables, or charting:

```javascript
const block = payload.data;
const rows = block.data.map((row) =>
  Object.fromEntries(block.columns.map((name, index) => [name.toLowerCase(), row[index]]))
);
```

If the user needs a table, rename `secid` to `ticker` for readability.

## Pagination

Raw endpoints can cap rows per response. Keep requesting with `start` until the `data` block is empty, and advance by the returned row count:

```text
start = 0
while true:
    request with start
    rows = normalized data block rows
    stop when rows is empty
    start = start + len(rows)
```

Local notes mention a 1000-row raw SuperCandles limit in some contexts, so pagination is required for full day/range pulls. Keep `limit` route-dependent where supported; do not promise one universal maximum.

## TradeStats Fields

- `tradedate`, `tradetime`, `secid`, `systime`.
- `pr_open`, `pr_high`, `pr_low`, `pr_close`: 5-minute OHLC.
- `pr_vwap`: volume-weighted average price, approximately `val / vol`.
- `pr_vwap_b`, `pr_vwap_s`: buyer-initiated and seller-initiated VWAP.
- `pr_change`: percent change from open to close.
- `pr_std`: price standard deviation.
- `trades`, `trades_b`, `trades_s`: total, buy, and sell trade counts.
- `vol`, `vol_b`, `vol_s`: total, buy, and sell volume.
- `val`, `val_b`, `val_s`: total, buy, and sell value.
- `disb`: buy/sell imbalance. Positive means more buyer-initiated activity; negative means more seller-initiated activity.

FO additions can include `asset_code`, `im`, `oi_open`, `oi_high`, `oi_low`, `oi_close`, and second-offset price-event fields. FX volume fields are currency-specific and do not include futures margin/open-interest fields.

## OrderStats Fields

- `put_orders_b`, `put_orders_s`, `put_orders`: placed orders.
- `put_vol_b`, `put_vol_s`, `put_vol`: placed order volume.
- `put_val_b`, `put_val_s`, `put_val`: placed order value.
- `put_vwap_b`, `put_vwap_s`: placed order VWAP.
- `cancel_orders_b`, `cancel_orders_s`, `cancel_orders`: cancelled orders.
- `cancel_vol_b`, `cancel_vol_s`, `cancel_vol`: cancelled volume.
- `cancel_val_b`, `cancel_val_s`, `cancel_val`: cancelled value.
- `cancel_vwap_b`, `cancel_vwap_s`: cancelled order VWAP.

High placed volume combined with high cancellation volume can indicate fast-changing displayed liquidity.

## OBStats Fields

EQ core:

- `spread_bbo`, `spread_lv10`, `spread_1mio`: spread measures.
- `levels_b`, `levels_s`: bid/ask level counts.
- `vol_b`, `vol_s`, `val_b`, `val_s`: visible book volume/value.
- `imbalance_vol_bbo`, `imbalance_val_bbo`: best-level imbalance.
- `imbalance_vol`, `imbalance_val`: full-book imbalance.
- `vwap_b`, `vwap_s`, `vwap_b_1mio`, `vwap_s_1mio`: book-side VWAP.

FO/FX routes can include `mid_price`, `micro_price`, `spread_l1..spread_l20`, cumulative depth fields such as `vol_b_l1..vol_b_l20`, and level-specific VWAP fields.

## Output Patterns

- Produce `.csv` or normalized JSON tables when the user wants data handoff to another tool.
- Create a simple self-contained HTML chart when the user asks for browser output.
- Use pandas or Matplotlib plotting when the user asks for notebook/script output.
- Use the project's existing charting stack when working inside an app.

Let the user's requested analysis decide which SuperCandles fields to keep. Avoid inventing VWAP, imbalance, churn, or liquidity panels unless the user asks for those metrics.
