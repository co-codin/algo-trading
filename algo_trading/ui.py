from __future__ import annotations

import argparse
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable

from algo_trading.data import (
    BinanceMarketDataClient,
    MarketDataClient,
    MoexSharesMarketDataClient,
    TransientMarketDataError,
    YahooFuturesMarketDataClient,
)
from algo_trading.models import (
    AllowedSide,
    Candle,
    StrategyConfig,
    StrategyName,
    StrategyPreset,
)
from algo_trading.strategy import (
    apply_strategy_preset,
    build_strategy_context,
    entry_signal_for_index,
    get_strategy,
    list_strategy_names,
)
from algo_trading.symbols import ranked_usdt_symbols

WEB_ROOT = Path(__file__).with_name("web")
WEB_DIST_ROOT = WEB_ROOT / "dist"
ALL_STRATEGIES_VALUE = "all"
CRYPTO_SPOT_MARKET = "crypto_spot"
CME_FUTURES_MARKET = "cme_futures"
COMMODITIES_MARKET = "commodities"
RUSSIAN_BLUECHIPS_MARKET = "russian_bluechips"
FRONTEND_ROUTES = frozenset(
    {
        "",
        "/",
        "/index.html",
        "/live",
        "/chart",
        "/breadth",
        "/profile",
        "/admin",
    }
)


def is_frontend_route(path: str) -> bool:
    return path in FRONTEND_ROUTES


def is_vite_asset_route(path: str) -> bool:
    normalized = Path(urllib.parse.unquote(path)).as_posix()
    return normalized.startswith("/assets/") and "/../" not in normalized


def top_symbols_payload(client: MarketDataClient, top: int = 10) -> dict[str, Any]:
    ranked = ranked_usdt_symbols(client.get_24h_tickers(), limit=top)
    return {
        "ok": True,
        "symbols": [
            {
                "symbol": item.symbol,
                "base_asset": item.base_asset,
                "quote_volume": item.quote_volume,
                "last_price": item.last_price,
            }
            for item in ranked
        ],
    }


def live_chart_payload(
    payload: dict[str, Any],
    client: MarketDataClient | None = None,
) -> dict[str, Any]:
    market = _market_from_payload(payload)
    market_client = client or market_data_client_from_payload(payload)
    symbol = _live_symbol_from_payload(payload, market)
    limit = _int_value(payload, "limit", 180)
    retries = _int_value(payload, "market_data_retries", 2)
    retry_delay = _float_value(payload, "retry_delay", 0.5)
    strategy_value = str(
        payload.get("strategy") or StrategyName.EMA_RSI.value
    ).strip().lower()
    configs = _live_strategy_configs_from_payload(
        payload,
        symbol=symbol,
        default_interval="1m",
    )
    config = configs[0]
    candles = _get_klines_with_retries(
        market_client,
        config.symbol,
        config.interval,
        limit,
        retries,
        retry_delay,
    )
    if not candles:
        raise ValueError("market-data client returned no candles")
    signals = (
        _all_strategy_signal_markers(candles, configs)
        if len(configs) > 1
        else _strategy_signal_markers(candles, config)
    )
    return {
        "ok": True,
        "market": market,
        "data_source": _data_source_label(market, market_client, config.symbol),
        "symbol": config.symbol,
        "interval": config.interval,
        "strategy": strategy_value,
        "candles": [_candle_payload(candle) for candle in candles],
        "signals": signals,
        "indicators": _popular_indicator_payload(candles, config),
    }


def market_data_client_from_payload(payload: dict[str, Any]) -> MarketDataClient:
    market = _market_from_payload(payload)
    if market in (CME_FUTURES_MARKET, COMMODITIES_MARKET):
        return YahooFuturesMarketDataClient()
    if market == RUSSIAN_BLUECHIPS_MARKET:
        return MoexSharesMarketDataClient()
    if market == CRYPTO_SPOT_MARKET:
        return BinanceMarketDataClient()
    raise ValueError(f"unsupported market: {market}")


