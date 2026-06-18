# MOEXAlgo FUTOI Reference

## Imports and Auth

```bash
python -m pip install "moexalgo[dataframe]" python-dotenv
```

```python
import os
from dotenv import load_dotenv
from moexalgo import session, Market, Ticker

load_dotenv()
session.TOKEN = os.environ["APIKEY"]
```

`Стартовый / Starter` free-token access has FUTOI delayed at `T - 15 days`; `Promo` has fuller/online access, subject to current entitlement. FUTOI is futures-only; it is not equities, FX, options, individual trader data, or exact single-contract FIZ/YUR positioning.

## Method Signatures

```text
Market("FO").futoi(date=None, native=False)
Ticker(...).futoi(start=None, end=None, native=False)
```

Pass explicit dates. In the current repo code, omitting `date` on market methods or `start`/`end` on ticker methods reaches `prepare_from_till_dates(...)` and raises instead of silently using today.

FUTOI is implemented only for the futures market. `Ticker(...).futoi(...)` resolves the ticker to the FUTOI identifier used by the endpoint. Perpetual futures such as `USDRUBF`, `EURRUBF`, `CNYRUBF`, `IMOEXF`, `GLDRUBF`, `SBERF`, and `GAZPF` are handled specially by the library.

## Library Parameter Caveats

FUTOI library methods do not expose `latest` or `offset`. For larger spans, loop by explicit date/range at the library level. Use the direct FUTOI REST endpoint when the user needs raw endpoint controls such as `latest`, `start`, or route-specific `limit`.

## Examples

All futures for one date:

```python
fo = Market("FO")
df = fo.futoi(date="2025-01-10")
```

One instrument range:

```python
si = Ticker("SiH5")
df = si.futoi(start="2025-01-10", end="2025-01-10")
```

Use DataFrames by default. If the user explicitly asks for iterators or dictionaries, mention `native=True` as the escape hatch.

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

- FUTOI aggregates active contract series by underlying/instrument.
- A participant's positions are netted within one contract first.
- A participant can count in both long and short groups if they are long one contract and short another.
- Zero net positions are excluded from participant counts.
- Do not infer individual identities or exact single-contract FIZ/YUR splits from aggregate rows.

## DataFrame Workflows

Build the table or chart from the fields the user requested. Start by creating a timestamp column when the output needs ordering or plotting:

```python
df = Market("FO").futoi(date="2025-01-10")
df["datetime"] = df["tradedate"].astype(str) + " " + df["tradetime"].astype(str)
```

Select requested fields for handoff:

```python
df = Ticker("SiH5").futoi(start="2025-01-10", end="2025-01-10")
table = df[["tradedate", "tradetime", "ticker", "clgroup", "pos", "pos_long", "pos_short"]]
```

Use pandas groupbys or pivots only when the user asks for an aggregate:

```python
latest_time = df["tradetime"].max()
latest = df[df["tradetime"] == latest_time]
by_group = latest.groupby(["ticker", "clgroup"], as_index=False)["pos"].sum()
```

Guard against division by zero and missing rows when deriving ratios.
