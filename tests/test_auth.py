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
        self.assertIsNone(user.free_trial_end_at)
        self.assertFalse(user.is_admin)
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
                "is_admin": False,
                "first_name": None,
                "last_name": None,
                "middle_name": None,
                "free_trial_end_at": None,
            },
        )
        with self.assertRaisesRegex(ValueError, "username already exists"):
            store.register_user("alice", "password123")

    def test_memory_store_free_trial_flag_grants_active_trial_registration(self):
        store = InMemoryAuthStore()

        self.assertFalse(store.is_free_trial_enabled())
        self.assertTrue(store.set_free_trial_enabled(True))
        before = utcnow()
        user = store.register_user("trial@example.com", "password123")
        after = utcnow()

        self.assertTrue(user.is_active)
        self.assertIsNotNone(user.activated_at)
        self.assertIsNone(user.expired_at)
        self.assertIsNotNone(user.free_trial_end_at)
        self.assertGreaterEqual(user.free_trial_end_at, before + timedelta(days=7))
        self.assertLessEqual(user.free_trial_end_at, after + timedelta(days=7))
        payload = public_user(user)
        self.assertTrue(payload["is_active"])
        self.assertIsNotNone(payload["free_trial_end_at"])

    def test_memory_store_deactivates_users_after_free_trial_end(self):
        store = InMemoryAuthStore()
        store.set_free_trial_enabled(True)
        user = store.register_user("trial@example.com", "password123")
        assert user.free_trial_end_at is not None

        deactivated = store.deactivate_expired_users(
            now=user.free_trial_end_at + timedelta(seconds=1)
        )

        users = store.list_users()
        self.assertEqual(deactivated, 1)
        self.assertFalse(users[0].is_active)
        self.assertIsNone(users[0].activated_at)
        self.assertEqual(users[0].free_trial_end_at, user.free_trial_end_at)

    def test_memory_store_manual_activation_clears_finished_free_trial(self):
        store = InMemoryAuthStore()
        store.set_free_trial_enabled(True)
        user = store.register_user("trial@example.com", "password123")
        assert user.free_trial_end_at is not None
        after_trial = user.free_trial_end_at + timedelta(seconds=1)
        store.deactivate_expired_users(now=after_trial)

        reactivated = store.set_user_access(
            user.id,
            is_active=True,
            activated_at=after_trial,
        )
        deactivated_again = store.deactivate_expired_users(
            now=after_trial + timedelta(days=1)
        )

        self.assertTrue(reactivated.is_active)
        self.assertIsNone(reactivated.free_trial_end_at)
        self.assertEqual(deactivated_again, 0)
        self.assertTrue(store.list_users()[0].is_active)

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

    def test_memory_store_seeds_admin_with_configured_password(self):
        store = InMemoryAuthStore()

        seeded = store.seed_admin_user(
            "cuiyeqing960904@gmail.com",
            "admin-test-password-123",
        )

        self.assertTrue(seeded.is_admin)
        self.assertTrue(seeded.is_active)
        self.assertIsNotNone(seeded.activated_at)
        authenticated = store.authenticate_user(
            "cuiyeqing960904@gmail.com",
            "admin-test-password-123",
        )
        self.assertEqual(authenticated.id, seeded.id)
        self.assertTrue(authenticated.is_admin)

    def test_memory_store_promotes_existing_seed_admin_without_resetting_password(self):
        store = InMemoryAuthStore()
        user = store.register_user("cuiyeqing960904@gmail.com", "oldpassword")

        seeded = store.seed_admin_user(
            "cuiyeqing960904@gmail.com",
            "admin-test-password-123",
        )

        self.assertEqual(seeded.id, user.id)
        self.assertTrue(seeded.is_admin)
        self.assertEqual(
            store.authenticate_user("cuiyeqing960904@gmail.com", "oldpassword"),
            seeded,
        )
        with self.assertRaisesRegex(ValueError, "invalid username or password"):
            store.authenticate_user(
                "cuiyeqing960904@gmail.com",
                "admin-test-password-123",
            )

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
