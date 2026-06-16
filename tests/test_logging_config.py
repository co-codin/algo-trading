import logging
import tempfile
import unittest
from pathlib import Path

from algo_trading.logging_config import configure_error_logging, log_file_path


class LoggingConfigTests(unittest.TestCase):
    def tearDown(self) -> None:
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            if getattr(handler, "_algo_trading_log_path", None):
                root_logger.removeHandler(handler)
                handler.close()

    def test_configure_error_logging_writes_exception_to_service_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp) / "logs"
            logger = configure_error_logging("app", log_dir=log_dir)

            try:
                raise RuntimeError("simulated failure")
            except RuntimeError as exc:
                logger.error(
                    "Unhandled API error",
                    exc_info=(type(exc), exc, exc.__traceback__),
                )

            log_path = log_file_path("app", log_dir=log_dir)
            content = log_path.read_text(encoding="utf-8")

        self.assertIn("Unhandled API error", content)
        self.assertIn("RuntimeError: simulated failure", content)
