"""
logger/unified_logger.py
Exposes named loggers and performance utilities.

NOTE: setup_logging() is called here so that all loggers are ready as soon as
this module is imported. init_sentry() is NOT called here — it is called once
in app.py's create_app() after Flask is initialised, preventing double-init.
"""

import logging
import logging.config
import time
from functools import wraps
from typing import Callable, Any
from flask import g

from config.logging import setup_logging

# Initialise logging configuration exactly once
setup_logging()

# ── Exposed named loggers ────────────────────────────────────────────────────
error_logger = logging.getLogger("error_logger")
audit_logger = logging.getLogger("audit_logger")
performance_logger = logging.getLogger("performance_logger")
access_logger = logging.getLogger("access_logger")
app_logger = logging.getLogger("application")


def get_logger(name: str) -> logging.Logger:
    """Returns a named child logger."""
    return logging.getLogger(name)


def get_request_id() -> str:
    """Safely retrieves the current request ID from Flask's global context."""
    try:
        return getattr(g, "request_id", "internal")
    except Exception:
        return "internal"


def log_performance(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator that logs execution time of the wrapped function
    to the dedicated performance logger.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        duration = time.perf_counter() - start_time
        performance_logger.info(
            f"Function '{func.__name__}' in '{func.__module__}' took {duration:.4f}s"
        )
        return result

    return wrapper


def log_error_with_sentry(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator that captures unhandled exceptions and forwards them to Sentry.
    Re-raises the exception after capturing so normal error flow is preserved.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            from config.sentry import capture_custom_exception

            capture_custom_exception(
                e, {"function": func.__name__, "module": func.__module__}
            )
            raise

    return wrapper


class PerformanceTimer:
    """
    Context manager that measures and logs the execution time of a code block.

    Usage:
        with PerformanceTimer("db_query"):
            results = Model.objects.filter(...)
    """

    def __init__(self, name: str):
        self.name = name
        self.start_time: float = 0.0

    def __enter__(self) -> "PerformanceTimer":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        duration = time.perf_counter() - self.start_time
        performance_logger.info(f"Block '{self.name}' took {duration:.4f}s")
