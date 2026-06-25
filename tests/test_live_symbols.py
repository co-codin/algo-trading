import unittest

from algo_trading.live_symbols import (
    InMemoryLiveSymbolStore,
    LiveSymbol,
    live_symbols_payload,
)


class LiveSymbolTests(unittest.TestCase):
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
