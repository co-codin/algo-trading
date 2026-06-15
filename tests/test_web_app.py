import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from algo_trading.auth import InMemoryAuthStore, utcnow
from algo_trading.web_app import create_app


class WebAppTests(unittest.TestCase):
    def make_client(self, **overrides: Any) -> TestClient:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        auth_store = overrides.pop("auth_store", InMemoryAuthStore())
        app = create_app(
            output_root=Path(tempdir.name),
            auth_store=auth_store,
            **overrides,
        )
        return TestClient(app)

    def test_trading_api_requires_authentication(self):
        client = self.make_client()

        response = client.get("/api/strategies")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {"ok": False, "error": "authentication required"},
        )

    def test_register_sets_inactive_session_and_blocks_trading_api(self):
        client = self.make_client()

        response = client.post(
            "/api/auth/register",
            json={"username": " Alice ", "password": "password123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "alice")
        self.assertFalse(response.json()["user"]["is_active"])
        self.assertIsNone(response.json()["user"]["activated_at"])
        self.assertIsNone(response.json()["user"]["expired_at"])
        self.assertIn("algo_session=", response.headers["set-cookie"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        protected = client.get("/api/strategies")
        self.assertEqual(protected.status_code, 403)
        self.assertEqual(protected.json(), {"ok": False, "error": "account inactive"})
        profile = client.get("/api/profile")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["user"]["username"], "alice")

    def test_active_user_can_access_trading_api(self):
        store = InMemoryAuthStore()
        client = self.make_client(auth_store=store)
        client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "password123"},
        )
        user = store.list_users()[0]
        store.set_user_access(user.id, is_active=True, activated_at=utcnow())

        protected = client.get("/api/strategies")

        self.assertEqual(protected.status_code, 200)
        self.assertTrue(protected.json()["ok"])

    def test_login_and_logout_manage_session_access(self):
        client = self.make_client()
        client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "password123"},
        )
        client.post("/api/auth/logout")

        self.assertEqual(client.get("/api/strategies").status_code, 401)

        login = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200)
        user = client.get("/api/auth/me").json()["user"]
        self.assertFalse(user["is_active"])
        self.assertEqual(client.get("/api/strategies").status_code, 403)

        logout = client.post("/api/auth/logout")
        self.assertEqual(logout.status_code, 200)
        self.assertIn("algo_session=", logout.headers["set-cookie"])
        self.assertEqual(client.get("/api/strategies").status_code, 401)

    def test_auth_me_is_public_and_reports_current_user(self):
        client = self.make_client()

        anonymous = client.get("/api/auth/me")
        self.assertEqual(anonymous.status_code, 200)
        self.assertEqual(anonymous.json(), {"ok": True, "user": None})

        client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "password123"},
        )
        authenticated = client.get("/api/auth/me")

        self.assertEqual(authenticated.status_code, 200)
        self.assertEqual(authenticated.json()["user"]["username"], "alice")
        self.assertIn("is_active", authenticated.json()["user"])

    def test_spa_routes_are_public_before_login(self):
        client = self.make_client()

        response = client.get("/live")

        self.assertEqual(response.status_code, 200)
        self.assertIn("<div id=\"app\"></div>", response.text)

    def test_market_breadth_api_requires_authentication(self):
        client = self.make_client()

        response = client.get("/api/market-breadth")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {"ok": False, "error": "authentication required"},
        )

    def test_market_breadth_api_returns_service_payload_after_login(self):
        class FakeMarketBreadthService:
            def __init__(self) -> None:
                self.symbols: list[str] | None = None

            def payload(self, symbols: list[str] | None = None) -> dict[str, object]:
                self.symbols = symbols
                return {
                    "ok": True,
                    "source": "Barchart",
                    "groups": [],
                    "series": {
                        "$S5FD": {
                            "symbol": "$S5FD",
                            "label": "S&P 500 5-day",
                            "data": "daily",
                            "candles": [],
                        }
                    },
                    "put_call_symbol": "$CPC",
                    "updated_at": "2026-06-15T00:00:00+00:00",
                }

        service = FakeMarketBreadthService()
        store = InMemoryAuthStore()
        client = self.make_client(auth_store=store, market_breadth_service=service)
        client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "password123"},
        )
        store.set_user_access(store.list_users()[0].id, is_active=True, activated_at=utcnow())

        response = client.get("/api/market-breadth?symbols=$S5FD,$CPC")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["series"]["$S5FD"]["data"], "daily")
        self.assertEqual(service.symbols, ["$S5FD", "$CPC"])

    def test_admin_users_requires_admin_email_and_lists_all_users(self):
        store = InMemoryAuthStore()
        client = self.make_client(auth_store=store)
        client.post(
            "/api/auth/register",
            json={"username": "alice@example.com", "password": "password123"},
        )

        forbidden = client.get("/api/admin/users")
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.json(), {"ok": False, "error": "admin required"})

        client.post("/api/auth/logout")
        client.post(
            "/api/auth/register",
            json={"username": "cuiyeqing960904@gmail.com", "password": "password123"},
        )
        response = client.get("/api/admin/users")

        self.assertEqual(response.status_code, 200)
        users = response.json()["users"]
        self.assertEqual(
            [user["username"] for user in users],
            ["alice@example.com", "cuiyeqing960904@gmail.com"],
        )
        self.assertFalse(users[0]["is_active"])
        self.assertIsNone(users[0]["expired_at"])

    def test_expired_active_user_is_deactivated_before_feature_access(self):
        store = InMemoryAuthStore()
        client = self.make_client(auth_store=store)
        client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "password123"},
        )
        user = store.list_users()[0]
        store.set_user_access(
            user.id,
            is_active=True,
            activated_at=utcnow() - timedelta(days=2),
            expired_at=utcnow() - timedelta(seconds=1),
        )

        response = client.get("/api/strategies")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"ok": False, "error": "account inactive"})
        self.assertFalse(store.list_users()[0].is_active)


if __name__ == "__main__":
    unittest.main()
