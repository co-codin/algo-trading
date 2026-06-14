from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from algo_trading.data import (
    BinanceMarketDataClient,
    MarketDataClient,
    TransientMarketDataError,
)
from algo_trading.models import (
    AllowedSide,
    Candle,
    StrategyConfig,
    StrategyName,
    StrategyPreset,
)
from algo_trading.paper import run_paper_session
from algo_trading.simulator import run_backtest
from algo_trading.storage import write_run_outputs
from algo_trading.strategy import (
    apply_strategy_preset,
    build_strategy_context,
    entry_signal_for_index,
)
from algo_trading.symbols import parse_symbol_list, ranked_usdt_symbols

WEB_ROOT = Path(__file__).with_name("web")


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


def run_backtest_payload(
    payload: dict[str, Any],
    client: MarketDataClient | None = None,
    output_root: str | Path = "runs",
) -> dict[str, Any]:
    market_client = client or BinanceMarketDataClient()
    output_path = Path(output_root)
    symbols = _resolve_symbols(
        str(payload.get("symbols") or payload.get("symbol") or "BTCUSDT"),
        _int_value(payload, "top", 10),
        market_client,
    )
    limit = _int_value(payload, "limit", 300)
    retries = _int_value(payload, "market_data_retries", 2)
    retry_delay = _float_value(payload, "retry_delay", 0.5)

    runs: list[dict[str, Any]] = []
    for symbol in symbols:
        config = apply_strategy_preset(
            _strategy_config_from_payload(payload, symbol=symbol, default_interval="1h")
        )
        candles = _get_klines_with_retries(
            market_client,
            config.symbol,
            config.interval,
            limit,
            retries,
            retry_delay,
        )
        result = run_backtest(candles, config)
        run_dir = write_run_outputs("backtests", config, result, output_path)
        runs.append(_run_payload("backtest", run_dir, output_path, result.summary))

    return {"ok": True, "mode": "backtest", "runs": runs}


def run_paper_payload(
    payload: dict[str, Any],
    client: MarketDataClient | None = None,
    output_root: str | Path = "runs",
) -> dict[str, Any]:
    market_client = client or BinanceMarketDataClient()
    output_path = Path(output_root)
    symbols = parse_symbol_list(str(payload.get("symbol") or "BTCUSDT"))
    if len(symbols) != 1:
        raise ValueError("paper mode accepts one symbol")

    config = apply_strategy_preset(
        _strategy_config_from_payload(
            payload,
            symbol=symbols[0],
            default_interval="1m",
        )
    )
    run_dir = run_paper_session(
        market_client,
        config,
        output_path,
        poll_seconds=_float_value(payload, "poll_seconds", 30.0),
        iterations=_int_value(payload, "iterations", 3),
        limit=_int_value(payload, "limit", 300),
    )
    summary = _read_json(run_dir / "summary.json")
    return {
        "ok": True,
        "mode": "paper",
        "runs": [_run_payload("paper", run_dir, output_path, summary)],
    }


def live_chart_payload(
    payload: dict[str, Any],
    client: MarketDataClient | None = None,
    output_root: str | Path = "runs",
) -> dict[str, Any]:
    market_client = client or BinanceMarketDataClient()
    symbol = str(payload.get("symbol") or "BTCUSDT").upper()
    limit = _int_value(payload, "limit", 180)
    config = apply_strategy_preset(
        _strategy_config_from_payload(payload, symbol=symbol, default_interval="1m")
    )
    candles = market_client.get_klines(config.symbol, config.interval, limit)
    if not candles:
        raise ValueError("market-data client returned no candles")
    start_time = candles[0].open_time
    end_time = candles[-1].open_time
    return {
        "ok": True,
        "symbol": config.symbol,
        "interval": config.interval,
        "candles": [_candle_payload(candle) for candle in candles],
        "signals": _strategy_signal_markers(candles, config),
        "paper_markers": paper_trade_markers(
            config.symbol,
            start_time,
            end_time,
            output_root,
        ),
    }


