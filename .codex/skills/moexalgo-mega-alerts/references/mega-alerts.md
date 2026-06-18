# MOEXAlgo Mega Alerts Reference

## Imports and Auth

```bash
python -m pip install "moexalgo[dataframe]" python-dotenv
```

```python
import json
import os
from dotenv import load_dotenv
from moexalgo import session, Market, Ticker

load_dotenv()
session.TOKEN = os.environ["APIKEY"]
```

`Promo` includes Mega Alerts. `Стартовый / Starter` free-token availability is planned at `T - 1 day`; if users see `403`, empty data, non-JSON responses, or missing rows, verify current entitlement and current DataShop terms before promising access. Local endpoint lists document EQ and FO.

## Method Signatures

```text
Market(...).alerts(date=None, latest=None, offset=None, native=False)
Ticker(...).alerts(start=None, end=None, latest=None, offset=None, native=False)
```

Pass explicit dates. In the current repo code, omitting `date` on market methods or `start`/`end` on ticker methods reaches `prepare_from_till_dates(...)` and raises instead of silently using today. Use `Market("EQ")` or `Market("FO")` unless current data proves another market is populated and entitled.

## Pagination and Larger Ranges

Use library parameters, not raw REST parameters. Mega Alerts library methods use `offset`, not `start`. Market-wide methods internally page up to the library's market call limit; ticker methods use a smaller ticker call limit. For larger ranges, loop by date/range or call with increasing `offset` where supported. Use direct REST only when the user needs raw endpoint controls such as route-specific `start` or `limit`.

## Examples

Market-wide:

```python
alerts = Market("EQ").alerts(date="2025-01-10")
```

Ticker range:

```python
sber_alerts = Ticker("SBER").alerts(start="2025-01-01", end="2025-03-30")
```

Latest rows:

```python
latest = Market("EQ").alerts(date="2025-01-10", latest=True)
```

## Fields

| Field | Meaning |
| --- | --- |
| `tradedate` | Date |
| `tradetime` | Alert time |
| `ticker` | Instrument id normalized by the library |
| `alert_type` | Anomaly code |
| `threshold` | Trigger threshold |
| `value` | Observed value |
| `reference` | JSON string with historical post-alert statistics |
| `systime` | Load/system time |

## Alert Types

Volume:

- `vol_s_99_9_pctl`, `vol_b_99_9_pctl`, `vol_99_9_pctl`.
- `vol_s_max`, `vol_b_max`, `vol_max`.

Net volume:

- `net_vol_99_9_pctl-`, `net_vol_99_9_pctl+`.
- `net_vol_min`, `net_vol_max`.

Price change:

- `pr_change_99_9_pctl-`, `pr_change_99_9_pctl+`.
- `pr_change_min`, `pr_change_max`.

Price levels:

- `pr_high_max`, `pr_low_min`.

Suffix `+` means positive/upside direction. Suffix `-` means negative/downside direction.

## Reference Parsing

`reference` is historical context after similar alerts, not a forecast.

```python
import json
import pandas as pd

def parse_reference(value):
    if not value:
        return {}
    try:
        data = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data[0] if data else {}

refs = alerts["reference"].map(parse_reference)
ref_df = pd.json_normalize(refs)
combined = alerts.join(ref_df.add_prefix("ref_"))
```

For reference keys such as `m_5`, `m_15`, `m_30`, and `h_1`, local examples encode five values:

1. Average price change when price rose, percent.
2. Average price change when price fell, percent.
3. Count of rising cases.
4. Count of falling cases.
5. Average change across all observations, percent.

## DataFrame Analysis

Alert counts:

```python
counts = alerts.groupby(["ticker", "alert_type"]).size().sort_values(ascending=False)
```

Strongest absolute threshold breaches:

```python
alerts["breach_abs"] = (alerts["value"] - alerts["threshold"]).abs()
top = alerts.sort_values("breach_abs", ascending=False).head(20)
```

Timeline table:

```python
alerts["datetime"] = alerts["tradedate"].astype(str) + " " + alerts["tradetime"].astype(str)
timeline = alerts[["datetime", "ticker", "alert_type", "value", "threshold"]]
```

Daily alert pivot:

```python
daily = alerts.pivot_table(index="tradedate", columns="alert_type", values="ticker", aggfunc="count", fill_value=0)
```

Use DataFrames by default. If the user explicitly asks for iterators or dictionaries, mention `native=True` as the escape hatch.