def strategies_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "strategies": [
            {
                "name": name,
                "description": get_strategy(name).description,
            }
            for name in list_strategy_names()
        ],
        "presets": [preset.value for preset in StrategyPreset],
    }


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    output_root: str | Path = "runs",
) -> None:
    display_host = "127.0.0.1" if host in ("", "0.0.0.0") else host
    print(f"Serving algo-trading UI at http://{display_host}:{port}")
    import uvicorn

    from algo_trading.web_app import create_app

    uvicorn.run(
        create_app(output_root=output_root),
        host=host,
        port=port,
        log_level="info",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="algo-trading-ui")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--output-root", default="runs")
    args = parser.parse_args(argv)
    serve(host=args.host, port=args.port, output_root=args.output_root)
    return 0


def _market_from_payload(payload: dict[str, Any]) -> str:
    market = str(payload.get("market") or CRYPTO_SPOT_MARKET).strip().lower()
    aliases = {
        "spot": CRYPTO_SPOT_MARKET,
        "crypto": CRYPTO_SPOT_MARKET,
        "crypto_spot": CRYPTO_SPOT_MARKET,
        "binance": CRYPTO_SPOT_MARKET,
        "futures": CME_FUTURES_MARKET,
        "cme": CME_FUTURES_MARKET,
        "cme_futures": CME_FUTURES_MARKET,
        "us_index_futures": CME_FUTURES_MARKET,
        "commodity": COMMODITIES_MARKET,
        "commodities": COMMODITIES_MARKET,
        "metals": COMMODITIES_MARKET,
        "energy": COMMODITIES_MARKET,
        "moex": RUSSIAN_BLUECHIPS_MARKET,
        "russian": RUSSIAN_BLUECHIPS_MARKET,
        "russian_bluechips": RUSSIAN_BLUECHIPS_MARKET,
        "ru_bluechips": RUSSIAN_BLUECHIPS_MARKET,
    }
    try:
        return aliases[market]
    except KeyError as exc:
        raise ValueError(f"unsupported market: {market}") from exc


def _live_symbol_from_payload(payload: dict[str, Any], market: str) -> str:
    default_symbol = "BTCUSDT"
    if market == CME_FUTURES_MARKET:
        default_symbol = "ES=F"
    if market == COMMODITIES_MARKET:
        default_symbol = "GC=F"
    if market == RUSSIAN_BLUECHIPS_MARKET:
        default_symbol = "SBER"
    return str(payload.get("symbol") or default_symbol).upper()


def _data_source_label(
    market: str,
    client: MarketDataClient | None = None,
    symbol: str = "",
) -> str:
    if market == CME_FUTURES_MARKET:
        return "Yahoo Finance delayed CME futures"
    if market == COMMODITIES_MARKET:
        return "Yahoo Finance delayed commodity futures"
    if market == RUSSIAN_BLUECHIPS_MARKET:
        if symbol.upper() == "IMOEX":
            return "MOEX APIM index"
        source_name = getattr(client, "source_name", None)
        if isinstance(source_name, str):
            return source_name
        return "MOEX shares"
    return "Binance Spot public REST"


def _live_client_for_handler(
    payload: dict[str, Any],
    client_factory: Callable[[], MarketDataClient],
) -> MarketDataClient:
    if client_factory is BinanceMarketDataClient:
        return market_data_client_from_payload(payload)
    return client_factory()


