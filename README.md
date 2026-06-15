# Algo Trading

Local market backtesting and paper trading.

Safety boundary: this project uses read-only public market data only. It does not accept exchange API keys and cannot place real orders.

## Usage

Run the full test suite:

```bash
python3 -m unittest discover -v
```

Start the local browser UI:

```bash
python3 -m algo_trading.ui --port 8765
```

Then open `http://127.0.0.1:8765`. The UI binds to localhost by default, uses read-only public market data, and cannot place real orders.

The frontend is a Vue 3 control panel with direct URLs:

- `http://127.0.0.1:8765/backtest`
- `http://127.0.0.1:8765/paper`
- `http://127.0.0.1:8765/live`
- `http://127.0.0.1:8765/chart`
- `http://127.0.0.1:8765/runs`
- `http://127.0.0.1:8765/lab`

The `Live` / `Chart` view uses a TradingView-style dark control panel with TradingView Lightweight Charts. Crypto spot candles come from Binance public REST. The S&P 500 futures option uses delayed Yahoo Finance CME futures candles for `ES=F`. It overlays strategy long/short markers plus simulated paper entry/exit markers from local `runs/paper/` output. Choose `All strategies` in the live strategy selector to draw every strategy's long/short markers on one chart with strategy-prefixed labels.

The `Strategy Lab` view ranks strategy and preset combinations across selected symbols using simulated backtests. Treat this as research support, not a profit guarantee.

Build the Vue frontend manually when changing frontend source:

```bash
npm ci
npm run frontend:build
```

The UI strategy dropdown supports:

- `ema-rsi`: fast/slow EMA crossover filtered by RSI.
- `macd`: MACD line crossing its signal line.
- `bollinger-reversion`: mean reversion after a Bollinger band reclaim/reject.
- `donchian-breakout`: breakout above or below the previous Donchian channel.
- `rsi-reversal`: RSI leaving overbought or oversold zones.
- `supertrend`: ATR SuperTrend-style trend flip.
- `vwap-reversion`: rolling VWAP reclaim/reject mean reversion.
- `stoch-rsi-reversal`: stochastic RSI leaving extreme levels.
- `ema-ribbon`: EMA ribbon alignment trend following.
- `momentum-scalping`: short-term momentum with RSI and MACD confirmation.

Presets are `custom`, `conservative`, `balanced`, and `aggressive`. Presets replace the related risk and indicator values with deterministic settings that are written into each run's `config.json`.

## Docker And Make

Run all local checks:

```bash
make check
```

Build and run the UI in Docker:

```bash
make docker-run
```

Then open `http://127.0.0.1:8765`. If that port is already in use, run `make docker-run PORT=8766` and open `http://127.0.0.1:8766`.

Run with Docker Compose:

```bash
make compose-up
```

Both Docker paths mount local `runs/` into the container so backtest and paper-trading outputs persist on the host.

List the most-traded Binance USDT crypto pairs by current 24h quote volume:

```bash
python3 -m algo_trading.cli symbols --top 10
```

The ranking is fetched live from Binance public market data. Stablecoin, fiat, and tokenized-metal bases such as `USDC`, `FDUSD`, `USD1`, and `XAUT` are excluded so the list focuses on crypto assets.

Run a live read-only single-symbol backtest:

```bash
python3 -m algo_trading.cli backtest --symbol BTCUSDT --interval 1h --limit 300
```

Run a specific strategy and preset:

```bash
python3 -m algo_trading.cli backtest --symbol BTCUSDT --strategy macd --preset aggressive --interval 1h --limit 300
```

Run a batch backtest over the current top traded USDT crypto pairs:

```bash
python3 -m algo_trading.cli backtest --symbols top --top 5 --interval 1h --limit 300
```

Live backtests retry transient market-data failures twice per symbol by default. Tune this when Binance is slow:

```bash
python3 -m algo_trading.cli backtest --symbols top --top 5 --market-data-retries 4 --retry-delay 1
```

Run a batch backtest over an explicit symbol list:

```bash
python3 -m algo_trading.cli backtest --symbols BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT --interval 1h --limit 300
```

Run a bounded paper-trading session:

```bash
python3 -m algo_trading.cli paper --symbol BTCUSDT --interval 1m --iterations 3
```

Paper trading is intentionally single-symbol in v1. Use separate bounded sessions for separate symbols until a real portfolio simulator is added.

Use `--allowed-side long-only` or `--allowed-side short-only` to focus a run on one side. The default is `both`.

Strategy-specific CLI options include `--macd-signal`, `--bollinger-period`, `--bollinger-stddev`, `--donchian-period`, and `--rsi-midline`. All strategies still use read-only public market data and only write simulated backtest or paper-trading outputs.

Outputs are written under `runs/backtests/<timestamp>/` or `runs/paper/<timestamp>/` and include `config.json`, `trades.csv`, `equity.csv`, and `summary.json`.
