import json
import unittest

from algo_trading.alerts import (
    InMemoryAlertStore,
    TelegramBotClient,
    build_telegram_signal_message,
    public_telegram_alert_settings,
)


class AlertTests(unittest.TestCase):
    def test_memory_store_masks_bot_token_and_preserves_existing_token(self):
        store = InMemoryAlertStore()

        settings = store.upsert_telegram_settings(
            user_id=7,
            enabled=True,
            bot_token="123456:abcdef-secret-token",
            chat_id="987654321",
        )

        payload = public_telegram_alert_settings(settings)
        self.assertTrue(payload["enabled"])
        self.assertTrue(payload["bot_token_configured"])
        self.assertNotIn("abcdef-secret-token", str(payload))
        self.assertEqual(payload["bot_token_preview"], "123456:...oken")
        self.assertEqual(payload["chat_id"], "987654321")

        updated = store.upsert_telegram_settings(
            user_id=7,
            enabled=True,
            bot_token="",
            chat_id="987654322",
        )

        self.assertEqual(updated.bot_token, "123456:abcdef-secret-token")
        self.assertEqual(updated.chat_id, "987654322")

    def test_memory_store_deduplicates_signal_deliveries(self):
        store = InMemoryAlertStore()

        self.assertFalse(store.has_signal_delivery(7, "BTCUSDT:5m:3:long"))
        store.record_signal_delivery(7, "BTCUSDT:5m:3:long")

        self.assertTrue(store.has_signal_delivery(7, "BTCUSDT:5m:3:long"))
        self.assertFalse(store.has_signal_delivery(8, "BTCUSDT:5m:3:long"))

    def test_signal_message_contains_rsi_context_without_token_leakage(self):
        message = build_telegram_signal_message(
            market="crypto_spot",
            symbol="BTCUSDT",
            interval="5m",
            signal={
                "time": 3,
                "price": 9.0,
                "type": "long_signal",
                "reason": "rsi_reversal_long",
            },
        )

        self.assertIn("RSI alert", message)
        self.assertIn("BTCUSDT", message)
        self.assertIn("5m", message)
        self.assertIn("long_signal", message)
        self.assertIn("rsi_reversal_long", message)

    def test_telegram_client_posts_send_message_payload(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b'{"ok": true}'

        def fake_opener(request, *, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["content_type"] = request.get_header("Content-type")
            return FakeResponse()

        client = TelegramBotClient(
            api_root="https://telegram.example.test",
            opener=fake_opener,
            timeout=4,
        )

        client.send_message("123456:token", "987654321", "RSI alert")

        self.assertEqual(
            captured["url"],
            "https://telegram.example.test/bot123456:token/sendMessage",
        )
        self.assertEqual(captured["timeout"], 4)
        self.assertEqual(
            captured["body"],
            {
                "chat_id": "987654321",
                "text": "RSI alert",
                "disable_web_page_preview": True,
            },
        )
        self.assertEqual(captured["content_type"], "application/json")


if __name__ == "__main__":
    unittest.main()
