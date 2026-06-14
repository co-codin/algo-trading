from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from algo_trading.models import BacktestResult, StrategyConfig


def write_run_outputs(
    kind: str,
    config: StrategyConfig,
    result: BacktestResult,
    output_root: str | Path = "runs",
) -> Path:
    run_dir = Path(output_root) / kind / _timestamp()
    run_dir.mkdir(parents=True, exist_ok=False)
    _write_json(run_dir / "config.json", _to_jsonable(asdict(config)))
    _write_trades(run_dir / "trades.csv", result)
    _write_equity(run_dir / "equity.csv", result)
    _write_json(run_dir / "summary.json", result.summary)
    return run_dir


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _write_trades(path: Path, result: BacktestResult) -> None:
    fieldnames = [
        "side",
        "entry_time",
        "exit_time",
        "entry_price",
        "exit_price",
        "quantity",
        "realized_pnl",
        "fees",
        "slippage",
        "entry_reason",
        "exit_reason",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for trade in result.trades:
            row = _to_jsonable(asdict(trade))
            writer.writerow(row)


def _write_equity(path: Path, result: BacktestResult) -> None:
    fieldnames = ["time", "equity", "cash", "position_side", "position_quantity"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for point in result.equity:
            writer.writerow(asdict(point))


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _to_jsonable(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(inner) for inner in value]
    return value
