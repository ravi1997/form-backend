# Unified Logging Service Documentation

## 1. Overview

The forms-backend implements a rigorous, enterprise-grade unified logging strategy. Instead of relying on raw print statements or scattered `logging.getLogger(__name__)` commands, the application uses a strict routing system tailored to specific types of events.

This ensures proper auditing, simplifies debugging via isolated file streams, automatically masks sensitive data, and prepares the system for seamless integration with external aggregators (like Datadog, Sentry, or ELK).

---

## 2. Configuration (`logger/config.py`)

Centralized configuration is handled purely in Python dictionaries rather than static `.ini` files.

### Architecture Specifications

- **Log Rotation**: We use `RotatingFileHandler`. Log files are capped at **10 MB**, and we retain the last **10 backups**.
- **Destinations**: All file logs are persisted in the root `logs/` directory.
- **Data Protection**: `SensitiveDataFilter` parses streams and aggressively masks terms containing passwords, secrets, or OTPs.

---

## 3. Logger Modules & Usage

When developing a new Service or API Route, you must import the specific logger tailored to your action from `logger`.

### `app_logger` (or `get_logger(__name__)`)

- **Purpose**: General operational application logging, basic debug flows, starting metrics.
- **Output**: `logs/application.log` and `Console`
- **Level**: INFO+
- **Example Usage**:

```python
from logger import get_logger
logger = get_logger(__name__)

logger.info("Initializing background cron job.")
logger.debug("Checking payload schema integrity.")
```

### `audit_logger`

- **Purpose**: Mandatory logging for strict compliance. E.g., Adding/Removing users from a tenant, publishing a Form blueprint, mutating workflow states.
- **Output**: `logs/audit.log` and `Console`
- **Level**: INFO
- **Example Usage**:

```python
from logger import audit_logger

# Record secure state transitions
audit_logger.info(f"User {auth.user_id} promoted to Administrator in group {group.id}")
audit_logger.info(f"Form '{form.title}' published iteratively from version 1.0.0 to 1.1.0")
```

### `access_logger`

- **Purpose**: Tracks traffic patterns, incoming ingestion payloads (Form Submissions), and external API requests hitting our edges.
- **Output**: `logs/access.log` and `Console`
- **Level**: INFO
- **Example Usage**:

```python
from logger import access_logger

access_logger.info(f"Incoming Form Submission payload from HTTP IP {request.ip_address}")
access_logger.warning(f"Submission rejected: Payload size exceeded 5MB limit.")
```

### `error_logger`

- **Purpose**: Captures stack traces, crash reports, database connectivity issues, and unhandled Exceptions.
- **Output**: `logs/error.log` and `Console`
- **Level**: ERROR (CRITICAL)
- **Example Usage**:

```python
from logger import error_logger

try:
    db.session.commit()
except Exception as e:
    # exc_info=True automatically dumps the stacktrace into the log securely
    error_logger.error("MongoDB commit transaction failed during payload ingestion.", exc_info=True)
```

### `performance_logger`

- **Purpose**: Diagnostic log for timing slow operations, materialized view executions, or ML inferences.
- **Output**: `logs/performance.log`
- **Level**: INFO
- **Example Usage**:

```python
from logger import log_performance, PerformanceTimer

# 1. Using the Decorator Pattern
@log_performance
def execute_materialized_view(self, view_id: str):
    return pipeline_result

# 2. Using Context Manager Pattern
with PerformanceTimer("heavy_db_aggregation"):
    result = FormResponse.objects.aggregate(*pipeline)
```

---

## 4. How to Update or Extend

1. Open `logger/config.py`.
2. To add a new log file (e.g., `webhooks.log`), create a new handler pointing to `RotatingFileHandler`.
3. Add a new `logger` block mapping to that handler.
4. Open `logger/unified_logger.py` and expose the new logger variable for external imports `webhook_logger = logging.getLogger("webhook")`.