def _strategy_config_from_payload(
    payload: dict[str, Any],
    symbol: str,
    default_interval: str,
) -> StrategyConfig:
    return StrategyConfig(
        symbol=symbol.upper(),
        interval=str(payload.get("interval") or default_interval),
        starting_balance=_float_value(payload, "starting_balance", 10000.0),
        fee_rate=_float_value(payload, "fee_rate", 0.001),
        slippage_rate=_float_value(payload, "slippage_rate", 0.0005),
        position_fraction=_float_value(payload, "position_fraction", 1.0),
        allowed_side=AllowedSide(str(payload.get("allowed_side") or "both")),
        strategy=StrategyName(str(payload.get("strategy") or StrategyName.EMA_RSI.value)),
        preset=StrategyPreset(str(payload.get("preset") or StrategyPreset.CUSTOM.value)),
        fast_ema=_int_value(payload, "fast_ema", 12),
        slow_ema=_int_value(payload, "slow_ema", 26),
        rsi_period=_int_value(payload, "rsi_period", 14),
        rsi_overbought=_float_value(payload, "rsi_overbought", 70.0),
        rsi_oversold=_float_value(payload, "rsi_oversold", 30.0),
        rsi_midline=_float_value(payload, "rsi_midline", 50.0),
        macd_signal=_int_value(payload, "macd_signal", 9),
        bollinger_period=_int_value(payload, "bollinger_period", 20),
        bollinger_stddev=_float_value(payload, "bollinger_stddev", 2.0),
        donchian_period=_int_value(payload, "donchian_period", 20),
        atr_period=_int_value(payload, "atr_period", 14),
        supertrend_multiplier=_float_value(payload, "supertrend_multiplier", 3.0),
        vwap_period=_int_value(payload, "vwap_period", 20),
        vwap_threshold_pct=_float_value(payload, "vwap_threshold_pct", 0.01),
        stoch_rsi_period=_int_value(payload, "stoch_rsi_period", 14),
        stoch_rsi_oversold=_float_value(payload, "stoch_rsi_oversold", 20.0),
        stoch_rsi_overbought=_float_value(payload, "stoch_rsi_overbought", 80.0),
        ema_ribbon_fast=_int_value(payload, "ema_ribbon_fast", 8),
        ema_ribbon_mid=_int_value(payload, "ema_ribbon_mid", 21),
        ema_ribbon_slow=_int_value(payload, "ema_ribbon_slow", 55),
        momentum_period=_int_value(payload, "momentum_period", 10),
        keltner_multiplier=_float_value(payload, "keltner_multiplier", 2.0),
        cci_period=_int_value(payload, "cci_period", 20),
        cci_oversold=_float_value(payload, "cci_oversold", -100.0),
        cci_overbought=_float_value(payload, "cci_overbought", 100.0),
        williams_period=_int_value(payload, "williams_period", 14),
        williams_oversold=_float_value(payload, "williams_oversold", -80.0),
        williams_overbought=_float_value(payload, "williams_overbought", -20.0),
        volume_period=_int_value(payload, "volume_period", 20),
        volume_multiplier=_float_value(payload, "volume_multiplier", 1.5),
        squeeze_threshold_pct=_float_value(payload, "squeeze_threshold_pct", 0.05),
        combo_strategies=str(payload.get("combo_strategies") or "all"),
        combo_entry_confirmations=_int_value(payload, "combo_entry_confirmations", 2),
        combo_exit_confirmations=_int_value(payload, "combo_exit_confirmations", 2),
        combo_lookback=_int_value(payload, "combo_lookback", 3),
        stop_loss_pct=_float_value(payload, "stop_loss_pct", 0.03),
        take_profit_pct=_float_value(payload, "take_profit_pct", 0.06),
        trailing_stop_pct=_float_value(payload, "trailing_stop_pct", 0.0),
    )


def _live_strategy_configs_from_payload(
    payload: dict[str, Any],
    symbol: str,
    default_interval: str,
) -> list[StrategyConfig]:
    strategy_value = str(
        payload.get("strategy") or StrategyName.EMA_RSI.value
    ).strip().lower()
    strategies = _strategy_names_from_value(strategy_value)
    return [
        apply_strategy_preset(
            _strategy_config_from_payload(
                {**payload, "strategy": strategy.value},
                symbol=symbol,
                default_interval=default_interval,
            )
        )
        for strategy in strategies
    ]


