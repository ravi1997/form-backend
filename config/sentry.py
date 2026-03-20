"""
config/sentry.py
Sentry SDK initialisation and helper utilities.
"""

import logging
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from config.settings import settings


def init_sentry() -> None:
    """
    Initialises Sentry SDK with secure defaults.
    Skips silently when SENTRY_DSN is not configured (e.g. local dev).
    """
    if not settings.SENTRY_DSN:
        logging.getLogger(__name__).debug(
            "Sentry DSN not configured — error tracking disabled."
        )
        return

    sentry_logging = LoggingIntegration(
        level=logging.INFO,  # Capture INFO and above as breadcrumbs
        event_level=logging.ERROR,  # Send ERROR and above as Sentry events
    )

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[
            FlaskIntegration(),
            RedisIntegration(),
            sentry_logging,
        ],
        # FIX: Never send PII (emails, IPs, usernames) to Sentry — GDPR risk
        send_default_pii=False,
        # FIX: Configurable sample rates — 1.0 in production is cost-prohibitive
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
        environment=settings.APP_ENV,
    )
    logging.getLogger(__name__).info("Sentry initialised successfully.")


def capture_custom_exception(e: Exception, context: dict = None) -> None:
    """
    Manually captures an exception with optional extra context.
    """
    with sentry_sdk.isolation_scope() as scope:
        if context:
            for key, value in context.items():
                scope.set_extra(key, value)
        sentry_sdk.capture_exception(e)


def log_custom_message(message: str, level: str = "info", context: dict = None) -> None:
    """
    Manually logs a message to Sentry.

    FIX: capture_message is now called INSIDE the isolation_scope so that
    the extra context set via scope.set_extra is correctly attached to the event.
    Previously the capture_message call was outside the `with` block, which
    caused all context to be discarded.
    """
    with sentry_sdk.isolation_scope() as scope:
        if context:
            for key, value in context.items():
                scope.set_extra(key, value)
        # Correctly placed INSIDE the scope context manager
        sentry_sdk.capture_message(message, level=level)
