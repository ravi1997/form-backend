"""
utils/sensitive_data_redaction.py
Redacts sensitive information from logs and error messages.
Implements GDPR and security best practices.
"""

import re
from typing import Any, Optional
from functools import wraps

# Patterns for sensitive data redaction
SENSITIVE_PATTERNS = {
    # Email addresses
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    # Phone numbers (various formats)
    "phone": re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
    # Credit card numbers (basic pattern)
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    # SSN-like patterns
    "ssn": re.compile(r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b"),
    # API keys and tokens (common patterns)
    "api_key": re.compile(r"\b[A-Za-z0-9]{32,}\b"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    # Password-like patterns
    "password": re.compile(
        r'(?i)password["\']?\s*[:=]\s*["\']?[^"\'\s]+["\']?', re.IGNORECASE
    ),
    # UUIDs
    "uuid": re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    ),
    # MongoDB ObjectIds
    "object_id": re.compile(r"\b[0-9a-fA-F]{24}\b"),
    # IP addresses
    "ip_address": re.compile(
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"
    ),
}

# Fields that should be redacted in log messages
REDACTED_FIELDS = {
    "password",
    "password_hash",
    "secret",
    "api_key",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "credit_card",
    "ssn",
    "social_security_number",
    "phone",
    "mobile",
    "telephone",
    "email",
}

# Replacement strings
REDACTION_PLACEHOLDERS = {
    "email": "[REDACTED_EMAIL]",
    "phone": "[REDACTED_PHONE]",
    "credit_card": "[REDACTED_CC]",
    "ssn": "[REDACTED_SSN]",
    "api_key": "[REDACTED_KEY]",
    "jwt": "[REDACTED_TOKEN]",
    "password": "[REDACTED_PASSWORD]",
    "uuid": "[REDACTED_UUID]",
    "object_id": "[REDACTED_ID]",
    "ip_address": "[REDACTED_IP]",
    "default": "[REDACTED]",
}


class SensitiveDataRedactor:
    """Redacts sensitive information from strings and dictionaries."""

    def __init__(self, redact_uuid: bool = True, redact_ip: bool = True):
        """
        Initialize redactor with configuration.

        Args:
            redact_uuid: Whether to redact UUIDs/ObjectIds (default: True)
            redact_ip: Whether to redact IP addresses (default: True)
        """
        self.redact_uuid = redact_uuid
        self.redact_ip = redact_ip

        # Build pattern list based on configuration
        self._patterns = {}
        for key, pattern in SENSITIVE_PATTERNS.items():
            if key == "uuid" and not self.redact_uuid:
                continue
            if key == "ip_address" and not self.redact_ip:
                continue
            self._patterns[key] = pattern

    def redact_string(self, text: str) -> str:
        """
        Redact sensitive data from a string.

        Args:
            text: The input string to redact

        Returns:
            String with sensitive data redacted
        """
        if not text or not isinstance(text, str):
            return text

        result = text

        # Apply each pattern
        for key, pattern in self._patterns.items():
            placeholder = REDACTION_PLACEHOLDERS.get(
                key, REDACTION_PLACEHOLDERS["default"]
            )
            result = pattern.sub(placeholder, result)

        return result

    def redact_dict(self, data: dict, deep: bool = True) -> dict:
        """
        Redact sensitive data from dictionary values.

        Args:
            data: Dictionary to redact
            deep: Whether to recursively redact nested dictionaries (default: True)

        Returns:
            Dictionary with sensitive values redacted
        """
        if not isinstance(data, dict):
            return data

        result = {}
        for key, value in data.items():
            key_lower = key.lower()

            # Check if field should be redacted
            if any(sensitive in key_lower for sensitive in REDACTED_FIELDS):
                result[key] = REDACTION_PLACEHOLDERS["default"]
            elif isinstance(value, str):
                result[key] = self.redact_string(value)
            elif isinstance(value, dict) and deep:
                result[key] = self.redact_dict(value, deep=True)
            elif isinstance(value, list) and deep:
                result[key] = self.redact_list(value, deep=True)
            else:
                result[key] = value

        return result

    def redact_list(self, data: list, deep: bool = True) -> list:
        """
        Redact sensitive data from list items.

        Args:
            data: List to redact
            deep: Whether to recursively redact nested structures (default: True)

        Returns:
            List with sensitive data redacted
        """
        if not isinstance(data, list):
            return data

        result = []
        for item in data:
            if isinstance(item, str):
                result.append(self.redact_string(item))
            elif isinstance(item, dict) and deep:
                result.append(self.redact_dict(item, deep=True))
            elif isinstance(item, list) and deep:
                result.append(self.redact_list(item, deep=True))
            else:
                result.append(item)

        return result

    def redact_object(self, obj: Any, deep: bool = True) -> Any:
        """
        Redact sensitive data from any Python object.

        Args:
            obj: Object to redact
            deep: Whether to recursively redact nested structures (default: True)

        Returns:
            Object with sensitive data redacted (dict representation)
        """
        if hasattr(obj, "__dict__"):
            return self.redact_dict(obj.__dict__, deep=deep)
        elif isinstance(obj, dict):
            return self.redact_dict(obj, deep=deep)
        elif isinstance(obj, list):
            return self.redact_list(obj, deep=deep)
        elif isinstance(obj, str):
            return self.redact_string(obj)
        else:
            return obj

    def redact_log_message(self, message: str, *args) -> str:
        """
        Redact sensitive data from log message with positional args.

        Useful for formatted log messages like:
            logger.info("User %s logged in", username)

        Args:
            message: Log message format string
            *args: Values to redact and format

        Returns:
            Redacted log message
        """
        if not args:
            return self.redact_string(message)

        # Redact each value in args
        redacted_args = []
        for value in args:
            if isinstance(value, str):
                redacted_args.append(self.redact_string(value))
            else:
                redacted_args.append(self.redact_object(value, deep=False))

        # Format message
        try:
            return message % tuple(redacted_args)
        except (TypeError, ValueError):
            # If format fails, return redacted message + redacted args as string
            return f"{self.redact_string(message)} | Args: {str(redacted_args)}"


def redact_sensitive(func):
    """
    Decorator to automatically redact sensitive data from logging calls.

    Usage:
        @redact_sensitive
        def my_function():
            logger.info("User %s with email %s logged in", username, email)
    """
    redactor = SensitiveDataRedactor()

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Get return value
        result = func(*args, **kwargs)

        # If result is a log message string, redact it
        if isinstance(result, str):
            return redactor.redact_string(result)

        return result

    return wrapper


# Singleton instances for common use cases
# Redact everything (most secure)
full_redactor = SensitiveDataRedactor(redact_uuid=True, redact_ip=True)

# Redact sensitive data but keep UUIDs and IPs for debugging
debug_redactor = SensitiveDataRedactor(redact_uuid=False, redact_ip=False)


def redact_for_log(message: str, *args) -> str:
    """
    Convenience function to redact sensitive data for logging.

    Usage:
        app_logger.info(redact_for_log("User %s logged in", username))
    """
    return full_redactor.redact_log_message(message, *args)


def safe_log_info(logger, message: str, *args):
    """
    Safely log info message with automatic redaction.

    Args:
        logger: Logger instance
        message: Log message
        *args: Values to log (will be redacted)
    """
    redacted_message = redact_for_log(message, *args)
    logger.info(redacted_message)


def safe_log_error(logger, message: str, *args, exc_info: bool = False):
    """
    Safely log error message with automatic redaction.

    Args:
        logger: Logger instance
        message: Error message
        *args: Values to log (will be redacted)
        exc_info: Whether to include exception info
    """
    redacted_message = redact_for_log(message, *args)
    if exc_info:
        logger.error(redacted_message, exc_info=True)
    else:
        logger.error(redacted_message)