def paper_trade_markers(
    symbol: str,
    start_time: int,
    end_time: int,
    output_root: str | Path = "runs",
) -> list[dict[str, Any]]:
    root = Path(output_root)
    paper_root = root / "paper"
    if not paper_root.exists():
        return []

    markers: list[dict[str, Any]] = []
    for run_dir in paper_root.iterdir():
        if not run_dir.is_dir():
            continue
        config_path = run_dir / "config.json"
        if config_path.exists():
            try:
                config = _read_json(config_path)
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            if str(config.get("symbol", "")).upper() != symbol.upper():
                continue

        for row in _read_csv_rows(run_dir / "trades.csv", 10_000):
            try:
                side = str(row["side"]).lower()
                entry_time = int(row["entry_time"])
                exit_time = int(row["exit_time"])
                entry_price = float(row["entry_price"])
                exit_price = float(row["exit_price"])
                entry_reason = str(row.get("entry_reason", ""))
                exit_reason = str(row.get("exit_reason", ""))
            except (KeyError, TypeError, ValueError):
                continue
            if side not in {"long", "short"}:
                continue
            if start_time <= entry_time <= end_time:
                markers.append(
                    {
                        "time": entry_time,
                        "price": entry_price,
                        "type": f"paper_entry_{side}",
                        "reason": entry_reason,
                    }
                )
            if start_time <= exit_time <= end_time:
                markers.append(
                    {
                        "time": exit_time,
                        "price": exit_price,
                        "type": f"paper_exit_{side}",
                        "reason": exit_reason,
                    }
                )
    return sorted(markers, key=lambda item: (int(item["time"]), str(item["type"])))


def list_runs(output_root: str | Path = "runs", limit: int = 20) -> list[dict[str, Any]]:
    root = Path(output_root)
    runs: list[dict[str, Any]] = []
    for directory_name, mode in (("backtests", "backtest"), ("paper", "paper")):
        base = root / directory_name
        if not base.exists():
            continue
        for run_dir in base.iterdir():
            summary_path = run_dir / "summary.json"
            if not run_dir.is_dir() or not summary_path.exists():
                continue
            try:
                summary = _read_json(summary_path)
            except (OSError, json.JSONDecodeError):
                continue
            runs.append(_run_payload(mode, run_dir, root, summary))
    return sorted(runs, key=lambda item: str(item["timestamp"]), reverse=True)[:limit]


def load_run_details(
    run_path: str,
    output_root: str | Path = "runs",
    trade_limit: int = 50,
    equity_limit: int = 200,
) -> dict[str, Any]:
    root = Path(output_root).resolve()
    relative = Path(run_path)
    if relative.is_absolute():
        raise ValueError("run path must be relative")
    run_dir = (root / relative).resolve()
    try:
        run_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("run path escapes output root") from exc
    if not run_dir.is_dir():
        raise ValueError("run not found")

    return {
        "ok": True,
        "path": relative.as_posix(),
        "summary": _read_json(run_dir / "summary.json"),
        "config": _read_json(run_dir / "config.json"),
        "trades": _read_csv_rows(run_dir / "trades.csv", trade_limit),
        "equity": _read_csv_rows(run_dir / "equity.csv", equity_limit),
    }


