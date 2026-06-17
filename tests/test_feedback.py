import unittest

from algo_trading.feedback import InMemoryFeedbackStore, public_feedback


class FeedbackTests(unittest.TestCase):
    def test_memory_store_creates_feedback_with_required_title_and_default_status(self):
        store = InMemoryFeedbackStore()

        item = store.create_feedback(
            user_id=7,
            username="alice@example.com",
            title=" Chart bug ",
            description=None,
        )

        self.assertEqual(item.id, 1)
        self.assertEqual(item.user_id, 7)
        self.assertEqual(item.username, "alice@example.com")
        self.assertEqual(item.title, "Chart bug")
        self.assertEqual(item.description, "")
        self.assertEqual(item.status, "open")
        payload = public_feedback(item)
        self.assertEqual(payload["status"], "open")
        self.assertTrue(str(payload["created_at"]).endswith("Z"))
        self.assertTrue(str(payload["updated_at"]).endswith("Z"))

        with self.assertRaisesRegex(ValueError, "feedback title is required"):
            store.create_feedback(
                user_id=7,
                username="alice@example.com",
                title=" ",
                description="missing title",
            )

    def test_memory_store_updates_feedback_status(self):
        store = InMemoryFeedbackStore()
        item = store.create_feedback(
            user_id=7,
            username="alice@example.com",
            title="Need HK stocks",
            description="",
        )

        updated = store.update_feedback_status(item.id, "in_progress")

        self.assertEqual(updated.status, "in_progress")
        self.assertEqual(store.list_feedback()[0].status, "in_progress")
        with self.assertRaisesRegex(ValueError, "unsupported feedback status"):
            store.update_feedback_status(item.id, "ignored")
        with self.assertRaisesRegex(ValueError, "unknown feedback"):
            store.update_feedback_status(999, "resolved")


if __name__ == "__main__":
    unittest.main()
