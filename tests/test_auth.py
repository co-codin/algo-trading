import unittest

from algo_trading.auth import InMemoryAuthStore, hash_password, verify_password


class AuthTests(unittest.TestCase):
    def test_password_hashing_uses_salt_and_verifies_password(self):
        password_hash = hash_password("correct horse battery staple")

        self.assertNotEqual(password_hash, "correct horse battery staple")
        self.assertTrue(verify_password("correct horse battery staple", password_hash))
        self.assertFalse(verify_password("wrong password", password_hash))

    def test_memory_store_registers_normalized_user_and_rejects_duplicates(self):
        store = InMemoryAuthStore()

        user = store.register_user(" Alice ", "password123")

        self.assertEqual(user.username, "alice")
        with self.assertRaisesRegex(ValueError, "username already exists"):
            store.register_user("alice", "password123")

    def test_memory_store_validates_usernames_and_passwords(self):
        store = InMemoryAuthStore()

        with self.assertRaisesRegex(ValueError, "username must be at least 3 characters"):
            store.register_user("ab", "password123")
        with self.assertRaisesRegex(ValueError, "password must be at least 8 characters"):
            store.register_user("alice", "short")

    def test_memory_store_authenticates_without_leaking_login_failures(self):
        store = InMemoryAuthStore()
        registered = store.register_user("alice", "password123")

        authenticated = store.authenticate_user("ALICE", "password123")

        self.assertEqual(authenticated.id, registered.id)
        with self.assertRaisesRegex(ValueError, "invalid username or password"):
            store.authenticate_user("alice", "wrong-password")
        with self.assertRaisesRegex(ValueError, "invalid username or password"):
            store.authenticate_user("missing", "password123")

    def test_memory_store_creates_and_deletes_sessions_by_token(self):
        store = InMemoryAuthStore()
        user = store.register_user("alice", "password123")

        token = store.create_session(user.id)

        self.assertGreater(len(token), 32)
        self.assertEqual(store.user_for_session(token), user)
        self.assertIsNone(store.user_for_session("not-a-real-token"))
        store.delete_session(token)
        self.assertIsNone(store.user_for_session(token))

    def test_memory_store_expires_sessions(self):
        store = InMemoryAuthStore(session_ttl_seconds=-1)
        user = store.register_user("alice", "password123")

        token = store.create_session(user.id)

        self.assertIsNone(store.user_for_session(token))


if __name__ == "__main__":
    unittest.main()
