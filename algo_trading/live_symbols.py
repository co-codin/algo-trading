from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from algo_trading.env import load_env_file


@dataclass(frozen=True)
class LiveSymbol:
    market: str
    symbol: str
    label: str
    sort_order: int = 0


class LiveSymbolStore(Protocol):
    def ensure_schema(self) -> None: ...
    def seed_default_symbols(self) -> None: ...
    def upsert_symbols(self, symbols: Sequence[LiveSymbol]) -> int: ...
    def list_symbols(self) -> list[LiveSymbol]: ...


CRYPTO_SYMBOLS = (
    ("BTCUSDT", "BTCUSDT"),
    ("ETHUSDT", "ETHUSDT"),
    ("SOLUSDT", "SOLUSDT"),
    ("BNBUSDT", "BNBUSDT"),
    ("XRPUSDT", "XRPUSDT"),
    ("DOGEUSDT", "DOGEUSDT"),
    ("ADAUSDT", "ADAUSDT"),
    ("AVAXUSDT", "AVAXUSDT"),
    ("LINKUSDT", "LINKUSDT"),
    ("TONUSDT", "TONUSDT"),
    ("DOTUSDT", "DOTUSDT"),
    ("TRXUSDT", "TRXUSDT"),
    ("MATICUSDT", "MATICUSDT"),
    ("LTCUSDT", "LTCUSDT"),
    ("BCHUSDT", "BCHUSDT"),
    ("UNIUSDT", "UNIUSDT"),
)

US_MARKET_SYMBOLS = (
    ("ES=F", "S&P 500 Future"),
    ("NQ=F", "Nasdaq 100 Future"),
    ("YM=F", "Dow Jones Future"),
    ("SPY", "SPY · S&P 500 ETF"),
    ("QQQ", "QQQ · Nasdaq 100 ETF"),
    ("DIA", "DIA · Dow Jones ETF"),
)

COMMODITY_SYMBOLS = (
    ("GC=F", "Gold"),
    ("SI=F", "Silver"),
    ("NG=F", "Natural gas"),
    ("BZ=F", "Brent oil"),
    ("PL=F", "Platinum"),
    ("PA=F", "Palladium"),
    ("HG=F", "Copper"),
)

MAG7_SYMBOLS = (
    ("AAPL", "AAPL · Apple"),
    ("AMZN", "AMZN · Amazon"),
    ("GOOGL", "GOOGL · Alphabet"),
    ("META", "META · Meta"),
    ("MSFT", "MSFT · Microsoft"),
    ("NVDA", "NVDA · NVIDIA"),
    ("TSLA", "TSLA · Tesla"),
)

HONG_KONG_SYMBOLS = (
    ("0700.HK", "0700.HK · Tencent"),
    ("9988.HK", "9988.HK · Alibaba"),
    ("9888.HK", "9888.HK · Baidu"),
    ("3690.HK", "3690.HK · Meituan"),
    ("9618.HK", "9618.HK · JD.com"),
    ("9999.HK", "9999.HK · NetEase"),
    ("1810.HK", "1810.HK · Xiaomi"),
    ("1024.HK", "1024.HK · Kuaishou"),
    ("0968.HK", "0968.HK · Xpeng"),
    ("2015.HK", "2015.HK · Li Auto"),
    ("1211.HK", "1211.HK · BYD"),
    ("2318.HK", "2318.HK · Ping An"),
    ("0939.HK", "0939.HK · China Construction Bank"),
    ("1398.HK", "1398.HK · ICBC"),
    ("0388.HK", "0388.HK · HKEX"),
    ("1299.HK", "1299.HK · AIA"),
    ("0005.HK", "0005.HK · HSBC"),
    ("0941.HK", "0941.HK · China Mobile"),
    ("0883.HK", "0883.HK · CNOOC"),
    ("2628.HK", "2628.HK · China Life"),
)

MOEX_BLUECHIP_SYMBOLS = (
    "AFKS",
    "AFLT",
    "ALRS",
    "ASTR",
    "BANEP",
    "BELU",
    "BSPB",
    "CBOM",
    "CHMF",
    "CNRU",
    "DATA",
    "DIAS",
    "DOMRF",
    "ENPG",
    "ETLN",
    "EUTR",
    "FEES",
    "FESH",
    "FIXR",
    "FLOT",
    "GAZP",
    "GMKN",
    "HEAD",
    "IRAO",
    "IVAT",
    "LENT",
    "LKOH",
    "LSNGP",
    "LSRG",
    "MAGN",
    "MGNT",
    "MOEX",
    "MRKC",
    "MRKV",
    "MSNG",
    "MTLR",
    "MTLRP",
    "MTSS",
    "MVID",
    "NLMK",
    "NMTP",
    "NVTK",
    "OZON",
    "PHOR",
    "PIKK",
    "PLZL",
    "POSI",
    "RAGR",
    "RASP",
    "RENI",
    "RNFT",
    "ROSN",
    "RTKM",
    "RUAL",
    "SBER",
    "SBERP",
    "SELG",
    "SFIN",
    "SGZH",
    "SIBN",
    "SMLT",
    "SNGS",
    "SNGSP",
    "SPBE",
    "SVCB",
    "T",
    "TATN",
    "TATNP",
    "TRMK",
    "TRNFP",
    "UGLD",
    "UPRO",
    "VKCO",
    "VTBR",
    "WUSH",
    "X5",
    "YDEX",
)

