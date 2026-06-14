import unittest

from algo_trading.symbols import parse_symbol_list, ranked_usdt_symbols


class SymbolTests(unittest.TestCase):
    def test_ranked_usdt_symbols_excludes_non_crypto_and_sorts_by_quote_volume(self):
        tickers = [
            {"symbol": "USDCUSDT", "quoteVolume": "999", "lastPrice": "1.0"},
            {"symbol": "XAUTUSDT", "quoteVolume": "900", "lastPrice": "4200"},
            {"symbol": "ETHBTC", "quoteVolume": "800", "lastPrice": "0.02"},
            {"symbol": "ETHUSDT", "quoteVolume": "200", "lastPrice": "1700"},
            {"symbol": "BTCUSDT", "quoteVolume": "500", "lastPrice": "65000"},
            {"symbol": "DOGEUSDT", "quoteVolume": "50", "lastPrice": "0.1"},
        ]

        symbols = ranked_usdt_symbols(tickers, limit=3)

        self.assertEqual(
            [item.symbol for item in symbols],
            ["BTCUSDT", "ETHUSDT", "DOGEUSDT"],
        )
        self.assertEqual(symbols[0].base_asset, "BTC")
        self.assertEqual(symbols[0].quote_volume, 500.0)

    def test_parse_symbol_list_normalizes_comma_separated_symbols(self):
        self.assertEqual(
            parse_symbol_list(" btcusdt, ethusdt ,solusdt "),
            ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        )


if __name__ == "__main__":
    unittest.main()
