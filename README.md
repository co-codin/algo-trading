# Algo Trading

Local market charting, breadth monitoring, and simulated strategy research.

Safety boundary: this project uses read-only market data only. It does not accept trading credentials and cannot place real orders.

## Usage

Run the full test suite:

```bash
python3 -m unittest discover -v
```

Install development tooling and enable the local pre-commit hook:

```bash
python3 -m pip install -e ".[dev]"
pre-commit install
```

Run the Python linter:

```bash
make lint
```

Start the local browser UI:

```bash
python3 -m algo_trading.ui --port 8765
```

Then open `http://127.0.0.1:8765`. The UI binds to localhost by default, uses read-only market data, and cannot place real orders.

The frontend is a Vue 3 control panel with direct URLs:

- `http://127.0.0.1:8765/live`
- `http://127.0.0.1:8765/chart`
- `http://127.0.0.1:8765/breadth`
- `http://127.0.0.1:8765/profile`
- `http://127.0.0.1:8765/admin`

The `Live` / `Chart` view uses a TradingView-style dark control panel with TradingView Lightweight Charts. Crypto spot candles come from Binance public REST, US futures and ETFs use delayed Yahoo Finance data, and Hong Kong stocks plus commodities use the same read-only market-data path. Choose `All strategies` to show consensus or capped individual strategy markers instead of flooding the chart with every raw marker. The page also supports saved local workspaces, data-health badges, browser alerts for new visible signals, and JSON snapshot export for the current chart state.

The `Breadth` page shows cached market-breadth history, including the official Cboe total put/call ratio at the top. `Profile` is available for signed-in users. `Admin` is visible only when the signed-in user's `is_admin` flag is true.

Project playbooks for repeated work live in [`SKILLS.md`](SKILLS.md) and [`docs/skills/`](docs/skills/): live chart UX, market-data integrations, auth/admin operations, and safe refactoring.

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
- `keltner-breakout`: breakout through ATR-width Keltner channels.
- `ema-pullback`: trend continuation after price reclaims the fast EMA.
- `atr-trailing-trend`: ATR trailing trend direction flips.
- `cci-reversal`: CCI leaving overbought or oversold extremes.
- `williams-r-reversal`: Williams %R leaving overbought or oversold extremes.
- `bollinger-squeeze-release`: Bollinger band squeeze expansion breakout.
- `obv-trend`: OBV confirmation aligned with price trend.
- `volume-breakout`: Donchian breakout confirmed by above-average volume.
- `vwap-trend-continuation`: VWAP reclaim with EMA trend confirmation.
- `sma-crossover`: simple moving average crossover baseline using the fast/slow period settings.
- `adx-trend`: ADX trend strength with directional movement confirmation.
- `ichimoku-breakout`: Ichimoku cloud breakout with conversion/base confirmation.
- `mfi-reversal`: Money Flow Index reversal after leaving extreme levels.
- `parabolic-sar`: Parabolic SAR trend flip.
- `zscore-reversion`: rolling z-score mean reversion from statistical extremes.
- `time-series-momentum`: lookback-return trend following from the quant idea generator.
- `volatility-breakout`: quant-style close versus the prior Donchian range; level-hold, not a new channel formula. Overlaps `donchian-breakout` on the same period.
- `rsi-mean-reversion`: RSI level mean reversion while oversold or overbought. Distinct from `rsi-reversal`, which waits for RSI to leave those extremes.
- `breadth-confirmation`: average breadth confirmation; stays flat when breadth bars are unavailable.
- `combined-signals`: configurable confirmation ensemble over selected member strategies. Optional combo-level filters: volatility-regime weighting, higher-timeframe confirmation, intermarket relative-strength soft veto, and New York session weights. Conf % remains agree/N of members; filtered votes simply do not count as agree.

Presets are `custom`, `conservative`, `balanced`, and `aggressive`. Presets replace the related risk and indicator values with deterministic settings that are written into each run's `config.json`.

## Docker And Make

Run all local checks:

```bash
make check
```

Run all configured pre-commit hooks manually:

