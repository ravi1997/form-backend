"""
services/sentry_service.py
Re-exports Sentry helpers from config.sentry and adds unified logging.
"""

from config.sentry import capture_custom_exception as _capture_custom_exception, log_custom_message as _log_custom_message
from logger.unified_logger import app_logger, error_logger

def capture_custom_exception(e: Exception, context: dict = None) -> None:
    """
    Manually captures an exception with optional extra context and logs it.
    """
    app_logger.info(f"Capturing custom exception to Sentry: {type(e).__name__}")
    try:
        _capture_custom_exception(e, context)
    except Exception as inner_e:
        error_logger.error(f"Failed to capture exception to Sentry: {str(inner_e)}", exc_info=True)

def log_custom_message(message: str, level: str = "info", context: dict = None) -> None:
    """
    Manually logs a message to Sentry and unified_logger.
    """
    app_logger.info(f"Logging custom message to Sentry [Level: {level}]: {message[:100]}...")
    try:
        _log_custom_message(message, level, context)
    except Exception as e:
        error_logger.error(f"Failed to log message to Sentry: {str(e)}", exc_info=True)

__all__ = ["capture_custom_exception", "log_custom_message"]
