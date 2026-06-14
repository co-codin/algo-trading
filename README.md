# Algo Trading

Local BTCUSDT backtesting and paper trading.

Safety boundary: this project uses read-only public market data only. It does not accept Binance API keys and cannot place real orders.

## Usage

Run the full test suite:

```bash
python3 -m unittest discover -v
```

Run a live read-only BTCUSDT backtest:

```bash
python3 -m algo_trading.cli backtest --symbol BTCUSDT --interval 1h --limit 300
```

Run a bounded paper-trading session:

```bash
python3 -m algo_trading.cli paper --symbol BTCUSDT --interval 1m --iterations 3
```

Use `--allowed-side long-only` or `--allowed-side short-only` to focus a run on one side. The default is `both`.

Outputs are written under `runs/backtests/<timestamp>/` or `runs/paper/<timestamp>/` and include `config.json`, `trades.csv`, `equity.csv`, and `summary.json`.