def create_handler(
    output_root: str | Path = "runs",
    client_factory: Callable[[], MarketDataClient] = BinanceMarketDataClient,
) -> type[BaseHTTPRequestHandler]:
    output_path = Path(output_root)

    class UiRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._handle_request("GET")

        def do_POST(self) -> None:
            self._handle_request("POST")

        def log_message(self, format: str, *args: object) -> None:
            print(f"{self.address_string()} - {format % args}", file=sys.stderr)

        def _handle_request(self, method: str) -> None:
            parsed = urllib.parse.urlparse(self.path)
            try:
                if method == "GET":
                    self._handle_get(parsed)
                    return
                if method == "POST":
                    self._handle_post(parsed)
                    return
                self._send_json(
                    {"ok": False, "error": "method not allowed"},
                    HTTPStatus.METHOD_NOT_ALLOWED,
                )
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json(
                    {"ok": False, "error": str(exc)},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def _handle_get(self, parsed: urllib.parse.ParseResult) -> None:
            if parsed.path in ("", "/", "/index.html"):
                self._send_file(WEB_ROOT / "index.html", "text/html; charset=utf-8")
                return
            if parsed.path == "/styles.css":
                self._send_file(WEB_ROOT / "styles.css", "text/css; charset=utf-8")
                return
            if parsed.path == "/app.js":
                self._send_file(WEB_ROOT / "app.js", "text/javascript; charset=utf-8")
                return
            if parsed.path == "/api/symbols":
                query = urllib.parse.parse_qs(parsed.query)
                top = int(query.get("top", ["10"])[0])
                self._send_json(top_symbols_payload(client_factory(), top=top))
                return
            if parsed.path == "/api/runs":
                self._send_json({"ok": True, "runs": list_runs(output_path)})
                return
            if parsed.path == "/api/live-chart":
                query = urllib.parse.parse_qs(parsed.query)
                self._send_json(
                    live_chart_payload(
                        _query_payload(query),
                        client_factory(),
                        output_path,
                    )
                )
                return
            if parsed.path == "/api/run":
                query = urllib.parse.parse_qs(parsed.query)
                run_path = query.get("path", [""])[0]
                self._send_json(load_run_details(run_path, output_path))
                return
            self._send_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)

        def _handle_post(self, parsed: urllib.parse.ParseResult) -> None:
            payload = self._read_json_body()
            if parsed.path == "/api/backtest":
                self._send_json(
                    run_backtest_payload(payload, client_factory(), output_path)
                )
                return
            if parsed.path == "/api/paper":
                self._send_json(run_paper_payload(payload, client_factory(), output_path))
                return
            self._send_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            value = json.loads(body)
            if not isinstance(value, dict):
                raise ValueError("JSON payload must be an object")
            return value

        def _send_file(self, path: Path, content_type: str) -> None:
            if not path.is_file():
                self._send_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(
            self,
            value: dict[str, Any],
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            body = (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return UiRequestHandler


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    output_root: str | Path = "runs",
) -> None:
    server = ThreadingHTTPServer((host, port), create_handler(output_root))
    display_host = "127.0.0.1" if host in ("", "0.0.0.0") else host
    print(f"Serving algo-trading UI at http://{display_host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping algo-trading UI")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="algo-trading-ui")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--output-root", default="runs")
    args = parser.parse_args(argv)
    serve(host=args.host, port=args.port, output_root=args.output_root)
    return 0


def _resolve_symbols(
    value: str,
    top: int,
    client: MarketDataClient,
) -> list[str]:
    text = value.strip()
    lower = text.lower()
    if lower == "top" or lower.startswith("top "):
        parts = lower.split()
        limit = int(parts[1]) if len(parts) > 1 else top
        return [item.symbol for item in ranked_usdt_symbols(client.get_24h_tickers(), limit)]
    return parse_symbol_list(text)


def _query_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    return {key: values[-1] for key, values in query.items() if values}


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
        stop_loss_pct=_float_value(payload, "stop_loss_pct", 0.03),
        take_profit_pct=_float_value(payload, "take_profit_pct", 0.06),
        trailing_stop_pct=_float_value(payload, "trailing_stop_pct", 0.0),
    )


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
) -> list[dict[str, Any]]:
    context = build_strategy_context(candles, config)
    markers: list[dict[str, Any]] = []
    for index, candle in enumerate(candles):
        signal = entry_signal_for_index(config, context, index)
        if signal.type.value == "enter_long":
            markers.append(
                {
                    "time": candle.open_time,
                    "price": candle.close,
                    "type": "long_signal",
                    "reason": signal.reason,
                }
            )
        elif signal.type.value == "enter_short":
            markers.append(
                {
                    "time": candle.open_time,
                    "price": candle.close,
                    "type": "short_signal",
                    "reason": signal.reason,
                }
            )
    return markers


def _candle_payload(candle: Candle) -> dict[str, float | int]:
    return {
        "time": candle.open_time,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
    }


def _run_payload(
    mode: str,
    run_dir: Path,
    output_root: Path,
    summary: dict[str, Any],
) -> dict[str, Any]:
    relative = run_dir.relative_to(output_root).as_posix()
    return {
        "mode": mode,
        "path": relative,
        "timestamp": run_dir.name,
        "symbol": summary.get("symbol", ""),
        "final_balance": summary.get("final_balance"),
        "summary": summary,
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


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _read_csv_rows(path: Path, limit: int) -> list[dict[str, str]]:
    if limit <= 0 or not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return rows[:limit]


if __name__ == "__main__":
    raise SystemExit(main())
