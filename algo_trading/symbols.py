from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


EXCLUDED_USDT_BASE_ASSETS = {
    "AUD",
    "BIDR",
    "BRL",
    "BUSD",
    "DAI",
    "EUR",
    "FDUSD",
    "GBP",
    "PAXG",
    "RUB",
    "TUSD",
    "TRY",
    "UAH",
    "USDC",
    "USD1",
    "USDP",
    "XAUT",
    "ZAR",
}


@dataclass(frozen=True)
class RankedSymbol:
    symbol: str
    base_asset: str
    quote_volume: float
    last_price: float


def ranked_usdt_symbols(
    tickers: Sequence[Mapping[str, Any]],
    limit: int = 10,
) -> list[RankedSymbol]:
    if limit <= 0:
        raise ValueError("limit must be positive")

    ranked: list[RankedSymbol] = []
    for ticker in tickers:
        symbol = str(ticker.get("symbol", "")).upper()
        if not symbol.endswith("USDT"):
            continue
        base_asset = symbol[:-4]
        if not base_asset or base_asset in EXCLUDED_USDT_BASE_ASSETS:
            continue
        try:
            quote_volume = float(ticker["quoteVolume"])
            last_price = float(ticker["lastPrice"])
        except (KeyError, TypeError, ValueError):
            continue
        ranked.append(
            RankedSymbol(
                symbol=symbol,
                base_asset=base_asset,
                quote_volume=quote_volume,
                last_price=last_price,
            )
        )

    return sorted(ranked, key=lambda item: item.quote_volume, reverse=True)[:limit]


def parse_symbol_list(value: str) -> list[str]:
    symbols = [part.strip().upper() for part in value.split(",") if part.strip()]
    if not symbols:
        raise ValueError("at least one symbol is required")
    return symbols
