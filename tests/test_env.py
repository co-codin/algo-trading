import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from algo_trading.env import load_env_file


class EnvTests(unittest.TestCase):
    def test_load_env_file_reads_plain_and_quoted_values_without_overriding(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "MOEX_API_KEY=fake-token",
                        "ADMIN_EMAIL='admin@example.com'",
                        "ADMIN_PASSWORD=from-file",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"ADMIN_PASSWORD": "from-shell"}, clear=True):
                load_env_file(env_path)

                self.assertEqual(os.environ["MOEX_API_KEY"], "fake-token")
                self.assertEqual(os.environ["ADMIN_EMAIL"], "admin@example.com")
                self.assertEqual(os.environ["ADMIN_PASSWORD"], "from-shell")


if __name__ == "__main__":
    unittest.main()
