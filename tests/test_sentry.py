import os
import unittest
from config.sentry import capture_custom_exception, log_custom_message, init_sentry


class TestSentryIntegration(unittest.TestCase):

    def setUp(self):
        # Set a dummy DSN for testing if not present
        if not os.getenv("SENTRY_DSN"):
            os.environ["SENTRY_DSN"] = "https://public@sentry.example.com/1"

        init_sentry()

    def test_capture_exception(self):
        """
        Tests that capture_custom_exception runs without error.
        """
        try:
            1 / 0
        except ZeroDivisionError as e:
            # This should not raise any error if Sentry is configured correctly
            capture_custom_exception(e, {"test_context": "unit_test_exception"})
            print("Successfully captured ZeroDivisionError manually.")

    def test_log_message(self):
        """
        Tests that log_custom_message runs without error.
        """
        # This should not raise any error
        log_custom_message(
            "Manual test message from unit test",
            level="info",
            context={"test_key": "test_value"},
        )
        print("Successfully logged manual message to Sentry.")

    def test_logger_integration(self):
        """
        Tests that normal logging also goes through the Sentry breadcrumbs/events.
        """
        import logging

        logger = logging.getLogger("test_sentry_logger")
        logger.info("This is an info breadcrumb for Sentry")
        logger.error("This is an error event for Sentry")
        print("Successfully tested logger integration.")


if __name__ == "__main__":
    unittest.main()