```bash
pre-commit run --all-files
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

Both Docker paths mount local `runs/` for command-line simulation outputs and `logs/` for persistent runtime error logs. Docker Compose also mounts `historical_data/` so market-breadth and candle CSV history persists across rebuilds.

FastAPI unhandled exceptions are appended to `logs/app.log`, and RQ worker errors are appended to `logs/worker.log`. Docker stdout/stderr remains available through `docker compose logs`; generated `logs/` files are ignored by git.

Runtime secrets belong in local `.env`, which is ignored by git. Use `.env.example` as the tracked template. Leave `DATABASE_URL` unset for local in-memory auth unless you are intentionally running Postgres outside Docker. Leave `REDIS_URL` unset for local in-process background maintenance unless you are also running Redis and `python -m algo_trading.worker`.

Live candle CSVs are retained for the latest 1095 days. The web app schedules refresh jobs for existing candle CSVs in `historical_data/` every hour (`HISTORICAL_CSV_REFRESH_SECONDS=3600`) and schedules a daily prune (`HISTORICAL_CSV_PRUNE_SECONDS=86400`) so rows older than three years are removed. With Docker Compose, those jobs are stored in Redis and executed by the `worker` service. Without `REDIS_URL`, local runs execute the same maintenance in the FastAPI process.

The `US Market Breadth` page saves Barchart market-breadth history under `historical_data/breadth/<symbol>.csv`. Saved CSVs are reused for one hour before the app refreshes that symbol from Barchart and rewrites a deduped, date-sorted file containing only the latest 365 days. The exception is `historical_data/breadth/CPC.csv`: it stores the full official Cboe total put/call ratio history from Cboe's ratio archives plus the post-2019 daily market-statistics page, and it is not pruned to one year.

List the most-traded Binance USDT crypto pairs by current 24h quote volume:

```bash
python3 -m algo_trading.cli symbols --top 10
```

The ranking is fetched live from Binance public market data. Stablecoin, fiat, and tokenized-metal bases such as `USDC`, `FDUSD`, `USD1`, and `XAUT` are excluded so the list focuses on crypto assets.

Export recent Binance historical candles to CSV:

```bash
python3 -m algo_trading.cli candles --symbol BTCUSDT --interval 1h --limit 1000 --output historical_data/BTCUSDT-1h.csv
```

Export the last 365 days by paginating Binance candles into the same CSV schema:

```bash
python3 -m algo_trading.cli candles --symbol BTCUSDT --interval 1h --days 365 --limit 1000 --output historical_data/BTCUSDT-1h-365d.csv
```

Export the last 365 days of delayed Yahoo Finance CME index futures candles:

```bash
python3 -m algo_trading.cli candles --market cme_futures --symbol SP500 --interval 1d --days 365 --limit 1000 --output historical_data/SP500-1d-365d.csv
python3 -m algo_trading.cli candles --market cme_futures --symbol NASDAQ --interval 1d --days 365 --limit 1000 --output historical_data/NASDAQ-1d-365d.csv
```

Export delayed Yahoo Finance Hong Kong stock candles:

```bash
python3 -m algo_trading.cli candles --market hong_kong_stocks --symbol 9988.HK --interval 1d --days 365 --limit 1000 --output historical_data/hong_kong_stocks/9988.HK-1d-365d.csv
python3 -m algo_trading.cli candles --market hong_kong_stocks --symbol 9888.HK --interval 1d --days 365 --limit 1000 --output historical_data/hong_kong_stocks/9888.HK-1d-365d.csv
```

The candle CSV columns are `open_time,open,high,low,close,volume`. The same file can be reused as a backtest fixture with `--fixture`.

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

Strategy-specific CLI options include the shared EMA/RSI knobs plus MACD, Bollinger, Donchian, ATR/SuperTrend, VWAP, stochastic RSI, EMA ribbon, momentum, Keltner, CCI, Williams %R, volume, squeeze-threshold, and combination-signal settings. For `combined-signals`, use `--combo-strategies`, `--combo-entry-confirmations`, `--combo-exit-confirmations`, `--combo-lookback`, and the optional `--combo-regime-*`, `--combo-mtf-*`, `--combo-rs-*`, and `--combo-session-*` knobs. All strategies still use read-only public market data and only write simulated backtest or paper-trading outputs.

Outputs are written under `runs/backtests/<timestamp>/` or `runs/paper/<timestamp>/` and include `config.json`, `trades.csv`, `equity.csv`, and `summary.json`.
