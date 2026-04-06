# Sensitive Data Redaction in Logging

**Purpose:** Documentation for PII and sensitive data redaction from logs and error messages.

**Scope:** Redaction patterns, field lists, usage examples for `safe_log_info()` and `safe_log_error()`, and GDPR compliance.

---

## Overview

The sensitive data redaction system implements GDPR and security best practices for protecting personally identifiable information (PII) and sensitive data in logs. It provides automatic redaction of common sensitive patterns while maintaining debugging capability through selective redaction.

**Key Components:**
- `utils/sensitive_data_redaction.py` - Redaction logic (304 lines)
- Integration with all route handlers
- Support for strings, dictionaries, lists, and objects

---

## Redaction Patterns

### Supported Sensitive Data Types

| Type | Pattern | Placeholder |
|------|---------|-------------|
| Email | `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z\|a-z]{2,}` | `[REDACTED_EMAIL]` |
| Phone | `\d{3}[-.]?\d{3}[-.]?\d{4}` | `[REDACTED_PHONE]` |
| Credit Card | `(?:\d[ -]*?){13,16}` | `[REDACTED_CC]` |
| SSN | `\d{3}[-.]?\d{2}[-.]?\d{4}` | `[REDACTED_SSN]` |
| API Key | `[A-Za-z0-9]{32,}` | `[REDACTED_KEY]` |
| JWT | `eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+` | `[REDACTED_TOKEN]` |
| Password | `password["']?\s*[:=]\s*["']?[^"'\s]+["']?` | `[REDACTED_PASSWORD]` |
| UUID | `[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}` | `[REDACTED_UUID]` |
| Object ID | `[0-9a-fA-F]{24}` | `[REDACTED_ID]` |
| IP Address | `(?:\d{1,3}\.){3}\d{1,3}` | `[REDACTED_IP]` |

### Redacted Fields

```python
REDACTED_FIELDS = {
    "password", "password_hash", "secret", "api_key", "token",
    "access_token", "refresh_token", "authorization", "cookie",
    "credit_card", "ssn", "social_security_number", "phone",
    "mobile", "telephone", "email",
}
```

**Usage:** When redacting dictionaries, any key containing these substrings (case-insensitive) will be fully redacted.

---

## Redactor Configuration

### Full Redactor (Production)

```python
from utils.sensitive_data_redaction import full_redactor

# Redacts everything: emails, phones, IPs, UUIDs, etc.
redactor = SensitiveDataRedactor(redact_uuid=True, redact_ip=True)
```

### Debug Redactor (Development)

```python
from utils.sensitive_data_redaction import debug_redactor

# Redacts PII but keeps UUIDs and IPs for debugging
redactor = SensitiveDataRedactor(redact_uuid=False, redact_ip=False)
```

### Custom Configuration

```python
from utils.sensitive_data_redaction import SensitiveDataRedactor

# Custom: Redact emails but keep IPs and UUIDs
redactor = SensitiveDataRedactor(
    redact_uuid=False,
    redact_ip=False
)
```

---

## Usage Examples

### 1. Basic String Redaction

```python
from utils.sensitive_data_redaction import full_redactor

message = "User john.doe@example.com logged in from 192.168.1.1"
redacted = full_redactor.redact_string(message)

# Output: "User [REDACTED_EMAIL] logged in from [REDACTED_IP]"
```

### 2. Dictionary Redaction

```python
from utils.sensitive_data_redaction import full_redactor

data = {
    "user_id": "507f1f77bcf86cd799439011",
    "email": "user@example.com",
    "password": "Secret123!",
    "phone": "555-123-4567",
    "metadata": {
        "ip_address": "192.168.1.1",
        "api_key": "sk_live_1234567890abcdef"
    }
}

redacted = full_redactor.redact_dict(data, deep=True)

# Output:
# {
#     "user_id": "[REDACTED_ID]",
#     "email": "[REDACTED]",
#     "password": "[REDACTED]",
#     "phone": "[REDACTED]",
#     "metadata": {
#         "ip_address": "[REDACTED_IP]",
#         "api_key": "[REDACTED]"
#     }
# }
```

### 3. List Redaction

