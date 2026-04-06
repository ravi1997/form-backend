# CORS Configuration

**Purpose:** Documentation for Cross-Origin Resource Sharing (CORS) configuration, security considerations, and wildcard restrictions.

**Scope:** CORS origins, credentials handling, preflight requests, security considerations, and wildcard restrictions.

---

## Overview

CORS (Cross-Origin Resource Sharing) is a browser security mechanism that restricts cross-origin HTTP requests. The system uses Flask-CORS to configure CORS policies, ensuring secure cross-origin access while preventing unauthorized requests.

**Key Components:**
- Flask-CORS initialization in `app.py`
- Allowed origins configuration
- Credentials handling
- Preflight request handling

---

## CORS Fundamentals

### Same-Origin Policy

Browsers enforce the Same-Origin Policy (SOP):

```
Same Origin:
- Protocol: https
- Domain: example.com
- Port: 443

Different Origin (Cross-Origin):
- Different protocol: http vs https
- Different domain: example.com vs api.example.com
- Different port: 80 vs 443
```

### CORS Request Flow

**Simple Request:**
```
1. Browser sends request with Origin header
2. Server checks Origin against allowed origins
3. Server sends response with Access-Control-Allow-Origin header
4. Browser allows or blocks response based on header
```

**Preflight Request (OPTIONS):**
```
1. Browser sends OPTIONS request with:
   - Origin
   - Access-Control-Request-Method
   - Access-Control-Request-Headers

2. Server checks preflight request
3. Server sends response with:
   - Access-Control-Allow-Origin
   - Access-Control-Allow-Methods
   - Access-Control-Allow-Headers
   - Access-Control-Max-Age

4. Browser sends actual request
```

---

## CORS Configuration

### Flask-CORS Initialization

```python
# app.py
from extensions import cors

# Configure CORS to support credentials (cookies) cross-origin
cors.init_app(
    app,
    origins=settings.ALLOWED_ORIGINS,
    supports_credentials=True,
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-CSRF-TOKEN-ACCESS",
        "X-CSRF-TOKEN-REFRESH",
        "X-Organization-ID",
    ],
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    max_age=3600,  # Preflight cache duration
)
```

### Configuration Parameters

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `origins` | `["http://localhost:3000", ...]` | Allowed origins |
| `supports_credentials` | `True` | Allow cookies/authorization headers |
| `allow_headers` | `["Content-Type", ...]` | Allowed request headers |
| `methods` | `["GET", "POST", ...]` | Allowed HTTP methods |
| `max_age` | `3600` | Preflight cache duration (seconds) |

---

## Allowed Origins

### Configuration

```python
# config/settings.py
ALLOWED_ORIGINS: list[str] = Field(
    default_factory=lambda: ["http://localhost:3000", "http://localhost:8080"]
)
```

### Environment-Specific Origins

**Development:**
```python
ALLOWED_ORIGINS = [
    "http://localhost:3000",     # React dev server
    "http://localhost:8080",     # Vue dev server
    "http://localhost:4200",     # Angular dev server
]
```

**Staging:**
```python
ALLOWED_ORIGINS = [
    "https://staging.example.com",
    "https://staging-frontend.example.com",
]
```

**Production:**
```python
ALLOWED_ORIGINS = [
    "https://example.com",
    "https://www.example.com",
    "https://app.example.com",
]
```

### Wildcard Restriction

**Validation:**
```python
# config/settings.py
@model_validator(mode="after")
def validate_secrets(self) -> "Settings":
    if self.APP_ENV != "development":
        if "*" in self.ALLOWED_ORIGINS:
            raise ValueError(
                "ALLOWED_ORIGINS must not contain wildcard (*) in non-development "
                "environments. Specify explicit trusted origins."
            )
    return self
```

**Rationale:**
- **Wildcards are insecure:** Allow any origin to make requests
- **Credentials requirement:** `supports_credentials=True` cannot be used with `*`
- **Explicit origins:** Specify exactly which origins are trusted

