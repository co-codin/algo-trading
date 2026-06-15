# Add Strategy Bundle Design

## Goal

Add all three requested strategy bundles to the existing backtesting and live-chart registry:

- Trend and breakout: `keltner-breakout`, `ema-pullback`, `atr-trailing-trend`
- Mean reversion: `cci-reversal`, `williams-r-reversal`, `bollinger-squeeze-release`
- Volume and confirmation: `obv-trend`, `volume-breakout`, `vwap-trend-continuation`

The feature must keep the read-only/simulated safety boundary. It only adds deterministic signal logic, metadata, tests, and documentation.

## Architecture

The project already centralizes strategies through `StrategyName`, `StrategyConfig`, `StrategyContext`, and `_STRATEGIES`. The new work follows that pattern: add enum values, compute any needed indicator series in `build_strategy_context`, implement one strategy class per strategy, register each class, and update warmup requirements in `simulator.py`.

Only lightweight indicator helpers are added to `algo_trading/indicators.py`: Keltner channels, CCI, Williams %R, OBV, rolling volume mean, and Bollinger band width. These helpers are pure functions over candles or numeric lists and do not call external services.

## Strategy Behavior

`keltner-breakout` enters long when close crosses above the Keltner upper band and short when close crosses below the lower band. It exits when price crosses back through the Keltner middle EMA.

`ema-pullback` enters in the trend direction when price reclaims the fast EMA while fast EMA remains above/below the slow EMA. It exits when the fast/slow EMA trend alignment is lost.

`atr-trailing-trend` enters on a SuperTrend-style direction flip and exits when price crosses an ATR trailing stop derived from the best close since entry context.

`cci-reversal` enters long when CCI leaves oversold territory and short when CCI leaves overbought territory. It exits around the CCI zero line.

`williams-r-reversal` enters long when Williams %R leaves oversold territory and short when it leaves overbought territory. It exits around the midpoint.

`bollinger-squeeze-release` enters when Bollinger width expands after a low-width squeeze and price breaks the upper/lower band. It exits when price returns to the Bollinger middle.

`obv-trend` enters when OBV momentum confirms price above/below the slow EMA. It exits when OBV momentum turns against the position.

`volume-breakout` enters when price breaks the previous Donchian high/low while current volume is above its rolling average. It exits on the opposite Donchian boundary.

`vwap-trend-continuation` enters when price is above/below VWAP and fast EMA confirms trend direction. It exits when price crosses VWAP.

## Testing

Use TDD. Add failing tests first for indicator helpers and strategy entries. Existing simulator and UI tests already exercise dynamic registry metadata, but add registry/warmup assertions so the new names are visible and backtest warmup validation does not regress.

## Documentation

Update the README strategy list with one-line descriptions. No frontend hardcoding is required because the UI strategy dropdown reads registry metadata dynamically.