```python
from utils.sensitive_data_redaction import full_redactor

users = [
    {"email": "user1@example.com", "name": "John Doe"},
    {"email": "user2@example.com", "name": "Jane Smith"}
]

redacted = full_redactor.redact_list(users, deep=True)

# Output:
# [
#     {"email": "[REDACTED]", "name": "John Doe"},
#     {"email": "[REDACTED]", "name": "Jane Smith"}
# ]
```

### 4. Safe Logging

```python
from utils.sensitive_data_redaction import safe_log_info, safe_log_error
from logger.unified_logger import app_logger, error_logger

# Safe info logging
safe_log_info(
    app_logger,
    "User %s logged in from %s with email %s",
    username,
    ip_address,
    email
)

# Output: "User [REDACTED_EMAIL] logged in from [REDACTED_IP] with email [REDACTED_EMAIL]"

# Safe error logging with exception info
safe_log_error(
    error_logger,
    "Failed to process user %s with ID %s",
    email,
    user_id,
    exc_info=True
)

# Output: "Failed to process user [REDACTED_EMAIL] with ID [REDACTED_ID]"
```

### 5. Decorator Usage

```python
from utils.sensitive_data_redaction import redact_sensitive
from logger.unified_logger import app_logger

@redact_sensitive
def log_user_action(user: User, action: str):
    """Automatically redact sensitive data from return value."""
    app_logger.info(f"User {user.email} performed {action}")
    return f"Action {action} completed for {user.email}"

# Log message automatically redacted
log_user_action(user, "login")

# Output: "Action login completed for [REDACTED_EMAIL]"
```

### 6. Log Message Formatting

```python
from utils.sensitive_data_redaction import redact_for_log

# Format message with redaction
message = redact_for_log(
    "User %s with ID %s logged in from %s",
    email,
    user_id,
    ip_address
)

app_logger.info(message)

# Output: "User [REDACTED_EMAIL] with ID [REDACTED_ID] logged in from [REDACTED_IP]"
```

---

## Integration Points

### 1. Authentication Routes

**Location:** `routes/v1/auth_route.py`

```python
from utils.sensitive_data_redaction import safe_log_info

@bp.route("/login", methods=["POST"])
def login():
    email = request.json.get("email")
    password = request.json.get("password")

    # ... authentication logic ...

    # Safe logging with redaction
    safe_log_info(app_logger, "User %s logged in", email)

    return success_response(data={"user_id": str(user.id)})
```

### 2. User Routes

**Location:** `routes/v1/user_route.py`

```python
from utils.sensitive_data_redaction import safe_log_info, safe_log_error

@bp.route("/profile", methods=["GET"])
@jwt_required()
def get_profile():
    user = get_current_user()

    safe_log_info(
        app_logger,
        "Profile requested by user %s",
        user.email
    )

    return success_response(data=user.to_dict())
```

### 3. File Upload Routes

**Location:** `routes/v1/form/files.py`

```python
from utils.sensitive_data_redaction import safe_log_info

@bp.route("/upload", methods=["POST"])
@jwt_required()
def upload_file():
    file = request.files.get("file")
    user = get_current_user()

    # ... file upload logic ...

    safe_log_info(
        app_logger,
        "File %s uploaded by user %s",
        file.filename,
        user.email
    )

    return success_response(data=file_info)
```

### 4. Export Routes

**Location:** `routes/v1/form/export.py`

```python
from utils.sensitive_data_redaction import safe_log_info

@bp.route("/<form_id>/export/csv", methods=["GET"])
@jwt_required()
def export_csv(form_id):
    user = get_current_user()

    # ... export logic ...

    safe_log_info(
        app_logger,
        "CSV export initiated by user %s for form %s",
        user.email,
        form_id
    )

    # ... stream response ...
```

---

## Best Practices

### 1. Always Use Safe Logging

```python
# CORRECT
from utils.sensitive_data_redaction import safe_log_info
safe_log_info(app_logger, "User %s logged in", email)

# WRONG
app_logger.info(f"User {email} logged in")  # Logs email address
```

### 2. Redact Before Logging Structured Data

```python
# CORRECT
redacted_data = full_redactor.redact_dict(user_data)
app_logger.info(f"User data: {redacted_data}")

# WRONG
app_logger.info(f"User data: {user_data}")  # Logs PII
```

### 3. Use Appropriate Logger

```python
# CORRECT - For security events
audit_logger.info("User login successful")

# CORRECT - For errors
error_logger.error("Login failed", exc_info=True)

# CORRECT - For informational messages
app_logger.info("Processing request")
```

