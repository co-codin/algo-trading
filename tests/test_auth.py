import unittest
from datetime import timedelta

from algo_trading.auth import InMemoryAuthStore, hash_password, public_user, utcnow, verify_password


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
        self.assertFalse(user.is_active)
        self.assertIsNone(user.activated_at)
        self.assertIsNone(user.expired_at)
        self.assertIsNone(user.first_name)
        self.assertIsNone(user.last_name)
        self.assertIsNone(user.middle_name)
        self.assertEqual(
            public_user(user),
            {
                "id": user.id,
                "username": "alice",
                "is_active": False,
                "activated_at": None,
                "expired_at": None,
                "first_name": None,
                "last_name": None,
                "middle_name": None,
            },
        )
        with self.assertRaisesRegex(ValueError, "username already exists"):
            store.register_user("alice", "password123")

    def test_memory_store_updates_profile_names(self):
        store = InMemoryAuthStore()
        user = store.register_user("alice", "password123")

        updated = store.update_user_profile(
            user.id,
            first_name=" Alice ",
            last_name=" Liddell ",
            middle_name="  ",
        )

        self.assertEqual(updated.first_name, "Alice")
        self.assertEqual(updated.last_name, "Liddell")
        self.assertIsNone(updated.middle_name)
        self.assertEqual(store.list_users()[0], updated)

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

    def test_memory_store_lists_users_and_deactivates_expired_users(self):
        store = InMemoryAuthStore()
        expired_user = store.register_user("expired@example.com", "password123")
        fresh_user = store.register_user("fresh@example.com", "password123")
        now = utcnow()
        store.set_user_access(
            expired_user.id,
            is_active=True,
            activated_at=now - timedelta(days=30),
            expired_at=now - timedelta(seconds=1),
        )
        store.set_user_access(
            fresh_user.id,
            is_active=True,
            activated_at=now - timedelta(days=1),
            expired_at=now + timedelta(days=1),
        )

        deactivated = store.deactivate_expired_users(now=now)

        users = store.list_users()
        self.assertEqual(deactivated, 1)
        self.assertEqual([user.username for user in users], ["expired@example.com", "fresh@example.com"])
        self.assertFalse(users[0].is_active)
        self.assertIsNone(users[0].activated_at)
        self.assertTrue(users[1].is_active)
        self.assertEqual(users[1].expired_at, now + timedelta(days=1))

    def test_memory_store_expires_sessions(self):
        store = InMemoryAuthStore(session_ttl_seconds=-1)
        user = store.register_user("alice", "password123")

        token = store.create_session(user.id)

        self.assertIsNone(store.user_for_session(token))


if __name__ == "__main__":
    unittest.main()
