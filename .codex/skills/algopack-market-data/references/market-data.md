# Direct Market Data Reference

## Hosts

- Public ISS: `https://iss.moex.com/iss`
- Authenticated ALGOPACK gateway: `https://apim.moex.com/iss`

Use the authenticated host plus `Authorization: Bearer ${APIKEY}` for plan-entitled ALGOPACK data. `Стартовый / Starter` free-token access includes 15-minute delayed candles and trades; `Promo` includes online order books, candles, and trades. Public ISS routes may return delayed data, limited fields, or 403 for subscriber-only blocks.

## Market Routes

| Market | Engine | Market | Board | Common instruments |
| --- | --- | --- | --- | --- |
| EQ | `stock` | `shares` | `TQBR` | Shares |
| FO | `futures` | `forts` | `RFUD` | Futures |
| FX | `currency` | `selt` | `CETS` | Currency pairs |
| Index | `stock` | `index` | `SNDX` | Indexes |

Override the board only after checking instrument metadata. Instruments can move boards, and historical ranges may need more than one board route.

## Endpoint Map

All securities and quotes:

```text
/iss/engines/stock/markets/shares/boards/TQBR/securities.json
/iss/engines/futures/markets/forts/boards/RFUD/securities.json
/iss/engines/currency/markets/selt/boards/CETS/securities.json
```

One security and quote blocks:

```text
/iss/engines/stock/markets/shares/boards/TQBR/securities/{ticker}.json
```

Ticker time series and current state:

```text
/iss/engines/{engine}/markets/{market}/boards/{board}/securities/{ticker}/candles.json
/iss/engines/{engine}/markets/{market}/boards/{board}/securities/{ticker}/trades.json
/iss/engines/{engine}/markets/{market}/boards/{board}/securities/{ticker}/orderbook.json
```

Discovery:

```text
/iss/securities.json?q={query}
/iss/securities/{ticker}.json
/iss/engines/stock/markets/shares/securities.json
/iss/engines/futures/markets/forts/securities.json
/iss/engines/currency/markets/selt/securities.json
```

## Common Parameters

- `iss.only=securities|marketdata|candles|trades|orderbook`: return one block.
- `{block}.columns=SECID,SHORTNAME,MINSTEP`: reduce columns for a block.
- `from`, `till`: date or datetime range for candles and history-like endpoints.
- `interval`: candles interval, commonly `1`, `10`, `60`, `24`, `7`, `31`.
- `start`: pagination offset.
- `limit`: route-dependent row limit where supported.
- `tradeno`: start stock/FX trades after a trade number.
- `recno`: start futures trades after a record number.

## curl Examples

All share quotes with a smaller payload:

```bash
curl -L "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json?iss.only=marketdata&marketdata.columns=SECID,LAST,BID,OFFER,VOLTODAY,VALTODAY,UPDATETIME"
```

Hourly SBER candles as CSV:

```bash
curl -L "https://apim.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/SBER/candles.csv?from=2025-01-01&till=2025-01-31&interval=60" \
  -H "Authorization: Bearer ${APIKEY}"
```

Current futures order book:

```bash
curl -L "https://apim.moex.com/iss/engines/futures/markets/forts/boards/RFUD/securities/SiH5/orderbook.json" \
  -H "Authorization: Bearer ${APIKEY}"
```

## Response Parsing

ISS JSON blocks contain `columns` and `data` arrays. Normalize the target block into rows before filtering, joining, writing CSV/JSON, or charting:

```javascript
const block = payload.candles;
const rows = block.data.map((row) =>
  Object.fromEntries(block.columns.map((name, index) => [name.toLowerCase(), row[index]]))
);
```

For all-securities routes, read both `securities` and `marketdata` blocks when the answer needs metadata plus current quote values.

## Pagination

Use `start` for endpoints that cap rows. Continue until the target block returns no rows, and advance `start` by the returned row count rather than by a guessed fixed page size:

```text
start = 0
while true:
    request with start
    rows = normalized target block rows
    stop when rows is empty
    start = start + len(rows)
```

Keep `limit` route-dependent where supported; do not promise one universal maximum.

## Important Fields

Securities:

- `SECID`, `BOARDID`, `SHORTNAME`, `SECNAME`, `LOTSIZE`, `DECIMALS`, `MINSTEP`, `ISIN`, `LISTLEVEL`.

Marketdata:

- `BID`, `OFFER`: best bid and offer.
- `OPEN`, `HIGH`, `LOW`, `LAST`, `WAPRICE`: intraday prices.
- `NUMTRADES`, `VOLTODAY`, `VALTODAY`: current-day activity.
- `UPDATETIME`, `SYSTIME`: update timestamps.

Candles:

- `open`, `high`, `low`, `close`, `volume`, `value`, `begin`, `end`.

Trades:

- `TRADENO` or `RECNO`, `TRADETIME`, `PRICE`, `QUANTITY`, `VALUE`, `BUYSELL`.

Order book:

- `BUYSELL`, `PRICE`, `QUANTITY`, `SEQNUM`, `UPDATETIME`.

## Output Patterns

- Produce `.csv` or normalized JSON tables when the user wants data handoff to another tool.
- Create a simple self-contained HTML chart when the user asks for browser output.
- Use pandas or Matplotlib plotting when the user asks for notebook/script output.
- Use the project's existing charting stack when working inside an app.

Let the user's requested chart determine which fields to keep. Do not force a fixed visualization when a table or different chart answers the request better.