### 4. Configure for Environment

```python
# config/settings.py or environment-specific
if settings.APP_ENV == "production":
    from utils.sensitive_data_redaction import full_redactor as redactor
else:
    from utils.sensitive_data_redaction import debug_redactor as redactor
```

### 5. Never Log Passwords

```python
# CORRECT - Never log passwords
# Just log that authentication was attempted
app_logger.info("Authentication attempted")

# WRONG
app_logger.info(f"Authentication with password {password}")  # NEVER DO THIS
```

---

## GDPR Compliance

### Data Minimization

Only log data necessary for debugging and security analysis.

**Example:**
```python
# CORRECT - Log user ID instead of email
app_logger.info(f"User {user_id} performed action")

# WRONG - Log email address
app_logger.info(f"User {email} performed action")
```

### Right to Erasure

When a user requests data deletion, ensure logs are redacted or deleted.

```python
def delete_user_data(user_id):
    """Delete user data including logs."""
    # 1. Delete user record
    User.objects(id=user_id).update(set__is_deleted=True)

    # 2. Redact logs (implementation depends on log storage)
    # 3. Archive logs if needed for legal retention
```

### Data Protection Impact Assessment (DPIA)

Document what PII is logged and why.

**Log Categories:**
1. **Security Logs:** Authentication attempts, access control decisions
2. **Audit Logs:** Data changes, configuration updates
3. **Error Logs:** System errors with request context
4. **Performance Logs:** Request timing, resource usage

---

## Security Considerations

### 1. Log Storage Security

**Recommendations:**
- Encrypt logs at rest
- Restrict log access to authorized personnel
- Use log forwarding to centralized logging system
- Implement log retention policies

### 2. Log Transmission

**Recommendations:**
- Use TLS for log forwarding
- Authenticate log destinations
- Validate log format before parsing

### 3. Log Analysis

**Considerations:**
- Redacted data limits debugging capability
- Use separate debug logging (not redacted) in development
- Implement log search with access controls

---

## Testing

### Unit Tests

```python
def test_email_redaction():
    from utils.sensitive_data_redaction import full_redactor

    message = "Contact john.doe@example.com for support"
    redacted = full_redactor.redact_string(message)

    assert "john.doe@example.com" not in redacted
    assert "[REDACTED_EMAIL]" in redacted

def test_phone_redaction():
    from utils.sensitive_data_redaction import full_redactor

    message = "Call 555-123-4567 for support"
    redacted = full_redactor.redact_string(message)

    assert "555-123-4567" not in redacted
    assert "[REDACTED_PHONE]" in redacted

def test_dict_redaction():
    from utils.sensitive_data_redaction import full_redactor

    data = {"email": "user@example.com", "name": "John Doe"}
    redacted = full_redactor.redact_dict(data)

    assert redacted["email"] == "[REDACTED]"
    assert redacted["name"] == "John Doe"

def test_field_name_redaction():
    from utils.sensitive_data_redaction import full_redactor

    data = {"user_password": "Secret123", "user_name": "John"}
    redacted = full_redactor.redact_dict(data)

    assert redacted["user_password"] == "[REDACTED]"
    assert redacted["user_name"] == "John"
```

---

## Configuration Reference

### Redactor Options

```python
# utils/sensitive_data_redaction.py

class SensitiveDataRedactor:
    def __init__(
        self,
        redact_uuid: bool = True,
        redact_ip: bool = True
    ):
        """
        Initialize redactor with configuration.

        Args:
            redact_uuid: Whether to redact UUIDs/ObjectIds (default: True)
            redact_ip: Whether to redact IP addresses (default: True)
        """
```

### Pre-configured Instances

```python
# Redact everything (most secure)
full_redactor = SensitiveDataRedactor(
    redact_uuid=True,
    redact_ip=True
)

# Redact sensitive data but keep UUIDs and IPs for debugging
debug_redactor = SensitiveDataRedactor(
    redact_uuid=False,
    redact_ip=False
)
```

---

## References

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [GDPR Article 25 - Data Protection by Design](https://gdpr-info.eu/art-25-gdpr/)
- [NIST SP 800-92 - Guide to Computer Security Log Management](https://csrc.nist.gov/publications/detail/sp/800-92/final)
- [PCI DSS Requirement 10 - Track and Monitor Access](https://www.pcisecuritystandards.org/document_library)
