from __future__ import annotations

import argparse
import time
import urllib.parse
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from algo_trading.data import (
    BinanceMarketDataClient,
    HONG_KONG_STOCK_SYMBOL_ALIASES,
    HONG_KONG_STOCK_SYMBOLS,
    MAG7_STOCK_SYMBOLS,
    MarketDataClient,
    MoexSharesMarketDataClient,
    TransientMarketDataError,
    YahooFuturesMarketDataClient,
)
from algo_trading.historical_store import HistoricalDataStore
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
MAG7_STOCKS_MARKET = "mag7_stocks"
HONG_KONG_STOCKS_MARKET = "hong_kong_stocks"
RUSSIAN_BLUECHIPS_MARKET = "russian_bluechips"
RUSSIAN_INDICES_MARKET = "russian_indices"
RUSSIAN_FUTURES_MARKET = "russian_futures"
RUSSIAN_INDICES_FUTURES_MARKET = "russian_indices_futures"
_DEFAULT_LIVE_CACHE_STALENESS_MS = 60_000
_LIVE_CACHE_STALENESS_MULTIPLIER = 2
FRONTEND_ROUTES = frozenset(
    {
        "",
        "/",
        "/index.html",
        "/live",
        "/chart",
        "/breadth",
        "/feedback",
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
    historical_store: HistoricalDataStore | None = None,
    *,
    allow_stale_cache: bool = False,
    cache_state: dict[str, bool] | None = None,
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
    data_source = _data_source_label(market, market_client, config.symbol)
    candles = _load_cached_live_candles(
        historical_store,
        market,
        config.symbol,
        config.interval,
        limit=limit,
    )
    cache_hit = False
    cache_stale = False
    if candles:
        cache_stale = not _live_candles_are_fresh(candles, config.interval)
        if cache_stale and not allow_stale_cache:
            candles = []
        else:
            cache_hit = True
    if not candles:
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
        candles = _persist_and_load_live_candles(
            historical_store,
            market,
            config.symbol,
            config.interval,
            candles,
            limit=limit,
            source=data_source,
        )
    if cache_state is not None:
        cache_state.clear()
        cache_state.update({"cache_hit": cache_hit, "cache_stale": cache_hit and cache_stale})
    signals = (
        _all_strategy_signal_markers(candles, configs)
        if len(configs) > 1
        else _strategy_signal_markers(candles, config)
    )
    return {
        "ok": True,
        "market": market,
        "data_source": data_source,
        "symbol": config.symbol,
        "interval": config.interval,
        "strategy": strategy_value,
        "candles": [_candle_payload(candle) for candle in candles],
        "signals": signals,
        "rsi_alert_signal": _latest_rsi_alert_signal(candles, config),
        "indicators": _popular_indicator_payload(candles, config),
    }


def _load_fresh_live_candles(
    historical_store: HistoricalDataStore | None,
    market: str,
    symbol: str,
    interval: str,
    *,
    limit: int,
) -> list[Candle]:
    stored = _load_cached_live_candles(
        historical_store,
        market,
        symbol,
        interval,
        limit=limit,
    )
    if not stored or not _live_candles_are_fresh(stored, interval):
        return []
    return stored


def _load_cached_live_candles(
    historical_store: HistoricalDataStore | None,
    market: str,
    symbol: str,
    interval: str,
    *,
    limit: int,
) -> list[Candle]:
    if historical_store is None:
        return []
    try:
        stored = historical_store.load_candles(
            market,
            symbol,
            interval,
            limit=limit,
        )
    except Exception:
        return []
    if len(stored) < limit:
        return []
    return stored


def _live_candles_are_fresh(candles: list[Candle], interval: str) -> bool:
    if not candles:
        return False
    newest_open_time = max(candle.open_time for candle in candles)
    allowed_age_ms = max(
        _interval_millis(interval) * _LIVE_CACHE_STALENESS_MULTIPLIER,
        _DEFAULT_LIVE_CACHE_STALENESS_MS,
    )
    return newest_open_time >= _current_millis() - allowed_age_ms


def _persist_and_load_live_candles(
    historical_store: HistoricalDataStore | None,
    market: str,
    symbol: str,
    interval: str,
    candles: list[Candle],
    *,
    limit: int,
    source: str,
) -> list[Candle]:
    if historical_store is None:
        return candles
    try:
        historical_store.upsert_candles(
            market,
            symbol,
            interval,
            candles,
            source=source,
        )
        stored = historical_store.load_candles(
            market,
            symbol,
            interval,
            limit=limit,
        )
    except Exception:
        return candles
    return stored or candles


def _current_millis() -> int:
    return int(time.time() * 1000)


def _interval_millis(interval: str) -> int:
    value = str(interval).strip()
    if not value:
        return _DEFAULT_LIVE_CACHE_STALENESS_MS
    unit = value[-1]
    amount_value = value[:-1]
    try:
        amount = int(amount_value)
    except ValueError:
        return _DEFAULT_LIVE_CACHE_STALENESS_MS
    if amount <= 0:
        return _DEFAULT_LIVE_CACHE_STALENESS_MS
    if unit == "m":
        return amount * 60_000
    if unit == "h":
        return amount * 60 * 60_000
    if unit == "d":
        return amount * 24 * 60 * 60_000
    if unit == "w":
        return amount * 7 * 24 * 60 * 60_000
    if unit == "M":
        return amount * 31 * 24 * 60 * 60_000
    return _DEFAULT_LIVE_CACHE_STALENESS_MS


def market_data_client_from_payload(payload: dict[str, Any]) -> MarketDataClient:
    market = _market_from_payload(payload)
    if market in (
        CME_FUTURES_MARKET,
        COMMODITIES_MARKET,
        MAG7_STOCKS_MARKET,
        HONG_KONG_STOCKS_MARKET,
    ):
        return YahooFuturesMarketDataClient()
    if market in (
        RUSSIAN_BLUECHIPS_MARKET,
        RUSSIAN_INDICES_FUTURES_MARKET,
    ):
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
        "us_market": CME_FUTURES_MARKET,
        "commodity": COMMODITIES_MARKET,
        "commodities": COMMODITIES_MARKET,
        "metals": COMMODITIES_MARKET,
        "energy": COMMODITIES_MARKET,
        "mag7": MAG7_STOCKS_MARKET,
        "mag7_stocks": MAG7_STOCKS_MARKET,
        "magnificent7": MAG7_STOCKS_MARKET,
        "magnificent_7": MAG7_STOCKS_MARKET,
        "magnificent_seven": MAG7_STOCKS_MARKET,
        "hk": HONG_KONG_STOCKS_MARKET,
        "hk_stocks": HONG_KONG_STOCKS_MARKET,
        "hongkong": HONG_KONG_STOCKS_MARKET,
        "hong_kong": HONG_KONG_STOCKS_MARKET,
        "hong_kong_stocks": HONG_KONG_STOCKS_MARKET,
        "hong-kong-stocks": HONG_KONG_STOCKS_MARKET,
        "moex": RUSSIAN_BLUECHIPS_MARKET,
        "russian": RUSSIAN_BLUECHIPS_MARKET,
        "russian_bluechips": RUSSIAN_BLUECHIPS_MARKET,
        "ru_bluechips": RUSSIAN_BLUECHIPS_MARKET,
        "russian_indices": RUSSIAN_INDICES_FUTURES_MARKET,
        "russian_index": RUSSIAN_INDICES_FUTURES_MARKET,
        "moex_indices": RUSSIAN_INDICES_FUTURES_MARKET,
        "moex_index": RUSSIAN_INDICES_FUTURES_MARKET,
        "russian_futures": RUSSIAN_INDICES_FUTURES_MARKET,
        "moex_futures": RUSSIAN_INDICES_FUTURES_MARKET,
        "rtsi_futures": RUSSIAN_INDICES_FUTURES_MARKET,
        "russian_indices_futures": RUSSIAN_INDICES_FUTURES_MARKET,
        "russian_index_futures": RUSSIAN_INDICES_FUTURES_MARKET,
        "moex_indices_futures": RUSSIAN_INDICES_FUTURES_MARKET,
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
    if market == MAG7_STOCKS_MARKET:
        default_symbol = "AAPL"
    if market == HONG_KONG_STOCKS_MARKET:
        default_symbol = "9988.HK"
    if market == RUSSIAN_BLUECHIPS_MARKET:
        default_symbol = "SBER"
    if market == RUSSIAN_INDICES_FUTURES_MARKET:
        default_symbol = "IMOEX"
    symbol = str(payload.get("symbol") or default_symbol).upper()
    if market == MAG7_STOCKS_MARKET and symbol not in MAG7_STOCK_SYMBOLS:
        raise ValueError(f"unsupported MAG 7 stock symbol: {symbol}")
    if market == HONG_KONG_STOCKS_MARKET:
        if symbol in HONG_KONG_STOCK_SYMBOLS:
            return symbol
        try:
            return HONG_KONG_STOCK_SYMBOL_ALIASES[symbol]
        except KeyError as exc:
            raise ValueError(f"unsupported Hong Kong stock symbol: {symbol}") from exc
    return symbol


def _data_source_label(
    market: str,
    client: MarketDataClient | None = None,
    symbol: str = "",
) -> str:
    if market == CME_FUTURES_MARKET:
        return "Yahoo Finance delayed CME futures"
    if market == COMMODITIES_MARKET:
        return "Yahoo Finance delayed commodity futures"
    if market == MAG7_STOCKS_MARKET:
        return "Yahoo Finance delayed US equities"
    if market == HONG_KONG_STOCKS_MARKET:
        return "Yahoo Finance delayed Hong Kong stocks"
    if market == RUSSIAN_INDICES_FUTURES_MARKET:
        return "MOEX APIM indices and futures"
    if market == RUSSIAN_BLUECHIPS_MARKET:
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


def _latest_rsi_alert_signal(
    candles: list[Candle],
    config: StrategyConfig,
) -> dict[str, Any] | None:
    rsi_config = replace(config, strategy=StrategyName.RSI_REVERSAL)
    markers = _strategy_signal_markers(candles, rsi_config)
    if not markers or not candles:
        return None
    latest_marker = markers[-1]
    return latest_marker if latest_marker["time"] == candles[-1].open_time else None


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
                _indicator_series_payload(
                    "volume",
                    "Volume",
                    "histogram",
                    "#64748b",
                    candles,
                    [candle.volume for candle in candles],
                    point_colors=_volume_bar_colors(candles),
                ),
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
    point_colors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": series_id,
        "label": label,
        "type": series_type,
        "color": color,
        "points": _indicator_points(candles, values, point_colors),
    }


def _indicator_points(
    candles: list[Candle],
    values: list[float],
    point_colors: list[str] | None = None,
) -> list[dict[str, float | int | str]]:
    points: list[dict[str, float | int | str]] = []
    for index, (candle, value) in enumerate(zip(candles, values)):
        point: dict[str, float | int | str] = {
            "time": candle.open_time,
            "value": float(value),
        }
        if point_colors and index < len(point_colors):
            point["color"] = point_colors[index]
        points.append(point)
    return points


def _volume_bar_colors(candles: list[Candle]) -> list[str]:
    colors: list[str] = []
    previous_close: float | None = None
    for candle in candles:
        reference = previous_close if previous_close is not None else candle.open
        colors.append("#22ab94" if candle.close >= reference else "#f23645")
        previous_close = candle.close
    return colors


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
