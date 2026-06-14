# Vue Strategy Lab Design

## Goal

Rebuild the local frontend as a Vue 3/Vite app, keep TradingView Lightweight Charts for live/chart views, and expand the strategy registry with more widely known technical strategies that can be backtested and paper-traded.

This project remains read-only and simulated. It can help compare strategies and improve discipline, but it cannot guarantee real profit.

## Architecture

The Python backend remains the API and static file server. Vue owns the browser experience and builds production assets into `algo_trading/web/dist`. The server serves the built Vue app for known frontend routes and continues serving `/api/*` explicitly.

The existing backend contracts stay in place:

- `/api/symbols` returns ranked Binance USDT symbols.
- `/api/backtest` runs one or more simulated backtests.
- `/api/paper` runs bounded local paper trading.
- `/api/live-chart` returns candles plus strategy and paper markers.
- `/api/runs` and `/api/run` read local run output.

Add `/api/strategy-lab` for a ranked matrix of strategy and preset backtests.

## Frontend Routes

- `/` and `/backtest`: backtest workspace.
- `/paper`: bounded paper-trading workspace.
- `/live` and `/chart`: TradingView live market chart with long/short and paper markers.
- `/runs` and `/history`: saved run browser.
- `/lab`: strategy lab for comparing strategy/preset combinations across selected symbols.

The Vue app uses browser history for tab navigation. Unknown non-API paths remain 404.

## TradingView Chart

The live/chart view uses TradingView Lightweight Charts, not the iframe Advanced Chart widget, because local strategy markers must be controlled by the app.

Candles render as candlesticks. Long signals render below bars, short signals render above bars, and paper entries/exits use distinct marker colors. If chart initialization fails, the live panel shows a chart-specific error and the rest of the app remains usable.

## Strategy Expansion

Keep the existing strategies:

- EMA + RSI
- MACD
- Bollinger Reversion
- Donchian Breakout
- RSI Reversal

Add these widely known strategies:

- SuperTrend ATR trend following
- VWAP mean reversion
- Stochastic RSI reversal
- EMA ribbon trend
- Momentum scalping with RSI and MACD confirmation

Each strategy supports long and short entries through the existing `allowed_side` setting. Existing stop loss, take profit, trailing stop, fees, and slippage remain active across all strategies.

## Strategy Lab

The strategy lab runs a matrix of strategy and preset combinations over selected symbols. The backend returns ranked rows with:

- symbol
- strategy
- preset
- final balance
- total return
- max drawdown
- trade count
- win rate
- profit factor

Ranking defaults to highest return, with drawdown and trade count visible so the user can reject fragile results. This is selection support, not an automated profit guarantee.

## Testing

Backend unit tests cover new strategy registry names, at least one entry signal per new strategy, validation of new periods, and strategy lab ranking payloads. Frontend verification covers Vue typecheck/build output and direct route serving. Docker smoke checks must build the Vue assets before running the Python server.

## Non-Goals

- No real Binance order placement.
- No API keys.
- No promise of profit.
- No automatic strategy optimization that mutates parameters until historical results look good.
- No arbitrary SPA fallback for unknown paths.