def _strategy_names_from_value(strategy_value: str) -> list[StrategyName]:
    raw_value = strategy_value.strip().lower()
    if raw_value == ALL_STRATEGIES_VALUE:
        return [StrategyName(name) for name in list_strategy_names()]

    raw_names = [item.strip() for item in raw_value.split(",") if item.strip()]
    if not raw_names:
        return [StrategyName.EMA_RSI]
    if ALL_STRATEGIES_VALUE in raw_names:
        return [StrategyName(name) for name in list_strategy_names()]

    strategies: list[StrategyName] = []
    seen: set[StrategyName] = set()
    for raw_name in raw_names:
        try:
            strategy_name = StrategyName(raw_name)
        except ValueError as exc:
            raise ValueError(f"unsupported strategy: {raw_name}") from exc
        if strategy_name in seen:
            continue
        strategies.append(strategy_name)
        seen.add(strategy_name)
    return strategies


def _get_klines_with_retries(
    client: MarketDataClient,
    symbol: str,
    interval: str,
    limit: int,
    retries: int,
    retry_delay: float,
) -> list[Candle]:
    if retries < 0:
        raise ValueError("market-data retries cannot be negative")
    if retry_delay < 0:
        raise ValueError("retry delay cannot be negative")

    attempts = 0
    while True:
        try:
            return client.get_klines(symbol, interval, limit)
        except TransientMarketDataError:
            if attempts >= retries:
                raise
            attempts += 1
            if retry_delay > 0:
                time.sleep(retry_delay)


def _strategy_signal_markers(
    candles: list[Candle],
    config: StrategyConfig,
    include_strategy_name: bool = False,
) -> list[dict[str, Any]]:
    context = build_strategy_context(candles, config)
    markers: list[dict[str, Any]] = []
    for index, candle in enumerate(candles):
        signal = entry_signal_for_index(config, context, index)
        reason = (
            f"{config.strategy.value}: {signal.reason}"
            if include_strategy_name
            else signal.reason
        )
        if signal.type.value == "enter_long":
            markers.append(
                {
                    "time": candle.open_time,
                    "price": candle.close,
                    "type": "long_signal",
                    "reason": reason,
                }
            )
        elif signal.type.value == "enter_short":
            markers.append(
                {
                    "time": candle.open_time,
                    "price": candle.close,
                    "type": "short_signal",
                    "reason": reason,
                }
            )
    return markers


def _all_strategy_signal_markers(
    candles: list[Candle],
    configs: list[StrategyConfig],
) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for config in configs:
        markers.extend(
            _strategy_signal_markers(candles, config, include_strategy_name=True)
        )
    return sorted(
        markers,
        key=lambda item: (int(item["time"]), str(item["reason"]), str(item["type"])),
    )


