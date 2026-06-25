import logging
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from algo_trading.auth import InMemoryAuthStore, utcnow
from algo_trading.feedback import InMemoryFeedbackStore
from algo_trading.historical_store import InMemoryHistoricalDataStore
from algo_trading.models import Candle
from algo_trading.web_app import admin_password, create_app
from algo_trading.workspaces import InMemoryWorkspaceStore


class WebAppTests(unittest.TestCase):
    def tearDown(self) -> None:
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            if getattr(handler, "_algo_trading_log_path", None):
                root_logger.removeHandler(handler)
                handler.close()

    def make_client(self, **overrides: Any) -> TestClient:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        auth_store = overrides.pop("auth_store", InMemoryAuthStore())
        overrides.setdefault("seed_admin", False)
        app = create_app(
            output_root=Path(tempdir.name),
            auth_store=auth_store,
            **overrides,
        )
        return TestClient(app)

    def test_admin_password_has_no_runtime_default(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "ADMIN_PASSWORD must be set"):
                admin_password()

    def test_market_breadth_api_uses_response_cache_after_first_success(self):
        class FakeResponseCache:
            def __init__(self) -> None:
                self.values: dict[str, dict[str, Any]] = {}
                self.set_calls: list[tuple[str, int]] = []

            def get_json(self, key: str) -> dict[str, Any] | None:
                return self.values.get(key)

            def set_json(
                self,
                key: str,
                payload: dict[str, Any],
                *,
                ttl_seconds: int,
            ) -> None:
                self.values[key] = payload
                self.set_calls.append((key, ttl_seconds))

        class FakeMarketBreadthService:
            def __init__(self) -> None:
                self.calls = 0

            def payload(self, symbols: list[str] | None = None) -> dict[str, Any]:
                self.calls += 1
                return {
                    "ok": True,
                    "source": "Barchart",
                    "groups": [],
                    "series": {},
                    "put_call_symbol": "$CPC",
                    "requested_symbols": symbols,
                    "calls": self.calls,
                }

        auth_store = InMemoryAuthStore()
        cache = FakeResponseCache()
        service = FakeMarketBreadthService()
        client = self.make_client(
            auth_store=auth_store,
            market_breadth_service=service,
            response_cache=cache,
        )
        client.post(
            "/api/auth/register",
            json={"username": "alice@example.com", "password": "password123"},
        )
        auth_store.set_user_access(
            auth_store.list_users()[0].id,
            is_active=True,
            activated_at=utcnow(),
        )

        first = client.get("/api/market-breadth?symbols=$S5FD,$CPC")
        second = client.get("/api/market-breadth?symbols=$S5FD,$CPC")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["calls"], 1)
        self.assertEqual(second.json()["calls"], 1)
        self.assertEqual(service.calls, 1)
        self.assertEqual(len(cache.set_calls), 1)
        self.assertEqual(cache.set_calls[0][1], 300)

    def test_api_response_cache_failures_are_logged_and_nonfatal(self):
        class FailingResponseCache:
            def get_json(self, key: str) -> dict[str, Any] | None:
                raise RuntimeError(f"redis get failed for {key}")

            def set_json(
                self,
                key: str,
                payload: dict[str, Any],
                *,
                ttl_seconds: int,
            ) -> None:
                raise RuntimeError(f"redis set failed for {key}")

        class FakeMarketBreadthService:
            def payload(self, symbols: list[str] | None = None) -> dict[str, Any]:
                return {
                    "ok": True,
                    "source": "Barchart",
                    "groups": [],
                    "series": {},
                    "put_call_symbol": "$CPC",
                    "requested_symbols": symbols,
                }

        with tempfile.TemporaryDirectory() as tempdir:
            log_dir = Path(tempdir) / "logs"
            auth_store = InMemoryAuthStore()
            client = self.make_client(
                auth_store=auth_store,
                market_breadth_service=FakeMarketBreadthService(),
                response_cache=FailingResponseCache(),
                log_dir=log_dir,
            )
            client.post(
                "/api/auth/register",
                json={"username": "alice@example.com", "password": "password123"},
            )
            auth_store.set_user_access(
                auth_store.list_users()[0].id,
                is_active=True,
                activated_at=utcnow(),
            )

            response = client.get("/api/market-breadth?symbols=$S5FD")
            content = (log_dir / "app.log").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("API response cache get failed for market-breadth", content)
        self.assertIn("API response cache set failed for market-breadth", content)

    def test_live_chart_api_uses_short_response_cache(self):
        class FakeResponseCache:
            def __init__(self) -> None:
                self.values: dict[str, dict[str, Any]] = {}
                self.set_ttls: list[int] = []

            def get_json(self, key: str) -> dict[str, Any] | None:
                return self.values.get(key)

            def set_json(
                self,
                key: str,
                payload: dict[str, Any],
                *,
                ttl_seconds: int,
            ) -> None:
                self.values[key] = payload
                self.set_ttls.append(ttl_seconds)

        class FakeMarketClient:
            calls = 0

            def get_24h_tickers(self) -> list[dict[str, object]]:
                return []

            def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
                self.__class__.calls += 1
                prices = [10, 9, 8, 7, 8]
                return [
                    Candle(
                        open_time=index,
                        open=price,
                        high=price + 1.0,
                        low=price - 1.0,
                        close=price,
                        volume=1.0,
                    )
                    for index, price in enumerate(prices)
                ][:limit]

        auth_store = InMemoryAuthStore()
        cache = FakeResponseCache()
        client = self.make_client(
            auth_store=auth_store,
            client_factory=FakeMarketClient,
            historical_store=InMemoryHistoricalDataStore(),
            response_cache=cache,
        )
        client.post(
            "/api/auth/register",
            json={"username": "alice@example.com", "password": "password123"},
        )
        user = auth_store.list_users()[0]
        auth_store.set_user_access(user.id, is_active=True, activated_at=utcnow())

        query = (
            "/api/live-chart?symbol=BTCUSDT&interval=5m&limit=5"
            "&strategy=ema-rsi&rsi_period=2&rsi_overbought=100&rsi_oversold=0"
        )
        first = client.get(query)
        second = client.get(query)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(FakeMarketClient.calls, 1)
        self.assertEqual(cache.set_ttls, [10])

    def test_unexpected_api_errors_are_written_to_app_log(self):
        def failing_client_factory() -> Any:
            raise RuntimeError("simulated route failure")

        with tempfile.TemporaryDirectory() as tempdir:
            log_dir = Path(tempdir) / "logs"
            auth_store = InMemoryAuthStore()
            app = create_app(
                output_root=Path(tempdir) / "runs",
                auth_store=auth_store,
                client_factory=failing_client_factory,
                seed_admin=False,
                log_dir=log_dir,
            )
            client = TestClient(app, raise_server_exceptions=False)
            client.post(
                "/api/auth/register",
                json={"username": "alice", "password": "password123"},
            )
            auth_store.set_user_access(
                auth_store.list_users()[0].id,
                is_active=True,
                activated_at=utcnow(),
            )
            response = client.get("/api/live-chart?symbol=BTCUSDT&interval=5m&limit=10")

            self.assertEqual(response.status_code, 500)
            self.assertEqual(
                response.json(),
                {"ok": False, "error": "simulated route failure"},
            )
            content = (log_dir / "app.log").read_text(encoding="utf-8")

        self.assertIn("Unhandled API error GET /api/live-chart", content)
        self.assertIn("RuntimeError: simulated route failure", content)

    def test_trading_api_requires_authentication(self):
        client = self.make_client()

        response = client.get("/api/strategies")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {"ok": False, "error": "authentication required"},
        )

    def test_active_user_can_load_quant_strategy_ideas(self):
        class FakeMarketClient:
            def get_24h_tickers(self) -> list[dict[str, object]]:
                return []

            def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
                return [
                    Candle(
                        open_time=index,
                        open=float(100 + index),
                        high=float(101 + index),
                        low=float(99 + index),
                        close=float(100 + index),
                        volume=100.0,
                    )
                    for index in range(limit)
                ]

        auth_store = InMemoryAuthStore()
        history_store = InMemoryHistoricalDataStore()
        client = self.make_client(
            auth_store=auth_store,
            historical_store=history_store,
            client_factory=FakeMarketClient,
        )
        client.post(
            "/api/auth/register",
            json={"username": "alice@example.com", "password": "password123"},
        )
        user = auth_store.list_users()[0]

        inactive = client.get("/api/quant-strategies?symbol=BTCUSDT&interval=1h&limit=80")
        self.assertEqual(inactive.status_code, 403)

        auth_store.set_user_access(user.id, is_active=True, activated_at=utcnow())
        active = client.get("/api/quant-strategies?symbol=BTCUSDT&interval=1h&limit=80")

        self.assertEqual(active.status_code, 200)
        payload = active.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["symbol"], "BTCUSDT")
        self.assertEqual(payload["market"], "crypto_spot")
        self.assertEqual(payload["interval"], "1h")
        self.assertEqual(len(payload["candles"]), 80)
        self.assertIn("signals", payload)
        self.assertIn("indicators", payload)
        idea_ids = {idea["id"] for idea in payload["ideas"]}
        self.assertIn("time-series-momentum", idea_ids)
        self.assertIn("rsi-mean-reversion", idea_ids)
        self.assertEqual(
            next(
                idea
                for idea in payload["ideas"]
                if idea["id"] == "time-series-momentum"
            )["action"],
            "bullish",
        )

    def test_workspace_api_requires_active_user(self):
        client = self.make_client(workspace_store=InMemoryWorkspaceStore())
        client.post(
            "/api/auth/register",
            json={"username": "inactive@example.com", "password": "password123"},
        )

        response = client.get("/api/workspaces")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"ok": False, "error": "account inactive"})

    def test_register_sets_inactive_session_and_blocks_trading_api(self):
        client = self.make_client()

        response = client.post(
            "/api/auth/register",
            json={"username": " Alice ", "password": "password123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "alice")
        self.assertFalse(response.json()["user"]["is_active"])
        self.assertFalse(response.json()["user"]["is_admin"])
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
        self.assertIsNone(profile.json()["user"]["first_name"])

    def test_platform_admin_can_toggle_free_trial_for_new_registrations(self):
        store = InMemoryAuthStore()
        client = self.make_client(
            auth_store=store,
            seed_admin=True,
            admin_seed_password="admin-test-password-123",
        )
        store.seed_admin_user("other-admin@example.com", "password123")

        client.post(
            "/api/auth/login",
            json={"username": "other-admin@example.com", "password": "password123"},
        )
        forbidden = client.put(
            "/api/admin/settings/free-trial",
            json={"is_free_trial_enabled": True},
        )
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(
            forbidden.json(),
            {"ok": False, "error": "platform admin required"},
        )

        client.post("/api/auth/logout")
        client.post(
            "/api/auth/login",
            json={
                "username": "cuiyeqing960904@gmail.com",
                "password": "admin-test-password-123",
            },
        )

        current = client.get("/api/admin/settings/free-trial")
        self.assertEqual(current.status_code, 200)
        self.assertFalse(current.json()["settings"]["is_free_trial_enabled"])

        updated = client.put(
            "/api/admin/settings/free-trial",
            json={"is_free_trial_enabled": True},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(updated.json()["settings"]["is_free_trial_enabled"])

        client.post("/api/auth/logout")
        registered = client.post(
            "/api/auth/register",
            json={"username": "trial@example.com", "password": "password123"},
        )

        self.assertEqual(registered.status_code, 200)
        user = registered.json()["user"]
        self.assertTrue(user["is_active"])
        self.assertIsNotNone(user["activated_at"])
        self.assertIsNotNone(user["free_trial_end_at"])
        self.assertEqual(client.get("/api/strategies").status_code, 200)

    def test_profile_can_update_name_fields_for_inactive_user(self):
        client = self.make_client()
        client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "password123"},
        )

        response = client.patch(
            "/api/profile",
            json={
                "first_name": " Alice ",
                "last_name": " Liddell ",
                "middle_name": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        user = response.json()["user"]
        self.assertEqual(user["first_name"], "Alice")
        self.assertEqual(user["last_name"], "Liddell")
        self.assertIsNone(user["middle_name"])
        profile = client.get("/api/profile")
        self.assertEqual(profile.json()["user"]["first_name"], "Alice")

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

    def test_feedback_requires_active_user_and_title(self):
        store = InMemoryAuthStore()
        feedback_store = InMemoryFeedbackStore()
        client = self.make_client(auth_store=store, feedback_store=feedback_store)
        client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "password123"},
        )

        inactive = client.post("/api/feedback", json={"title": "Chart bug"})

        self.assertEqual(inactive.status_code, 403)
        self.assertEqual(inactive.json(), {"ok": False, "error": "account inactive"})

        store.set_user_access(store.list_users()[0].id, is_active=True, activated_at=utcnow())
        missing_title = client.post("/api/feedback", json={"title": " "})

        self.assertEqual(missing_title.status_code, 400)
        self.assertEqual(
            missing_title.json(),
            {"ok": False, "error": "feedback title is required"},
        )

    def test_active_user_can_submit_feedback_and_admin_can_update_status(self):
        store = InMemoryAuthStore()
        feedback_store = InMemoryFeedbackStore()
        client = self.make_client(auth_store=store, feedback_store=feedback_store)
        client.post(
            "/api/auth/register",
            json={"username": "alice@example.com", "password": "password123"},
        )
        alice = store.list_users()[0]
        store.set_user_access(alice.id, is_active=True, activated_at=utcnow())

        created = client.post(
            "/api/feedback",
            json={"title": " Chart bug ", "description": ""},
        )

        self.assertEqual(created.status_code, 200)
        feedback = created.json()["feedback"]
        self.assertEqual(feedback["title"], "Chart bug")
        self.assertEqual(feedback["description"], "")
        self.assertEqual(feedback["status"], "open")
        self.assertEqual(feedback["username"], "alice@example.com")

        forbidden = client.get("/api/admin/feedback")
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.json(), {"ok": False, "error": "admin required"})

        client.post("/api/auth/logout")
        store.seed_admin_user("admin@example.com", "admin-test-password-123")
        client.post(
            "/api/auth/login",
            json={"username": "admin@example.com", "password": "admin-test-password-123"},
        )

        listed = client.get("/api/admin/feedback")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["feedback"]), 1)
        self.assertEqual(listed.json()["feedback"][0]["id"], feedback["id"])

        updated = client.patch(
            f"/api/admin/feedback/{feedback['id']}/status",
            json={"status": "in_progress"},
        )

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["feedback"]["status"], "in_progress")
        self.assertEqual(
            client.get("/api/admin/feedback").json()["feedback"][0]["status"],
            "in_progress",
        )

    def test_live_chart_route_persists_fetched_candles_to_historical_store(self):
        class FakeMarketClient:
            def get_24h_tickers(self) -> list[dict[str, object]]:
                return []

            def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
                return [
                    Candle(
                        open_time=1000,
                        open=10,
                        high=11,
                        low=9,
                        close=10,
                        volume=1,
                    ),
                    Candle(
                        open_time=2000,
                        open=11,
                        high=12,
                        low=10,
                        close=11,
                        volume=1,
                    ),
                ][:limit]

        auth_store = InMemoryAuthStore()
        historical_store = InMemoryHistoricalDataStore()
        client = self.make_client(
            auth_store=auth_store,
            client_factory=FakeMarketClient,
            historical_store=historical_store,
        )
        client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "password123"},
        )
        auth_store.set_user_access(
            auth_store.list_users()[0].id,
            is_active=True,
            activated_at=utcnow(),
        )

        response = client.get(
            "/api/live-chart?market=crypto_spot&symbol=BTCUSDT&interval=5m"
            "&limit=2&fast_ema=1&slow_ema=2&rsi_period=2"
            "&rsi_overbought=100&rsi_oversold=0"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [
                stored.open_time
                for stored in historical_store.load_candles(
                    "crypto_spot",
                    "BTCUSDT",
                    "5m",
                )
            ],
            [1000, 2000],
        )

    def test_live_chart_route_returns_stale_cache_then_refreshes_in_background(self):
        class FakeMarketClient:
            kline_calls: list[tuple[str, str, int]] = []

            def get_24h_tickers(self) -> list[dict[str, object]]:
                return []

            def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
                self.kline_calls.append((symbol, interval, limit))
                return [
                    Candle(
                        open_time=3000 + index,
                        open=price,
                        high=price + 1.0,
                        low=price - 1.0,
                        close=price,
                        volume=1.0,
                    )
                    for index, price in enumerate([13, 14])
                ][:limit]

        auth_store = InMemoryAuthStore()
        historical_store = InMemoryHistoricalDataStore()
        historical_store.upsert_candles(
            "crypto_spot",
            "BTCUSDT",
            "5m",
            [
                Candle(1000, 11, 12, 10, 11, 1),
                Candle(2000, 12, 13, 11, 12, 1),
            ],
            source="seed",
        )
        client = self.make_client(
            auth_store=auth_store,
            client_factory=FakeMarketClient,
            historical_store=historical_store,
        )
        client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "password123"},
        )
        auth_store.set_user_access(
            auth_store.list_users()[0].id,
            is_active=True,
            activated_at=utcnow(),
        )

        response = client.get(
            "/api/live-chart?market=crypto_spot&symbol=BTCUSDT&interval=5m"
            "&limit=2&fast_ema=1&slow_ema=2&rsi_period=2"
            "&rsi_overbought=100&rsi_oversold=0"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["time"] for item in response.json()["candles"]], [1000, 2000])
        self.assertEqual(FakeMarketClient.kline_calls, [("BTCUSDT", "5m", 2)])
        self.assertEqual(
            [
                stored.open_time
                for stored in historical_store.load_candles(
                    "crypto_spot",
                    "BTCUSDT",
                    "5m",
                )
            ],
            [1000, 2000, 3000, 3001],
        )

    def test_live_chart_stale_background_refresh_writes_response_cache(self):
        class FakeResponseCache:
            def __init__(self) -> None:
                self.values: dict[str, dict[str, Any]] = {}

            def get_json(self, key: str) -> dict[str, Any] | None:
                return self.values.get(key)

            def set_json(
                self,
                key: str,
                payload: dict[str, Any],
                *,
                ttl_seconds: int,
            ) -> None:
                self.values[key] = payload | {"cached_ttl": ttl_seconds}

        class FakeMarketClient:
            def get_24h_tickers(self) -> list[dict[str, object]]:
                return []

            def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
                return [
                    Candle(
                        open_time=3000 + index,
                        open=price,
                        high=price + 1.0,
                        low=price - 1.0,
                        close=price,
                        volume=1.0,
                    )
                    for index, price in enumerate([13, 14])
                ][:limit]

        auth_store = InMemoryAuthStore()
        historical_store = InMemoryHistoricalDataStore()
        historical_store.upsert_candles(
            "crypto_spot",
            "BTCUSDT",
            "5m",
            [
                Candle(1000, 11, 12, 10, 11, 1),
                Candle(2000, 12, 13, 11, 12, 1),
            ],
            source="seed",
        )
        cache = FakeResponseCache()
        client = self.make_client(
            auth_store=auth_store,
            client_factory=FakeMarketClient,
            historical_store=historical_store,
            response_cache=cache,
        )
        client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "password123"},
        )
        auth_store.set_user_access(
            auth_store.list_users()[0].id,
            is_active=True,
            activated_at=utcnow(),
        )

        response = client.get(
            "/api/live-chart?market=crypto_spot&symbol=BTCUSDT&interval=5m"
            "&limit=2&fast_ema=1&slow_ema=2&rsi_period=2"
            "&rsi_overbought=100&rsi_oversold=0"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["time"] for item in response.json()["candles"]], [1000, 2000])
        self.assertEqual(len(cache.values), 1)
        cached_payload = next(iter(cache.values.values()))
        self.assertEqual([item["time"] for item in cached_payload["candles"]], [3000, 3001])
        self.assertEqual(cached_payload["cached_ttl"], 10)

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

    def test_removed_workflow_apis_return_404(self):
        store = InMemoryAuthStore()
        client = self.make_client(auth_store=store)
        client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "password123"},
        )
        store.set_user_access(store.list_users()[0].id, is_active=True, activated_at=utcnow())

        requests = [
            client.post("/api/strategy-lab", json={}),
            client.post("/api/backtest", json={}),
            client.post("/api/paper", json={}),
            client.post("/api/combination-signals", json={}),
            client.get("/api/alerts/telegram"),
            client.put("/api/alerts/telegram", json={}),
            client.post("/api/alerts/telegram/test"),
            client.get("/api/runs"),
            client.get("/api/run?path=backtests/x"),
        ]

        self.assertTrue(all(response.status_code == 404 for response in requests))

    def test_seeded_admin_can_login_with_configured_password_and_access_admin_api(self):
        client = self.make_client(
            seed_admin=True,
            admin_seed_password="admin-test-password-123",
        )

        login = client.post(
            "/api/auth/login",
            json={
                "username": "cuiyeqing960904@gmail.com",
                "password": "admin-test-password-123",
            },
        )

        self.assertEqual(login.status_code, 200)
        user = login.json()["user"]
        self.assertTrue(user["is_admin"])
        self.assertTrue(user["is_active"])
        response = client.get("/api/admin/users")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["users"][0]["username"], "cuiyeqing960904@gmail.com")

    def test_inactive_admin_session_cannot_access_admin_api(self):
        store = InMemoryAuthStore()
        client = self.make_client(
            auth_store=store,
            seed_admin=True,
            admin_seed_password="admin-test-password-123",
        )
        login = client.post(
            "/api/auth/login",
            json={
                "username": "cuiyeqing960904@gmail.com",
                "password": "admin-test-password-123",
            },
        )
        admin_user = store.list_users()[0]
        store.set_user_access(admin_user.id, is_active=False)

        self.assertEqual(login.status_code, 200)
        for method, path, payload in (
            ("get", "/api/admin/users", None),
            ("get", "/api/admin/settings/free-trial", None),
            ("put", "/api/admin/settings/free-trial", {"is_free_trial_enabled": True}),
            ("get", "/api/admin/feedback", None),
        ):
            with self.subTest(path=path):
                caller = getattr(client, method)
                response = caller(path, json=payload) if payload is not None else caller(path)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {"ok": False, "error": "account inactive"})

    def test_admin_users_requires_admin_flag_and_lists_all_users(self):
        store = InMemoryAuthStore()
        client = self.make_client(auth_store=store)
        client.post(
            "/api/auth/register",
            json={"username": "alice@example.com", "password": "password123"},
        )

        forbidden = client.get("/api/admin/users")
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.json(), {"ok": False, "error": "account inactive"})

        registered_user = store.list_users()[0]
        store.set_user_access(registered_user.id, is_active=True, activated_at=utcnow())

        forbidden = client.get("/api/admin/users")
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.json(), {"ok": False, "error": "admin required"})

        store.set_user_access(registered_user.id, is_active=False)

        client.post("/api/auth/logout")
        store.seed_admin_user("admin@example.com", "admin-test-password-123")
        client.post(
            "/api/auth/login",
            json={"username": "admin@example.com", "password": "admin-test-password-123"},
        )
        response = client.get("/api/admin/users")

        self.assertEqual(response.status_code, 200)
        users = response.json()["users"]
        self.assertEqual(
            [user["username"] for user in users],
            ["alice@example.com", "admin@example.com"],
        )
        self.assertFalse(users[0]["is_active"])
        self.assertIsNone(users[0]["expired_at"])
        self.assertFalse(users[0]["is_admin"])
        self.assertTrue(users[1]["is_admin"])

    def test_admin_can_update_user_active_flag(self):
        store = InMemoryAuthStore()
        client = self.make_client(auth_store=store)
        client.post(
            "/api/auth/register",
            json={"username": "alice@example.com", "password": "password123"},
        )
        alice = store.list_users()[0]
        client.post("/api/auth/logout")
        store.seed_admin_user("admin@example.com", "admin-test-password-123")
        client.post(
            "/api/auth/login",
            json={"username": "admin@example.com", "password": "admin-test-password-123"},
        )

        response = client.patch(
            f"/api/admin/users/{alice.id}/access",
            json={"is_active": True},
        )

        self.assertEqual(response.status_code, 200)
        updated = response.json()["user"]
        self.assertEqual(updated["username"], "alice@example.com")
        self.assertTrue(updated["is_active"])
        self.assertIsNotNone(updated["activated_at"])
        users = client.get("/api/admin/users").json()["users"]
        self.assertTrue(users[0]["is_active"])

        deactivate = client.patch(
            f"/api/admin/users/{alice.id}/access",
            json={"is_active": False},
        )

        self.assertEqual(deactivate.status_code, 200)
        self.assertFalse(deactivate.json()["user"]["is_active"])
        self.assertIsNone(deactivate.json()["user"]["activated_at"])

    def test_admin_can_update_user_expiration_date(self):
        store = InMemoryAuthStore()
        client = self.make_client(auth_store=store)
        client.post(
            "/api/auth/register",
            json={"username": "alice@example.com", "password": "password123"},
        )
        alice = store.list_users()[0]
        client.post("/api/auth/logout")
        store.seed_admin_user("admin@example.com", "admin-test-password-123")
        client.post(
            "/api/auth/login",
            json={"username": "admin@example.com", "password": "admin-test-password-123"},
        )
        expires_at = (utcnow() + timedelta(days=30)).replace(microsecond=0)

        response = client.patch(
            f"/api/admin/users/{alice.id}/access",
            json={
                "is_active": True,
                "expired_at": expires_at.isoformat().replace("+00:00", "Z"),
            },
        )

        self.assertEqual(response.status_code, 200)
        updated = response.json()["user"]
        self.assertTrue(updated["is_active"])
        self.assertEqual(updated["expired_at"], expires_at.isoformat().replace("+00:00", "Z"))

        clear_response = client.patch(
            f"/api/admin/users/{alice.id}/access",
            json={"is_active": True, "expired_at": None},
        )

        self.assertEqual(clear_response.status_code, 200)
        self.assertIsNone(clear_response.json()["user"]["expired_at"])

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