---

## Credentials Handling

### Cookie-Based Authentication

**Configuration:**
```python
JWT_TOKEN_LOCATION = ["headers", "cookies"]
JWT_COOKIE_SECURE = not DEBUG
JWT_COOKIE_HTTPONLY = True
JWT_COOKIE_SAMESITE = "Lax"
```

**CORS Requirement:**
```python
cors.init_app(
    app,
    origins=settings.ALLOWED_ORIGINS,
    supports_credentials=True,  # Required for cookies
)
```

**Important:** When `supports_credentials=True`:
- `Access-Control-Allow-Origin` must be explicit (not `*`)
- `Access-Control-Allow-Credentials` header is set to `true`
- Browser sends cookies with requests

### Authorization Header

**Configuration:**
```python
allow_headers=[
    "Content-Type",
    "Authorization",  # Bearer token
    "X-CSRF-TOKEN-ACCESS",
]
```

**Client-Side:**
```javascript
fetch('https://api.example.com/protected', {
    method: 'GET',
    headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
    },
    credentials: 'include'  // Include cookies
});
```

---

## Preflight Requests

### Preflight Headers

**Request Headers:**
```http
OPTIONS /form/api/v1/forms HTTP/1.1
Host: api.example.com
Origin: https://example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: Content-Type, Authorization
```

**Response Headers:**
```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://example.com
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, PATCH, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization, X-CSRF-TOKEN-ACCESS
Access-Control-Max-Age: 3600
Access-Control-Allow-Credentials: true
Vary: Origin
```

### Preflight Cache

**Configuration:**
```python
max_age=3600  # Cache preflight response for 1 hour
```

**Benefit:** Reduces number of preflight requests, improving performance.

---

## Security Considerations

### 1. Never Use Wildcards in Production

```python
# CORRECT - Explicit origins
ALLOWED_ORIGINS = ["https://example.com", "https://app.example.com"]

# WRONG - Wildcard (insecure)
ALLOWED_ORIGINS = ["*"]
```

### 2. Use HTTPS in Production

```python
# CORRECT - HTTPS only
ALLOWED_ORIGINS = ["https://example.com"]

# WRONG - HTTP (insecure)
ALLOWED_ORIGINS = ["http://example.com"]
```

### 3. Restrict Allowed Headers

```python
# CORRECT - Minimal headers
allow_headers=[
    "Content-Type",
    "Authorization",
    "X-CSRF-TOKEN-ACCESS",
]

# WRONG - All headers (insecure)
allow_headers="*"
```

### 4. Validate Origin on Server

```python
# Additional origin validation
from flask import request

@bp.route("/protected", methods=["POST"])
@jwt_required()
def protected():
    origin = request.headers.get("Origin")

    # Validate origin matches allowed origins
    if origin not in settings.ALLOWED_ORIGINS:
        audit_logger.warning(
            f"Invalid origin in request: {origin}"
        )
        return error_response(
            message="Invalid origin",
            status_code=403
        )

    # ... process request ...
    return success_response(data={})
```

### 5. Use Vary Header

```python
# Flask-CORS automatically adds Vary: Origin
# This ensures correct caching behavior
```

---

## Common CORS Issues

### 1. Credentials and Wildcard

**Error:**
```
Access to fetch at 'https://api.example.com' from origin 'https://example.com'
has been blocked by CORS policy: The value of the
'Access-Control-Allow-Origin' header in the response
must not be the wildcard '*' when the request's
credentials mode is 'include'.
```

**Solution:**
```python
# Use explicit origins instead of wildcard
ALLOWED_ORIGINS = ["https://example.com"]
cors.init_app(app, origins=ALLOWED_ORIGINS, supports_credentials=True)
```

### 2. Preflight Failure

**Error:**
```
Request header field X-Custom-Header is not allowed
by Access-Control-Allow-Headers in preflight response.
```

**Solution:**
```python
# Add header to allow_headers
allow_headers=[
    "Content-Type",
    "Authorization",
    "X-Custom-Header",  # Add custom header
]
```