def _popular_indicator_payload(
    candles: list[Candle],
    config: StrategyConfig,
) -> list[dict[str, Any]]:
    context = build_strategy_context(candles, config)
    return [
        _indicator_payload(
            indicator_id="sma",
            label="SMA",
            pane="price",
            default_visible=False,
            series=[
                _indicator_series_payload("sma_fast", f"SMA {config.fast_ema}", "line", "#f59e0b", candles, context.fast_sma),
                _indicator_series_payload("sma_slow", f"SMA {config.slow_ema}", "line", "#60a5fa", candles, context.slow_sma),
            ],
        ),
        _indicator_payload(
            indicator_id="ema",
            label="EMA",
            pane="price",
            default_visible=True,
            series=[
                _indicator_series_payload("ema_fast", f"EMA {config.fast_ema}", "line", "#ffb020", candles, context.fast),
                _indicator_series_payload("ema_slow", f"EMA {config.slow_ema}", "line", "#6ea8fe", candles, context.slow),
            ],
        ),
        _indicator_payload(
            indicator_id="bollinger",
            label="Bollinger Bands",
            pane="price",
            default_visible=False,
            series=[
                _indicator_series_payload("bollinger_upper", "BB Upper", "line", "#9b8cff", candles, context.bollinger_upper),
                _indicator_series_payload("bollinger_mid", "BB Mid", "line", "#c4b5fd", candles, context.bollinger_mid),
                _indicator_series_payload("bollinger_lower", "BB Lower", "line", "#9b8cff", candles, context.bollinger_lower),
            ],
        ),
        _indicator_payload(
            indicator_id="vwap",
            label="VWAP",
            pane="price",
            default_visible=True,
            series=[
                _indicator_series_payload("vwap", f"VWAP {config.vwap_period}", "line", "#2dd4bf", candles, context.vwap),
            ],
        ),
        _indicator_payload(
            indicator_id="donchian",
            label="Donchian Channel",
            pane="price",
            default_visible=False,
            series=[
                _indicator_series_payload("donchian_high", "Donchian High", "line", "#38bdf8", candles, context.donchian_high),
                _indicator_series_payload("donchian_low", "Donchian Low", "line", "#38bdf8", candles, context.donchian_low),
            ],
        ),
        _indicator_payload(
            indicator_id="volume",
            label="Volume",
            pane="volume",
            default_visible=True,
            series=[
                _indicator_series_payload("volume", "Volume", "histogram", "#64748b", candles, [candle.volume for candle in candles]),
                _indicator_series_payload("volume_mean", f"Volume MA {config.volume_period}", "line", "#f97316", candles, context.volume_mean),
            ],
        ),
        _indicator_payload(
            indicator_id="rsi",
            label="RSI",
            pane="oscillator",
            default_visible=True,
            series=[
                _indicator_series_payload("rsi", f"RSI {config.rsi_period}", "line", "#a78bfa", candles, context.rsi_values),
            ],
        ),
        _indicator_payload(
            indicator_id="macd",
            label="MACD",
            pane="oscillator",
            default_visible=True,
            series=[
                _indicator_series_payload("macd", "MACD", "line", "#60a5fa", candles, context.macd),
                _indicator_series_payload("macd_signal", "MACD Signal", "line", "#f59e0b", candles, context.macd_signal),
                _indicator_series_payload("macd_histogram", "MACD Histogram", "histogram", "#22ab94", candles, [macd_value - signal_value for macd_value, signal_value in zip(context.macd, context.macd_signal)]),
            ],
        ),
        _indicator_payload(
            indicator_id="atr",
            label="ATR",
            pane="oscillator",
            default_visible=False,
            series=[
                _indicator_series_payload("atr", f"ATR {config.atr_period}", "line", "#f43f5e", candles, context.atr_values),
            ],
        ),
        _indicator_payload(
            indicator_id="stoch-rsi",
            label="Stoch RSI",
            pane="oscillator",
            default_visible=False,
            series=[
                _indicator_series_payload("stoch_rsi", f"Stoch RSI {config.stoch_rsi_period}", "line", "#34d399", candles, context.stoch_rsi_values),
            ],
        ),
    ]


def _indicator_payload(
    *,
    indicator_id: str,
    label: str,
    pane: str,
    default_visible: bool,
    series: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": indicator_id,
        "label": label,
        "pane": pane,
        "default_visible": default_visible,
        "series": series,
    }


def _indicator_series_payload(
    series_id: str,
    label: str,
    series_type: str,
    color: str,
    candles: list[Candle],
    values: list[float],
) -> dict[str, Any]:
    return {
        "id": series_id,
        "label": label,
        "type": series_type,
        "color": color,
        "points": _indicator_points(candles, values),
    }


def _indicator_points(
    candles: list[Candle],
    values: list[float],
) -> list[dict[str, float | int]]:
    return [
        {
            "time": candle.open_time,
            "value": float(value),
        }
        for candle, value in zip(candles, values)
    ]


def _candle_payload(candle: Candle) -> dict[str, float | int]:
    return {
        "time": candle.open_time,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
    }


def _int_value(payload: dict[str, Any], key: str, default: int) -> int:
    value = payload.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _float_value(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a number") from exc


if __name__ == "__main__":
    raise SystemExit(main())
