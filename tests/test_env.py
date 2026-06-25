import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from algo_trading.env import load_env_file


class EnvTests(unittest.TestCase):
    def test_load_env_file_sets_missing_values_without_overriding_existing_env(self):
        with tempfile.TemporaryDirectory() as tempdir:
            env_file = Path(tempdir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "DATABASE_URL=postgresql://example",
                        "REDIS_URL=redis://example",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"REDIS_URL": "redis://existing"}, clear=True):
                load_env_file(env_file)

                self.assertEqual(os.environ["DATABASE_URL"], "postgresql://example")
                self.assertEqual(os.environ["REDIS_URL"], "redis://existing")
