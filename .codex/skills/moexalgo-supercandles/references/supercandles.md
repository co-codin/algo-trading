# MOEXAlgo SuperCandles Reference

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

`Promo` includes SuperCandles. `Стартовый / Starter` free-token availability is planned at `T - 1 day`; if users see `403`, empty data, non-JSON responses, or missing rows, verify current entitlement and current DataShop terms before promising access.

## Method Choice

- `tradestats`: OHLC, VWAP, volume, trade count, buy/sell split, `disb`.
- `orderstats`: placed/cancelled orders, order volumes/values, order-flow VWAP.
- `obstats`: visible liquidity, spreads, levels, book VWAP, imbalance.

Markets: `Market("EQ")`, `Market("FO")`, `Market("FX")`.

## Method Signatures

Market-wide by date:

```text
Market(...).tradestats(date=None, latest=None, offset=None, native=False)
Market(...).orderstats(date=None, latest=None, offset=None, native=False)
Market(...).obstats(date=None, latest=None, offset=None, native=False)
```

One ticker over a date range:

```text
Ticker(...).tradestats(start=None, end=None, latest=None, offset=None, native=False)
Ticker(...).orderstats(start=None, end=None, latest=None, offset=None, native=False)
Ticker(...).obstats(start=None, end=None, latest=None, offset=None, native=False)
```

Pass explicit dates. In the current repo code, omitting `date` on market methods or `start`/`end` on ticker methods reaches `prepare_from_till_dates(...)` and raises instead of silently using today.

## Pagination and Larger Ranges

Use library parameters, not raw REST parameters. SuperCandles library methods use `offset`, not `start`. Market-wide methods internally page up to the library's market call limit; ticker methods use a smaller ticker call limit. For larger ranges, loop by date/range or call with increasing `offset` where supported. Use direct REST only when the user needs raw endpoint controls such as route-specific `start` or `limit`.

## Examples

Latest market-wide rows:

```python
eq = Market("EQ")
latest_book = eq.obstats(date="2025-01-10", latest=True)
latest_trades = eq.tradestats(date="2025-01-10", latest=True)
```

Ticker range:

```python
sber = Ticker("SBER")
df = sber.tradestats(start="2025-01-01", end="2025-01-31")
df["datetime"] = df["tradedate"].astype(str) + " " + df["tradetime"].astype(str)
```

Futures and FX:

```python
si = Ticker("SiH5")
si_book = si.obstats(start="2025-01-10", end="2025-01-10")

fx = Market("FX")
fx_orders = fx.orderstats(date="2025-01-10")
```

## TradeStats Fields

- `tradedate`, `tradetime`, `ticker`, `systime`.
- `pr_open`, `pr_high`, `pr_low`, `pr_close`: 5-minute OHLC.
- `pr_vwap`, `pr_vwap_b`, `pr_vwap_s`: total, buy, and sell VWAP.
- `pr_change`, `pr_std`: price change and volatility.
- `trades`, `trades_b`, `trades_s`: trade counts.
- `vol`, `vol_b`, `vol_s`: volume.
- `val`, `val_b`, `val_s`: value.
- `disb`: buy/sell imbalance, positive for buyer-initiated dominance.

FO rows can include `asset_code`, `im`, `oi_open`, `oi_high`, `oi_low`, and `oi_close`.

## OrderStats Fields

- `put_orders_b`, `put_orders_s`, `put_orders`: placed order counts.
- `put_vol_b`, `put_vol_s`, `put_vol`: placed volume.
- `put_val_b`, `put_val_s`, `put_val`: placed value.
- `put_vwap_b`, `put_vwap_s`: placed order VWAP.
- `cancel_orders_b`, `cancel_orders_s`, `cancel_orders`: cancelled order counts.
- `cancel_vol_b`, `cancel_vol_s`, `cancel_vol`: cancelled volume.
- `cancel_val_b`, `cancel_val_s`, `cancel_val`: cancelled value.
- `cancel_vwap_b`, `cancel_vwap_s`: cancelled order VWAP.

## OBStats Fields

EQ core:

- `spread_bbo`, `spread_lv10`, `spread_1mio`.
- `levels_b`, `levels_s`.
- `vol_b`, `vol_s`, `val_b`, `val_s`.
- `imbalance_vol_bbo`, `imbalance_val_bbo`, `imbalance_vol`, `imbalance_val`.
- `vwap_b`, `vwap_s`, `vwap_b_1mio`, `vwap_s_1mio`.

FO/FX rows can include `mid_price`, `micro_price`, level-specific spreads, cumulative depths, and level-specific VWAP fields.

## DataFrame Workflows

Build the table or chart from the fields the user requested. Start by creating a timestamp column when the output needs ordering or plotting:

```python
df = Ticker("SBER").tradestats(start="2025-01-01", end="2025-01-31")
df["datetime"] = df["tradedate"].astype(str) + " " + df["tradetime"].astype(str)
```

Select only the requested columns for handoff:

```python
table = df[["datetime", "ticker", "pr_open", "pr_high", "pr_low", "pr_close", "vol"]]
```

Use pandas aggregations only when the user asks for an aggregate:

```python
daily = df.groupby("tradedate", as_index=False).agg(vol=("vol", "sum"), trades=("trades", "sum"))
```

Use pandas or Matplotlib plotting for notebook/script output, and the project's existing charting stack inside an app. Avoid inventing VWAP, imbalance, churn, or liquidity panels unless the user asks for those metrics.
