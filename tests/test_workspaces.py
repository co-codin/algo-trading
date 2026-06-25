import unittest

from algo_trading.workspaces import InMemoryWorkspaceStore


class WorkspaceStoreTests(unittest.TestCase):
    def test_watchlists_are_saved_and_deleted_per_user(self):
        store = InMemoryWorkspaceStore()
        store.ensure_schema()

        watchlist = store.create_watchlist(
            user_id=7,
            name="Asia tech",
            market="hong_kong_stocks",
            symbols=["9988.HK", "9888.HK", "0700.HK"],
        )
        store.create_watchlist(
            user_id=8,
            name="Crypto",
            market="crypto_spot",
            symbols=["BTCUSDT"],
        )
        updated = store.update_watchlist(
            user_id=7,
            watchlist_id=watchlist.id,
            name="HK tech",
            market="hong_kong_stocks",
            symbols=["9988.HK", "0700.HK"],
        )

        self.assertEqual(updated.symbols, ["9988.HK", "0700.HK"])
        self.assertEqual(store.delete_watchlist(7, watchlist.id), True)
        self.assertEqual(store.list_watchlists(7), [])
        self.assertEqual(len(store.list_watchlists(8)), 1)

    def test_workspace_validation_rejects_empty_names_and_settings(self):
        store = InMemoryWorkspaceStore()

        with self.assertRaisesRegex(ValueError, "workspace name is required"):
            store.create_workspace(
                user_id=7,
                name=" ",
                market="crypto_spot",
                symbol="BTCUSDT",
                settings={"interval": "1h"},
            )
        with self.assertRaisesRegex(ValueError, "workspace settings are required"):
            store.create_workspace(
                user_id=7,
                name="BTC",
                market="crypto_spot",
                symbol="BTCUSDT",
                settings=[],
            )

    def test_watchlist_validation_rejects_empty_symbol_lists(self):
        store = InMemoryWorkspaceStore()

        with self.assertRaisesRegex(ValueError, "watchlist symbols are required"):
            store.create_watchlist(
                user_id=7,
                name="Empty",
                market="crypto_spot",
                symbols=[],
            )


if __name__ == "__main__":
    unittest.main()
