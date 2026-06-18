# ISS Calendar Reference

Use direct ISS for trading calendars. Local docs state calendar methods support `from`, `till`, and pagination through `start`; some endpoints support `show_all_days=1` and `iss.only`. ALGOPACK `Promo` includes a machine-readable calendar, but do not imply every public ISS calendar route requires `Promo`. If a calendar URL returns `text/html` rather than JSON, verify the current route in the live ISS reference before relying on that endpoint.

## All Markets Off Days

Endpoint:

```text
/iss/calendars.json
```

Fields:

- `tradedate`: calendar date.
- `currency_workday`, `futures_workday`, `stock_workday`: `1` trading day, `0` non-trading day, `null` unknown.
- `currency_trade_session_date`, `futures_trade_session_date`, `stock_trade_session_date`.
- `currency_reason`, `futures_reason`, `stock_reason`: reason code.

Reason codes in local docs:

- `H`: holiday.
- `W`: weekend/special non-trading day.
- `N`: normal trading.
- `T`: transferred day.

Example:

```python
import requests
import pandas as pd

url = "https://iss.moex.com/iss/calendars.json"
params = {"from": "2025-01-01", "till": "2025-01-31", "show_all_days": 1}
payload = requests.get(url, params=params, timeout=30).json()
block = payload["off_days"]
calendar = pd.DataFrame(block["data"], columns=[c.lower() for c in block["columns"]])
```

## Stock Calendar

Endpoints:

- `/iss/calendars/stock.json`: stock off-days.
- `/iss/calendars/stock/static.json?iss.only=markets_classifier`: market classifier.
- `/iss/calendars/stock/static.json?iss.only=boards_classifier`: board classifier.
- `/iss/calendars/stock/securities/boards.json`: boards by security/date.
- `/iss/calendars/stock/session/settlecodes.json`: settlement codes.
- `/iss/calendars/stock/securities/suspended/details.json`: suspensions.
- `/iss/calendars/stock/securities/changes.json`: security attribute changes.
- `/iss/calendars/stock/session.json`: trading session schedule.

Useful stock session fields:

- `tradedate`, `tradingsession`, `boardid`, `secid`.
- `type`, `time_from`, `time_till`, `updatetime`.
- `tradingsession`: local docs list `0` morning, `1` main, `2` evening, `5` special day.

## Futures Calendar

Endpoints:

- `/iss/calendars/futures.json`: futures off-days.
- `/iss/calendars/futures/securities.json`: futures and options metadata.
- `/iss/calendars/futures/session.json`: session schedule.

`futures/securities.json` contains options and forts blocks. Futures fields include `secid`, `asset_code`, `shortname`, `exec_type`, `expiration_date`, `end_date`, `weekend_session`.

## Currency Calendar

Endpoints:

- `/iss/calendars/currency.json`: currency off-days and settlement data.
- `/iss/calendars/currency/session.json`: currency session/security data.
- `/iss/calendars/currency/securities.json`: suspended instruments and settlement shifts.
- `/iss/calendars/currency/changes.json`: changes.

Currency fields include `tradedate`, `secid`, `boardid`, `currencyid`, `faceunit`, `prevdate`, `settledate`, `updatetime`.

## Pagination Helper

```python
def calendar_pages(url, block_name, params=None):
    import pandas as pd
    import requests

    params = dict(params or {})
    start = int(params.get("start", 0))
    frames = []
    while True:
        params["start"] = start
        payload = requests.get(url, params=params, timeout=30).json()
        block = payload[block_name]
        rows = block["data"]
        if not rows:
            break
        frames.append(pd.DataFrame(rows, columns=[c.lower() for c in block["columns"]]))
        start += len(rows)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
```
