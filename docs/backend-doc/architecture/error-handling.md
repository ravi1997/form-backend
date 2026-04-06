# Error Handling Patterns

**Purpose:** Documentation for error handling patterns, error code catalog, retry logic, and client error handling guidelines.

**Scope:** Error code catalog, error type categorization, error response format, retry-able vs non-retry-able errors, client error handling, error suppression policy, and rate limit error handling.

---

## Overview

This document outlines error handling patterns for the RIDP Form Platform, ensuring consistent error responses across all endpoints and enabling proper client-side error recovery.

**Target Audience:** API developers, frontend developers, system architects

---

## Error Response Format

### Standard Error Response

```python
# utils/response_helper.py
def error_response(
    message: str = None,
    errors: list = None,
    error_code: str = None,
    status_code: int = 400
) -> tuple:
    """Standard error response format."""
    response = {
        "success": False,
        "error": message,
        "error_code": error_code,
        "errors": errors or [],
        "timestamp": datetime.utcnow().isoformat()
    }

    return jsonify(response), status_code
```

### Response Examples

**Validation Error:**
```json
{
  "success": false,
  "error": "Validation failed",
  "error_code": "VALIDATION_ERROR",
  "errors": [
    {
      "field": "email",
      "message": "Invalid email format"
    },
    {
      "field": "password",
      "message": "Password must be at least 12 characters"
    }
  ],
  "timestamp": "2026-04-06T10:00:00Z"
}
```

**Not Found Error:**
```json
{
  "success": false,
  "error": "Resource not found",
  "error_code": "NOT_FOUND",
  "errors": [],
  "timestamp": "2026-04-06T10:00:00Z"
}
```

**Rate Limit Error:**
```json
{
  "success": false,
  "error": "Rate limit exceeded",
  "error_code": "RATE_LIMIT_EXCEEDED",
  "errors": [],
  "timestamp": "2026-04-06T10:00:00Z",
  "retry_after": 60
}
```

---

## Error Code Catalog

### Error Codes

| Error Code | HTTP Status | Description | Retry-able |
|-----------|------------|-------------|------------|
| VALIDATION_ERROR | 400 | Request validation failed | No |
| INVALID_INPUT | 400 | Invalid input data | No |
| MISSING_REQUIRED_FIELD | 400 | Missing required field | No |
| INVALID_FIELD_TYPE | 400 | Invalid field type | No |
| INVALID_FORMAT | 400 | Invalid format (email, date, etc.) | No |
| VALUE_TOO_LONG | 400 | Value exceeds maximum length | No |
| VALUE_TOO_SHORT | 400 | Value below minimum length | No |
| DUPLICATE_VALUE | 409 | Duplicate value (unique constraint) | No |
| UNAUTHORIZED | 401 | Authentication required | No |
| INVALID_TOKEN | 401 | Invalid authentication token | No |
| EXPIRED_TOKEN | 401 | Expired authentication token | No |
| FORBIDDEN | 403 | Permission denied | No |
| INSUFFICIENT_PERMISSION | 403 | Insufficient permissions | No |
| RESOURCE_NOT_FOUND | 404 | Resource not found | No |
| METHOD_NOT_ALLOWED | 405 | HTTP method not allowed | No |
| CONFLICT | 409 | Conflict with existing resource | No |
| RATE_LIMIT_EXCEEDED | 429 | Rate limit exceeded | Yes |
| INTERNAL_ERROR | 500 | Internal server error | Yes |
| SERVICE_UNAVAILABLE | 503 | Service temporarily unavailable | Yes |
| DATABASE_ERROR | 500 | Database operation failed | Yes |
| EXTERNAL_SERVICE_ERROR | 502 | External service error | Yes |

---

## Error Type Categorization

### Validation Errors

**Status Code:** 400 Bad Request

**Examples:**
```python
# Invalid email
if not is_valid_email(email):
    return error_response(
        message="Invalid email format",
        error_code="INVALID_FORMAT",
        status_code=400
    )

# Password too short
if len(password) < 12:
    return error_response(
        message="Password must be at least 12 characters",
        error_code="VALUE_TOO_SHORT",
        status_code=400
    )
```

### Authentication Errors

