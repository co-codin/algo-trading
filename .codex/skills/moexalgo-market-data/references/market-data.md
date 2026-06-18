# MOEXAlgo Market Data Reference

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

Set `APIKEY=...` in a local `.env` file and keep that file out of source control. When `session.TOKEN` is set, the library uses `https://apim.moex.com/iss` and adds `Authorization: Bearer ...` for plan-entitled access. `Стартовый / Starter` free-token access includes 15-minute delayed candles and trades; `Promo` includes online order books, candles, and trades. Without a token, the library uses public ISS, which can be delayed or limited.

## Markets and Boards

| Alias examples | Engine/market | Default board | Notes |
| --- | --- | --- | --- |
| `EQ`, `eq`, `shares`, `stocks`, `equity` | `stock/shares` | `TQBR` | Shares |
| `FO`, `fo`, `futures`, `forts` | `futures/forts` | `RFUD` | Futures, includes FUTOI support |
| `FX`, `fx`, `currency`, `selt` | `currency/selt` | `CETS` | Currency |
| `index` | `stock/index` | `SNDX` | Basic market data |
| `bonds` | `stock/bonds` | `TQOB` | Basic market data |
| `options` | `futures/options` | `ROPD` | Basic market data |

Board override:

```python
eq_tqpi = Market("EQ", board="TQPI")
instrument = Ticker("SOME_TICKER", board="TQPI")
```

Use board overrides only when the default board misses the instrument or the date range spans a board migration.

## Market Methods

```python
eq = Market("EQ")

tickers = eq.tickers("ticker", "shortname", "minstep")
all_ticker_fields = eq.tickers("*")
quotes = eq.marketdata("ticker", "last", "bid", "offer", "updatetime")
all_quote_fields = eq.marketdata("*")
trades = eq.trades()
recent_candles = eq.candles()
```

`Market.candles()` returns recent calculated 1-minute candles from current-day trades. It is not a historical candle range method.

## Ticker Methods

```python
sber = Ticker("SBER")

info = sber.info("ticker", "title", "market", "engine", "decimals")
all_info = sber.info("*")
trades = sber.trades()
latest_trade = sber.trades(latest=True)
book = sber.orderbook()
candles = sber.candles(start="2025-01-01", end="2025-01-31", period="1h")
latest_candle = sber.candles(start="2025-01-01", end="2025-01-31", period="1h", latest=True)
```

Common signatures:

```text
Market(name: str, board: str = None)
Ticker(name: str, board: str = None)
Market.tickers(*fields: str, native: bool = False)
Market.marketdata(*fields: str, native: bool = False)
Ticker.info(*fields: str, native: bool = False)
Ticker.candles(start, end, period=None, offset=0, latest=False, native=False)
Ticker.trades(tradeno_or_recno=None, offset=0, latest=False, native=False)
Ticker.orderbook(native=False)
```

Futures ticker trades accept the first argument as `recno`; stock and currency ticker trades use `tradeno`.

## Securities vs Marketdata Blocks

- `Market.tickers(...)` reads the ISS `securities` block. Use it for metadata such as `minstep`, `lotsize`, `stepprice`, `shortname`, and `sectype`.
- `Market.marketdata(...)` reads the ISS `marketdata` block. Use it for quote and session fields such as `last`, `bid`, `offer`, `voltoday`, and `updatetime`.
- `tickers("*")` means all `securities` fields. `marketdata("*")` means all `marketdata` fields.
- Custom fields do not cross blocks. Fetch metadata and quotes separately, then join or filter the DataFrames in pandas.

Both methods normalize raw `SECID` to `ticker` and `BOARDID` to `board`. Even when requesting a small field list, the returned DataFrame can still include `ticker` and `board` if those source columns are present.

Example matching the repo test style. `minstep` and `stepprice` come from the `securities` block, while `last` comes from the `marketdata` block, so this must be two library calls:

```python
market = Market("futures")
securities = market.tickers("minstep", "stepprice")
market_data = market.marketdata("last")

security = securities[securities["ticker"] == "GDM6"]
quote = market_data[market_data["ticker"] == "GDM6"]
```

## Candle Periods

Native ISS intervals:

- Strings: `"1min"`, `"10min"`, `"1h"`, `"1D"`, `"1W"`, `"1M"`.
- Numbers: `1`, `10`, `60`, `24`, `7`, `31`.

Library resampled intervals:

- `"5min"`, `"15min"`, `"20min"`, `"30min"`, `"2h"`, `"3h"`, `"6h"`, `"12h"`, `"5D"`, `"10D"`, `"2W"`, `"4W"`.

Use explicit `start` and `end` for historical candles.

## Pagination and Larger Ranges

Use library parameters, not raw REST parameters. `Ticker.candles(...)` and `Ticker.trades(...)` expose `offset`; do not pass raw ISS `start` to library methods. For larger historical pulls, loop by date/range or call with increasing `offset` where the method supports it. Use direct ISS/REST only when the user needs raw endpoint pagination controls.

## Important Fields

Ticker metadata:

- `ticker`, `shortname`, `lotsize`, `decimals`, `minstep`, `isin`, `listlevel`.
- Futures also commonly expose `sectype`, `assetcode`, `lotvolume`, `initialmargin`, `lasttradedate`, and fields such as `stepprice` when requested.

Marketdata:

- `bid`, `offer`, `last`, `open`, `high`, `low`, `waprice`, `numtrades`, `voltoday`, `valtoday`, `updatetime`, `systime`.

Candles:

- `open`, `high`, `low`, `close`, `volume`, `value`, `begin`, `end`.

Trades:

- `tradeno` or `recno`, `tradetime`, `price`, `quantity`, `value`, `buysell`, `systime`.

Order book:

- `buysell`, `price`, `quantity`, `seqnum`, `updatetime`.

## DataFrame Examples

Join metadata and quotes:

```python
eq = Market("EQ")
tickers = eq.tickers("ticker", "shortname", "minstep")
quotes = eq.marketdata("ticker", "last", "bid", "offer", "updatetime")
snapshot = tickers.merge(quotes, on="ticker", how="left")
```

Futures contract value from quote and tick value:

```python
market = Market("futures")
secid = "GDM6"
securities = market.tickers("minstep", "stepprice")
market_data = market.marketdata("last")

security = securities[securities["ticker"] == secid]
quote = market_data[market_data["ticker"] == secid]
contract_value = (quote["last"].iloc[0] / security["minstep"].iloc[0]) * security["stepprice"].iloc[0]
```

Aggregate hourly volume to daily volume:

```python
sber = Ticker("SBER")
candles = sber.candles(start="2025-01-01", end="2025-01-31", period="1h")
candles["begin"] = candles["begin"].astype("datetime64[ns]")
daily_volume = candles.groupby(candles["begin"].dt.date)["volume"].sum()
```

Use DataFrames by default. If the user explicitly asks for iterators or dictionaries, mention `native=True` as the escape hatch.

## Edge Cases

- Missing data can mean market holiday, unsupported board, delayed publication, or insufficient entitlement.
- Some indexes or boards may have limited candle intervals for specific dates. Check metadata and try the raw ISS route when the library default does not resolve.
- `Ticker(...)` resolves through ISS metadata and can fail if the ticker is delisted or non-primary on the requested board. Pass `board=` explicitly when needed.
