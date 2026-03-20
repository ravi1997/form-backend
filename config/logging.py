import os
import logging
import logging.config
from typing import Dict, Any

# Ensure log directory exists
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

import re

# Masking patterns for sensitive data
SENSITIVE_KEYS = {
    "password", "token", "secret", "otp", "credit_card", "cvv", 
    "authorization", "api_key", "cookie"
}

PII_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
    "phone": re.compile(r"(\+\d{1,2}\s?)?1?\-?\.?\s?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}"),
}

class SensitiveDataFilter(logging.Filter):
    """
    Filters or masks sensitive information and PII from log messages.
    """

    def filter(self, record):
        from flask import g, has_request_context
        # Inject request_id for the formatter
        record.request_id = g.request_id if has_request_context() and hasattr(g, "request_id") else "no-request"
        
        if not isinstance(record.msg, str):
            return True

        msg = record.msg
        
        # 1. Mask PII via Regex
        for pii_type, pattern in PII_PATTERNS.items():
            msg = pattern.sub(f" [MASKED_{pii_type.upper()}] ", msg)
            
        # 2. Mask Key-Value pairs
        for key in SENSITIVE_KEYS:
            # Matches key followed by separator and value (e.g. password: value, password=value)
            kv_pattern = re.compile(rf"({key})[\s:=]+([^\s,;]+)", re.IGNORECASE)
            msg = kv_pattern.sub(r"\1: [MASKED]", msg)

        record.msg = msg
        return True


LOGGING_CONFIG: Dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] [ReqID: %(request_id)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "detailed": {
            "format": "%(asctime)s [%(levelname)s] [ReqID: %(request_id)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "audit": {
            "format": "%(asctime)s [AUDIT] [ReqID: %(request_id)s] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "performance": {
            "format": "%(asctime)s [PERF] [ReqID: %(request_id)s] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "filters": {
        "sensitive_filter": {
            "()": SensitiveDataFilter,
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": "DEBUG",
            "filters": ["sensitive_filter"],
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "ERROR",
            "formatter": "detailed",
            "filename": os.path.join(LOG_DIR, "error.log"),
            "maxBytes": 10485760,  # 10MB
            "backupCount": 10,
            "encoding": "utf8",
        },
        "audit_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "INFO",
            "formatter": "audit",
            "filename": os.path.join(LOG_DIR, "audit.log"),
            "maxBytes": 10485760,
            "backupCount": 10,
            "encoding": "utf8",
        },
        "performance_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "INFO",
            "formatter": "performance",
            "filename": os.path.join(LOG_DIR, "performance.log"),
            "maxBytes": 10485760,
            "backupCount": 10,
            "encoding": "utf8",
        },
        "access_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "INFO",
            "formatter": "standard",
            "filename": os.path.join(LOG_DIR, "access.log"),
            "maxBytes": 10485760,
            "backupCount": 10,
            "encoding": "utf8",
        },
        "app_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "INFO",
            "formatter": "standard",
            "filename": os.path.join(LOG_DIR, "application.log"),
            "maxBytes": 10485760,
            "backupCount": 10,
            "encoding": "utf8",
            "filters": ["sensitive_filter"],
        },
    },
    "loggers": {
        "": {  # Root logger
            "handlers": ["console", "app_file"],
            "level": "INFO",
            "propagate": True,
        },
        "error_logger": {
            "handlers": ["error_file", "console"],
            "level": "ERROR",
            "propagate": False,
        },
        "audit_logger": {
            "handlers": ["audit_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "performance_logger": {
            "handlers": ["performance_file"],
            "level": "INFO",
            "propagate": False,
        },
        "access_logger": {
            "handlers": ["access_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


def setup_logging():
    logging.config.dictConfig(LOGGING_CONFIG)
