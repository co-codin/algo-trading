# Algo Trading

Local crypto backtesting and paper trading.

Safety boundary: this project uses read-only public market data only. It does not accept Binance API keys and cannot place real orders.

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

The UI includes a `Live` tab for public Binance candle charts. It overlays EMA/RSI long and short signal markers plus simulated paper entry/exit markers from local `runs/paper/` output.

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

Outputs are written under `runs/backtests/<timestamp>/` or `runs/paper/<timestamp>/` and include `config.json`, `trades.csv`, `equity.csv`, and `summary.json`.