MOEX_INDEX_FUTURE_SYMBOLS = (
    ("IMOEX", "IMOEX · MOEX Russia Index"),
    ("RTSI", "RTSI · RTS Index"),
    ("IMOEXF", "IMOEXF · IMOEX Futures"),
    ("MXM6", "MXM6 · MOEX Index Futures"),
    ("MXU6", "MXU6 · MOEX Index Futures"),
    ("MXZ6", "MXZ6 · MOEX Index Futures"),
    ("RIM6", "RIM6 · RTS Index Futures"),
    ("RIU6", "RIU6 · RTS Index Futures"),
    ("RIZ6", "RIZ6 · RTS Index Futures"),
)


def default_live_symbols() -> list[LiveSymbol]:
    symbols: list[LiveSymbol] = []
    symbols.extend(_symbols_for_market("crypto_spot", CRYPTO_SYMBOLS))
    symbols.extend(_symbols_for_market("cme_futures", US_MARKET_SYMBOLS))
    symbols.extend(_symbols_for_market("commodities", COMMODITY_SYMBOLS))
    symbols.extend(_symbols_for_market("mag7_stocks", MAG7_SYMBOLS))
    symbols.extend(_symbols_for_market("hong_kong_stocks", HONG_KONG_SYMBOLS))
    symbols.extend(
        LiveSymbol(
            market="russian_bluechips",
            symbol=symbol,
            label=symbol,
            sort_order=index,
        )
        for index, symbol in enumerate(MOEX_BLUECHIP_SYMBOLS)
    )
    symbols.extend(_symbols_for_market("russian_indices_futures", MOEX_INDEX_FUTURE_SYMBOLS))
    return symbols


def _symbols_for_market(
    market: str,
    symbol_pairs: Sequence[tuple[str, str]],
) -> list[LiveSymbol]:
    return [
        LiveSymbol(market=market, symbol=symbol, label=label, sort_order=index)
        for index, (symbol, label) in enumerate(symbol_pairs)
    ]


class InMemoryLiveSymbolStore:
    def __init__(self) -> None:
        self._symbols: dict[tuple[str, str], LiveSymbol] = {}

    def ensure_schema(self) -> None:
        return None

    def seed_default_symbols(self) -> None:
        self.upsert_symbols(default_live_symbols())

    def upsert_symbols(self, symbols: Sequence[LiveSymbol]) -> int:
        before = set(self._symbols)
        for symbol in symbols:
            normalized = normalize_live_symbol(symbol)
            self._symbols[(normalized.market, normalized.symbol)] = normalized
        return len(set(self._symbols) - before)

    def list_symbols(self) -> list[LiveSymbol]:
        return sorted(
            self._symbols.values(),
            key=lambda symbol: (symbol.market, symbol.sort_order, symbol.symbol),
        )


class PostgresLiveSymbolStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS live_symbols (
                        market TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        label TEXT NOT NULL,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        PRIMARY KEY (market, symbol)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS live_symbols_market_sort_idx
                    ON live_symbols(market, sort_order, symbol)
                    """
                )

    def seed_default_symbols(self) -> None:
        self.upsert_symbols(default_live_symbols())

    def upsert_symbols(self, symbols: Sequence[LiveSymbol]) -> int:
        changed = 0
        with self._connect() as conn:
            with conn.cursor() as cursor:
                for symbol in symbols:
                    normalized = normalize_live_symbol(symbol)
                    cursor.execute(
                        """
                        INSERT INTO live_symbols (
                            market,
                            symbol,
                            label,
                            sort_order,
                            updated_at
                        )
                        VALUES (%s, %s, %s, %s, now())
                        ON CONFLICT (market, symbol) DO UPDATE
                        SET label = EXCLUDED.label,
                            sort_order = EXCLUDED.sort_order,
                            updated_at = now()
                        """,
                        (
                            normalized.market,
                            normalized.symbol,
                            normalized.label,
                            normalized.sort_order,
                        ),
                    )
                    changed += int(cursor.rowcount or 0)
        return changed

    def list_symbols(self) -> list[LiveSymbol]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT market,
                           symbol,
                           label,
                           sort_order
                    FROM live_symbols
                    ORDER BY market, sort_order, symbol
                    """
                )
                rows = cursor.fetchall()
        return [live_symbol_from_row(row) for row in rows]

    def _connect(self):
        import psycopg  # type: ignore[import-not-found]

        return psycopg.connect(self.database_url)


def normalize_live_symbol(symbol: LiveSymbol) -> LiveSymbol:
    market = symbol.market.strip().lower()
    value = symbol.symbol.strip().upper()
    label = symbol.label.strip() or value
    if not market:
        raise ValueError("symbol market is required")
    if not value:
        raise ValueError("symbol is required")
    return LiveSymbol(
        market=market,
        symbol=value,
        label=label,
        sort_order=int(symbol.sort_order),
    )


def live_symbol_from_row(row: Sequence[object]) -> LiveSymbol:
    return LiveSymbol(
        market=str(row[0]),
        symbol=str(row[1]),
        label=str(row[2]),
        sort_order=int(str(row[3])),
    )


def live_symbols_payload(store: LiveSymbolStore) -> dict[str, object]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for symbol in store.list_symbols():
        grouped.setdefault(symbol.market, []).append(
            {
                "value": symbol.symbol,
                "label": symbol.label,
            }
        )
    return {"ok": True, "symbols": grouped}


def live_symbol_store_from_env() -> LiveSymbolStore:
    load_env_file()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    store: LiveSymbolStore
    if database_url:
        store = PostgresLiveSymbolStore(database_url)
    else:
        store = InMemoryLiveSymbolStore()
    store.ensure_schema()
    store.seed_default_symbols()
    return store