### 3. Method Not Allowed

**Error:**
```
Method PUT is not allowed by Access-Control-Allow-Methods
in preflight response.
```

**Solution:**
```python
# Add method to allowed methods
methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
```

### 4. Origin Mismatch

**Error:**
```
The 'Access-Control-Allow-Origin' header has a value
'https://staging.example.com' that is not equal
to the supplied origin 'https://example.com'.
```

**Solution:**
```python
# Add origin to allowed origins
ALLOWED_ORIGINS = [
    "https://example.com",
    "https://staging.example.com",  # Add staging origin
]
```

---

## Testing

### Unit Tests

```python
def test_cors_headers():
    """Test that CORS headers are present."""
    with app.test_client() as client:
        response = client.get("/health")

        assert "Access-Control-Allow-Origin" in response.headers
        assert response.headers["Access-Control-Allow-Credentials"] == "true"

def test_preflight_request():
    """Test preflight request handling."""
    with app.test_client() as client:
        response = client.options(
            "/form/api/v1/forms",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type, Authorization"
            }
        )

        assert response.status_code == 204
        assert "Access-Control-Allow-Methods" in response.headers
        assert "Access-Control-Allow-Headers" in response.headers

def test_wildcard_restriction():
    """Test that wildcard is blocked in production."""
    settings.APP_ENV = "production"
    settings.ALLOWED_ORIGINS = ["*"]

    with pytest.raises(ValueError) as exc_info:
        Settings()

    assert "wildcard" in str(exc_info.value).lower()
```

---

## Best Practices

### 1. Use Explicit Origins

```python
# CORRECT - Explicit origins
ALLOWED_ORIGINS = ["https://example.com", "https://app.example.com"]

# WRONG - Wildcard (insecure)
ALLOWED_ORIGINS = ["*"]
```

### 2. Separate Configurations per Environment

```python
# CORRECT - Environment-specific origins
if APP_ENV == "development":
    ALLOWED_ORIGINS = ["http://localhost:3000"]
elif APP_ENV == "production":
    ALLOWED_ORIGINS = ["https://example.com"]

# WRONG - Same origins for all environments
ALLOWED_ORIGINS = ["http://localhost:3000", "https://example.com"]
```

### 3. Minimize Allowed Headers

```python
# CORRECT - Minimal headers
allow_headers=[
    "Content-Type",
    "Authorization",
]

# WRONG - All headers (insecure)
allow_headers="*"
```

### 4. Use HTTPS in Production

```python
# CORRECT - HTTPS only
ALLOWED_ORIGINS = ["https://example.com"]

# WRONG - HTTP (insecure)
ALLOWED_ORIGINS = ["http://example.com"]
```

### 5. Validate Origin Server-Side

```python
# CORRECT - Additional server-side validation
origin = request.headers.get("Origin")
if origin not in settings.ALLOWED_ORIGINS:
    return error_response(message="Invalid origin", status_code=403)

# WRONG - Trust CORS headers only
# CORS is browser-enforced, not server-enforced
```

---

## Configuration Reference

### CORS Settings

```python
# config/settings.py
class Settings(BaseSettings):
    ALLOWED_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:8080"]
    )
```

### Flask-CORS Configuration

```python
# app.py
cors.init_app(
    app,
    origins=settings.ALLOWED_ORIGINS,
    supports_credentials=True,
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-CSRF-TOKEN-ACCESS",
        "X-CSRF-TOKEN-REFRESH",
        "X-Organization-ID",
    ],
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    max_age=3600,
)
```

---

## References

- [MDN CORS Documentation](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)
- [Flask-CORS Documentation](https://flask-cors.readthedocs.io/)
- [OWASP CORS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Origin_Resource_Sharing_Cheat_Sheet.html)
- [W3C CORS Specification](https://www.w3.org/TR/cors/)
- [HTTP Access Control (MDN)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Access_control_CORS)
