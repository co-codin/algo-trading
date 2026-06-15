import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from algo_trading.auth import InMemoryAuthStore
from algo_trading.web_app import create_app


class WebAppTests(unittest.TestCase):
    def make_client(self) -> TestClient:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        app = create_app(
            output_root=Path(tempdir.name),
            auth_store=InMemoryAuthStore(),
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

    def test_register_sets_session_cookie_and_allows_trading_api(self):
        client = self.make_client()

        response = client.post(
            "/api/auth/register",
            json={"username": " Alice ", "password": "password123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "alice")
        self.assertIn("algo_session=", response.headers["set-cookie"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
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
        self.assertEqual(client.get("/api/strategies").status_code, 200)

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

    def test_spa_routes_are_public_before_login(self):
        client = self.make_client()

        response = client.get("/live")

        self.assertEqual(response.status_code, 200)
        self.assertIn("<div id=\"app\"></div>", response.text)


if __name__ == "__main__":
    unittest.main()
