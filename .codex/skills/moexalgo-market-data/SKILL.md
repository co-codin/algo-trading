---
name: moexalgo-market-data
description: Python moexalgo library workflows for Market and Ticker market data, .env session.TOKEN setup, pandas DataFrames, tickers metadata, marketdata quotes, info, candles, trades, orderbook, market aliases, board overrides, field selection, offset pagination, native-mode escape hatches, and basic EQ/FO/FX data analysis.
---

# MOEXAlgo Market Data

## Overview

Use this skill when the user wants the `moexalgo` Python package, pandas-style DataFrames, or `Market`/`Ticker` helpers for market data.

## Quick Start

```bash
python -m pip install "moexalgo[dataframe]" python-dotenv
```

```python
import os
from dotenv import load_dotenv
from moexalgo import session, Market, Ticker

load_dotenv()
session.TOKEN = os.environ["APIKEY"]

eq = Market("EQ")
tickers = eq.tickers("ticker", "shortname", "minstep")
quotes = eq.marketdata("ticker", "last", "bid", "offer", "updatetime")

sber = Ticker("SBER")
info = sber.info("ticker", "title", "market", "engine", "decimals")
candles = sber.candles(start="2025-01-01", end="2025-01-31", period="1h")
trades = sber.trades(latest=True)
book = sber.orderbook()
```

## Core Workflow

1. Install `moexalgo[dataframe]` and `python-dotenv` for DataFrame output and `.env` loading.
2. Store `APIKEY` in `.env`, call `load_dotenv()`, then set `session.TOKEN` from `os.environ["APIKEY"]` for plan-entitled access. `Стартовый / Starter` free-token access includes 15-minute delayed candles and trades; `Promo` includes online order books, candles, and trades.
3. Use `Market("EQ"|"FO"|"FX")` for market-wide rows and `Ticker("SBER")` for one instrument.
4. Keep metadata and quotes separate: `tickers(...)` reads the ISS `securities` block, while `marketdata(...)` reads the ISS `marketdata` block.
5. Pass explicit field names for compact DataFrames; use `tickers("*")` for all `securities` fields and `marketdata("*")` for all `marketdata` fields.
6. Use `board=...` only after metadata shows a non-default board is required.

## References

Read `references/market-data.md` for signatures, aliases, `securities` versus `marketdata` fields, candle periods, board caveats, pagination, and DataFrame examples.

## Boundary

For raw REST URLs, curl, ISS pagination mechanics, or non-Python integrations, use the direct ISS/API skills instead.