**Status Code:** 401 Unauthorized

**Examples:**
```python
# Missing token
if not get_jwt_identity():
    return error_response(
        message="Authentication token required",
        error_code="MISSING_TOKEN",
        status_code=401
    )

# Invalid token
if not verify_jwt_token(token):
    return error_response(
        message="Invalid authentication token",
        error_code="INVALID_TOKEN",
        status_code=401
    )
```

### Authorization Errors

**Status Code:** 403 Forbidden

**Examples:**
```python
# Permission denied
if not has_permission(user, resource, action):
    return error_response(
        message="You don't have permission to perform this action",
        error_code="INSUFFICIENT_PERMISSION",
        status_code=403
    )

# Cross-tenant access attempt
if form.organization_id != user.organization_id:
    return error_response(
        message="Resource not found",
        error_code="RESOURCE_NOT_FOUND",
        status_code=404
    )
```

### Not Found Errors

**Status Code:** 404 Not Found

**Examples:**
```python
# Form not found
if not form:
    return error_response(
        message="Form not found",
        error_code="RESOURCE_NOT_FOUND",
        status_code=404
    )
```

### Rate Limit Errors

**Status Code:** 429 Too Many Requests

**Examples:**
```python
# Rate limit exceeded
if is_rate_limited(user):
    return error_response(
        message="Rate limit exceeded. Please try again later.",
        error_code="RATE_LIMIT_EXCEEDED",
        status_code=429
    ), {"Retry-After": "60"}
```

### Server Errors

**Status Code:** 500 Internal Server Error

**Examples:**
```python
# Database error
try:
    form.save()
except Exception as e:
    error_logger.error(f"Database error: {str(e)}", exc_info=True)
    return error_response(
        message="An error occurred while processing your request",
        error_code="DATABASE_ERROR",
        status_code=500
    )
```

---

## Retry Logic

### Retry-able Errors

**Retry-able Error Codes:**
- `INTERNAL_ERROR` - Server error
- `SERVICE_UNAVAILABLE` - Service down
- `DATABASE_ERROR` - Database error
- `EXTERNAL_SERVICE_ERROR` - External service error
- `RATE_LIMIT_EXCEEDED` - Rate limit (with backoff)

**Non-Retry-able Errors:**
- `VALIDATION_ERROR` - Client error
- `INVALID_INPUT` - Client error
- `UNAUTHORIZED` - Auth error
- `FORBIDDEN` - Permission error
- `RESOURCE_NOT_FOUND` - Not found

### Retry Strategy

**Exponential Backoff:**

```python
# utils/retry.py
import time
import random

def retry_with_backoff(func, max_retries=3, initial_delay=1):
    """Retry function with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise

            # Calculate delay with jitter
            delay = initial_delay * (2 ** attempt) + random.uniform(0, 1)
            time.sleep(delay)
```

**Client-Side Retry:**

```javascript
// JavaScript retry logic
async function fetchWithRetry(url, options, maxRetries = 3) {
    for (let attempt = 0; attempt < maxRetries; attempt++) {
        try {
            const response = await fetch(url, options);

            // Check if retry-able error
            if (response.status === 500 ||
                response.status === 503 ||
                response.status === 429) {

                // Calculate backoff
                const delay = Math.pow(2, attempt) * 1000;

                // Wait before retry
                await new Promise(resolve => setTimeout(resolve, delay));

                continue;
            }

            // Return response
            return response;

        } catch (error) {
            if (attempt === maxRetries - 1) {
                throw error;
            }

            // Wait before retry
            const delay = Math.pow(2, attempt) * 1000;
            await new Promise(resolve => setTimeout(resolve, delay));
        }
    }
}
```

---

## Global Error Handlers

### Flask Error Handlers

**Implementation:**

