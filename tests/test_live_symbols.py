import unittest

from algo_trading.live_symbols import (
    InMemoryLiveSymbolStore,
    LiveSymbol,
    live_symbols_payload,
)


class LiveSymbolTests(unittest.TestCase):
    def test_default_symbols_are_seeded_into_store(self):
        store = InMemoryLiveSymbolStore()
        store.ensure_schema()
        store.seed_default_symbols()

        payload = live_symbols_payload(store)
        symbols = payload["symbols"]
        russian_symbols = payload["russian_symbols"]

        self.assertEqual(symbols["crypto_spot"][0], {"value": "BTCUSDT", "label": "BTCUSDT"})
        self.assertEqual(symbols["crypto_spot"][1], {"value": "ETHUSDT", "label": "ETHUSDT"})
        crypto_values = {str(option["value"]) for option in symbols["crypto_spot"]}
        for symbol in (
            "SOLUSDT",
            "BNBUSDT",
            "XRPUSDT",
            "DOGEUSDT",
            "ADAUSDT",
            "AVAXUSDT",
            "LINKUSDT",
            "TONUSDT",
        ):
            self.assertIn(symbol, crypto_values)
        self.assertIn(
            {"value": "SPY", "label": "SPY · S&P 500 ETF"},
            symbols["cme_futures"],
        )
        self.assertIn(
            {"value": "QQQ", "label": "QQQ · Nasdaq 100 ETF"},
            symbols["cme_futures"],
        )
        self.assertIn(
            {"value": "DIA", "label": "DIA · Dow Jones ETF"},
            symbols["cme_futures"],
        )
        self.assertNotIn("russian_bluechips", symbols)
        self.assertNotIn("russian_indices_futures", symbols)
        self.assertIn("russian_bluechips", russian_symbols)
        self.assertIn(
            {"value": "IMOEX", "label": "IMOEX · MOEX Russia Index"},
            russian_symbols["russian_indices_futures"],
        )
        self.assertIn(
            {"value": "RIM6", "label": "RIM6 · RTS Index Futures"},
            russian_symbols["russian_indices_futures"],
        )

    def test_store_keeps_database_symbols_alongside_seed_defaults(self):
        store = InMemoryLiveSymbolStore()
        store.ensure_schema()
        store.upsert_symbols(
            [
                LiveSymbol(
                    market="crypto_spot",
                    symbol="DOGEUSDT",
                    label="DOGEUSDT",
                    sort_order=99,
                )
            ]
        )

        store.seed_default_symbols()
        payload = live_symbols_payload(store)

        self.assertIn(
            {"value": "DOGEUSDT", "label": "DOGEUSDT"},
            payload["symbols"]["crypto_spot"],
        )


if __name__ == "__main__":
    unittest.main()