```python
# utils/error_handlers.py
from werkzeug.exceptions import HTTPException

@app.errorhandler(404)
def not_found(error):
    """Handle 404 Not Found errors."""
    return error_response(
        message="Resource not found",
        error_code="RESOURCE_NOT_FOUND",
        status_code=404
    )

@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 Method Not Allowed errors."""
    return error_response(
        message="Method not allowed",
        error_code="METHOD_NOT_ALLOWED",
        status_code=405
    )

@app.errorhandler(422)
def unprocessable_entity(error):
    """Handle 422 Unprocessable Entity errors."""
    return error_response(
        message="Unprocessable entity",
        error_code="UNPROCESSABLE_ENTITY",
        status_code=422
    )

@app.errorhandler(429)
def rate_limit_exceeded(error):
    """Handle 429 Rate Limit Exceeded errors."""
    return error_response(
        message="Rate limit exceeded",
        error_code="RATE_LIMIT_EXCEEDED",
        status_code=429
    )

@app.errorhandler(500)
def internal_server_error(error):
    """Handle 500 Internal Server Error errors."""
    error_logger.error(
        f"Internal server error: {str(error)}",
        exc_info=True
    )
    return error_response(
        message="An internal server error occurred",
        error_code="INTERNAL_ERROR",
        status_code=500
    )

@app.errorhandler(HTTPException)
def handle_http_exception(error):
    """Handle HTTP exceptions."""
    return error_response(
        message=error.description,
        status_code=error.code
    )

@app.errorhandler(Exception)
def handle_exception(error):
    """Handle all uncaught exceptions."""
    error_logger.error(
        f"Unhandled exception: {str(error)}",
        exc_info=True
    )

    # Don't expose error details in production
    if settings.APP_ENV == "production":
        message = "An internal server error occurred"
    else:
        message = str(error)

    return error_response(
        message=message,
        error_code="INTERNAL_ERROR",
        status_code=500
    )
```

---

## Client Error Handling Guidelines

### 1. Check Success Flag

```javascript
// CORRECT - Check success flag
const response = await fetch('/api/v1/forms');
const data = await response.json();

if (data.success) {
    // Handle success
    console.log(data.data);
} else {
    // Handle error
    console.error(data.error);
}

// WRONG - Only check status code
const response = await fetch('/api/v1/forms');

if (response.status === 200) {
    // Handle success
} else {
    // Different logic for each status code
}
```

### 2. Use Error Code

```javascript
// CORRECT - Use error code for specific handling
switch (data.error_code) {
    case 'VALIDATION_ERROR':
        // Show validation errors
        displayValidationErrors(data.errors);
        break;
    case 'UNAUTHORIZED':
        // Redirect to login
        redirectToLogin();
        break;
    case 'FORBIDDEN':
        // Show permission denied message
        showPermissionDenied();
        break;
    default:
        // Show generic error message
        showGenericError(data.error);
}

// WRONG - Generic handling for all errors
showError(data.error);
```

### 3. Implement Retry Logic

```javascript
// CORRECT - Implement retry for retry-able errors
const RETRYABLE_ERRORS = ['INTERNAL_ERROR', 'SERVICE_UNAVAILABLE', 'RATE_LIMIT_EXCEEDED'];

async function apiCall(url, options, retries = 3) {
    for (let i = 0; i < retries; i++) {
        try {
            const response = await fetch(url, options);
            const data = await response.json();

            if (data.success) {
                return data;
            }

            // Check if retry-able
            if (RETRYABLE_ERRORS.includes(data.error_code) && i < retries - 1) {
                const delay = Math.pow(2, i) * 1000;
                await new Promise(resolve => setTimeout(resolve, delay));
                continue;
            }

            // Not retry-able or last retry
            throw new Error(data.error);

        } catch (error) {
            if (i === retries - 1) {
                throw error;
            }

            // Network error - retry
            const delay = Math.pow(2, i) * 1000;
            await new Promise(resolve => setTimeout(resolve, delay));
        }
    }
}

// WRONG - No retry logic
const response = await fetch(url);
const data = await response.json();

if (!data.success) {
    throw new Error(data.error);
}
```

### 4. Display User-Friendly Messages

```javascript
// CORRECT - User-friendly messages
const errorMessages = {
    'VALIDATION_ERROR': 'Please check your input and try again.',
    'UNAUTHORIZED': 'Please log in to continue.',
    'FORBIDDEN': 'You don\'t have permission to access this resource.',
    'RESOURCE_NOT_FOUND': 'The requested resource was not found.',
    'RATE_LIMIT_EXCEEDED': 'You\'ve exceeded the rate limit. Please try again later.',
    'INTERNAL_ERROR': 'An unexpected error occurred. Please try again later.'
};

function showError(error) {
    const message = errorMessages[error.error_code] || 'An error occurred.';
    alert(message);
}

// WRONG - Technical error messages
alert(error.error);  // Shows "Database connection failed"
```

---

## Error Suppression Policy

### Suppressible Errors

**Criteria for Suppression:**
- Non-critical errors
- Transient errors
- Expected failures (e.g., network timeout)
- Errors with acceptable fallback

**Examples:**
```python
# Suppress network timeout errors
try:
    external_service.call()
except TimeoutError:
    # Log error but don't expose to user
    error_logger.warning("External service timeout", exc_info=True)
    # Use cached data or fallback
    return get_cached_data()
```

### Non-Suppressible Errors

**Criteria for Non-Suppression:**
- Security violations
- Data corruption risks
- Authentication/authorization failures
- Regulatory violations

**Examples:**
```python
# Don't suppress authentication errors
if not authenticate_user(user, password):
    error_logger.warning(f"Authentication failed for {email}")
    # Must expose to user
    return error_response(message="Invalid credentials", status_code=401)
```

---

## Error Logging Requirements

### Error Logger vs Audit Logger

**Error Logger:**
- Use for system errors and exceptions
- Include stack traces (exc_info=True)
- Not for security events

**Audit Logger:**
- Use for security events and state changes
- Include user context (who, what, when)
- Not for system errors

### Error Logging Examples

```python
# System error - use error_logger
try:
    form.save()
except Exception as e:
    error_logger.error(
        f"Failed to save form: {str(e)}",
        exc_info=True  # Include stack trace
    )
    return error_response(
        message="An error occurred while saving the form",
        status_code=500
    )

# Security event - use audit_logger
if login_attempts > MAX_ATTEMPTS:
    audit_logger.warning(
        f"Account locked due to excessive failed login attempts: {email}"
    )
```

---

## Best Practices

### 1. Use Consistent Error Format

```python
# CORRECT - Consistent format
return error_response(
    message="Validation failed",
    error_code="VALIDATION_ERROR",
    errors=validation_errors
)

# WRONG - Inconsistent formats
return jsonify({"error": "Validation failed"})  # Sometimes includes error_code, sometimes not
return jsonify({"message": "Not found", "code": 404})  # Different field names
```

### 2. Return Appropriate HTTP Status Codes

```python
# CORRECT - Appropriate status codes
return error_response(message="Not found", status_code=404)
return error_response(message="Unauthorized", status_code=401)
return error_response(message="Rate limit exceeded", status_code=429)

# WRONG - Always return 500
return error_response(message="Not found", status_code=500)
return error_response(message="Unauthorized", status_code=500)
```

### 3. Don't Expose Internal Details

```python
# CORRECT - Generic error in production
if settings.APP_ENV == "production":
    message = "An error occurred while processing your request"
else:
    message = str(error)

# WRONG - Expose internal details
return error_response(message=f"Database error: {str(e)}")
```

### 4. Log All Errors

```python
# CORRECT - Log all errors with context
try:
    form.save()
except Exception as e:
    error_logger.error(
        f"Failed to save form {form_id}: {str(e)}",
        extra={
            "user_id": user_id,
            "organization_id": organization_id,
            "form_id": form_id
        },
        exc_info=True
    )

# WRONG - No logging
try:
    form.save()
except Exception as e:
    return error_response(message="Error occurred")
```

### 5. Provide Retry Information

```python
# CORRECT - Include retry information
if is_rate_limited(user):
    return error_response(
        message="Rate limit exceeded",
        error_code="RATE_LIMIT_EXCEEDED",
        status_code=429
    ), {"Retry-After": str(retry_after_seconds)}

# WRONG - No retry information
if is_rate_limited(user):
    return error_response(
        message="Rate limit exceeded",
        status_code=429
    )
```

---

## References

- [HTTP Status Codes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status)
- [RFC 7807 - Problem Details for HTTP APIs](https://tools.ietf.org/html/rfc7807)
- [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html)
- [Google API Error Handling](https://cloud.google.com/apis/design/errors)
