# CSRF Protection

**Purpose:** Documentation for Cross-Site Request Forgery (CSRF) protection using the Synchronizer Token Pattern.

**Scope:** CSRF token generation, validation, token lifecycle, exempt paths, and integration with Flask-JWT-Extended.

---

## Overview

CSRF protection prevents attackers from tricking authenticated users into executing unwanted actions on web applications where they are currently authenticated. This system implements the Synchronizer Token Pattern (double-submit cookie) to validate state-changing requests.

**Key Components:**
- `utils/csrf_protection.py` - CSRF protection middleware (282 lines)
- Integration with Flask-JWT-Extended for cookie-based auth
- Token generation, validation, and expiration

---

## CSRF Attack Vector

### How CSRF Works

```
1. User logs into legitimate site (example.com)
2. Server sets authentication cookie (session_id)
3. User visits malicious site (evil.com)
4. Malicious site sends POST request to example.com
5. Browser automatically includes authentication cookie
6. Server executes action on behalf of user
```

### Example Attack

**Malicious HTML:**
```html
<!-- On evil.com -->
<form action="https://example.com/form/api/v1/forms/delete" method="POST">
    <input type="hidden" name="form_id" value="12345">
    <input type="submit" value="Click for Prize!">
</form>
```

**Result:** Form is deleted when user clicks button, even though they didn't intend to.

---

## Synchronizer Token Pattern

### Design

```
GET Request → Generate CSRF Token → Store in Cookie
                    ↓
                    ↓
POST Request → Send CSRF Token (Header or Cookie)
                    ↓
              Compare Request Token with Cookie Token
                    ↓
                    ↓
           Match? → Execute Request
           No Match? → Reject (403)
```

### Token Lifecycle

```
1. Generation (GET request)
   - Generate 32-byte random token (64 hex characters)
   - Store in cookie: csrf_token
   - Store timestamp in session: csrf_secret_timestamp
   - Cookie: HttpOnly, Secure (production), SameSite=Strict

2. Validation (POST/PUT/DELETE/PATCH request)
   - Extract token from X-CSRF-TOKEN header or cookie
   - Validate token expiration (24 hours)
   - Compare header token with cookie token (if both present)

3. Expiration
   - Tokens expire after 24 hours
   - New token generated on each GET request
```

---

## Configuration

### CSRF Protection Settings

```python
# utils/csrf_protection.py
class CSRFProtection:
    # Token configuration
    CSRF_TOKEN_LENGTH = 32              # 32 bytes = 64 hex characters
    CSRF_TOKEN_EXPIRE_HOURS = 24        # 24 hours
    CSRF_COOKIE_NAME = "csrf_token"
    CSRF_HEADER_NAME = "X-CSRF-TOKEN"
    SESSION_KEY = "csrf_secret"
```

### Cookie Configuration

```python
response.set_cookie(
    self.CSRF_COOKIE_NAME,
    value=csrf_token,
    max_age=self.CSRF_TOKEN_EXPIRE_HOURS * 3600,
    httponly=True,                       # Prevent JavaScript access
    secure=not self.app.debug,           # HTTPS only in production
    samesite="Strict",                  # Prevent cross-site cookie sending
)
```

### Exempt Paths

```python
def _is_csrf_exempt_path(self) -> bool:
    """Check if current path is exempt from CSRF validation."""
    exempt_paths = [
        "/form/api/v1/auth/login",
        "/form/api/v1/auth/register",
        "/form/api/v1/auth/request-otp",
        "/form/api/v1/docs",
        "/health",
    ]

    for exempt_path in exempt_paths:
        if request.path.startswith(exempt_path):
            return True

    return False
```

**Rationale for Exemptions:**
- `/auth/login`, `/auth/register`, `/auth/request-otp`: No session to protect
- `/docs`: Public API documentation
- `/health`: Health check endpoint

---

## Token Generation

### Secure Random Generation

```python
import secrets

def generate_csrf_token(self) -> str:
    """Generate a new CSRF token."""
    return secrets.token_hex(self.CSRF_TOKEN_LENGTH)
```

**Security Properties:**
- Cryptographically secure random number generator
- 32 bytes = 256 bits of entropy
- Hexadecimal encoding (URL-safe)

### Token Storage

```python
def add_csrf_token_to_response(self, response):
    """Add CSRF token to response."""
    csrf_token = self.generate_csrf_token()
    session[f"{self.SESSION_KEY}_timestamp"] = time.time()

    # Store in cookie
    response.set_cookie(
        self.CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=self.CSRF_TOKEN_EXPIRE_HOURS * 3600,
        httponly=True,
        secure=not self.app.debug,
        samesite="Strict",
    )

    # Also add to response data for client access
    if hasattr(response, "json"):
        data = response.get_json()
        if isinstance(data, dict):
            data["csrf_token"] = csrf_token
            response.data = jsonify(data)

    return response
```

---

## Token Validation

### Validation Flow

```python
def _validate_csrf_token(self):
    """Validate CSRF token for state-changing requests."""
    # 1. Skip safe methods
    if request.method in ("GET", "OPTIONS", "HEAD"):
        return

    # 2. Skip exempt paths
    if self._is_csrf_exempt_path():
        return

    # 3. Get tokens
    cookie_token = self.get_csrf_token_from_cookie()
    header_token = self.get_csrf_token_from_header()

    # 4. Validate at least one token present
    if not cookie_token and not header_token:
        abort(403, description="CSRF token missing")

    # 5. Validate header token
    if header_token:
        if cookie_token and secrets.compare_digest(header_token, cookie_token):
            return  # Tokens match
        self._validate_token_expiration(header_token)
        return

    # 6. Validate cookie token
    if cookie_token:
        self._validate_token_expiration(cookie_token)
        return

    # 7. No valid token found
    abort(403, description="Invalid CSRF token")
```

### Expiration Validation

```python
def _validate_token_expiration(self, token: str):
    """Validate that CSRF token hasn't expired."""
    token_timestamp = session.get(f"{self.SESSION_KEY}_timestamp")
    if not token_timestamp:
        abort(403, description="CSRF token expired")

    # Check age
    current_time = time.time()
    token_age_seconds = current_time - token_timestamp
    max_age_seconds = self.CSRF_TOKEN_EXPIRE_HOURS * 3600

    if token_age_seconds > max_age_seconds:
        app_logger.warning(
            f"CSRF token expired: Age {token_age_seconds}s > {max_age_seconds}s"
        )
        abort(403, description="CSRF token expired")
```

---

## Usage Examples

### 1. Initializing CSRF Protection

```python
# app.py
from utils.csrf_protection import init_csrf_protection

app = create_app()
csrf = init_csrf_protection(app)
```

### 2. Protected Route

```python
from utils.csrf_protection import csrf_protection

@bp.route("/api/submit", methods=["POST"])
@csrf_protection.require_csrf_token
def submit_form():
    # CSRF validation happens automatically
    data = request.json
    # ... process form submission ...
    return success_response(data={"status": "success"})
```

### 3. Client-Side Integration

```javascript
// GET request - receive CSRF token
fetch('/form/api/v1/form/data')
    .then(response => response.json())
    .then(data => {
        // Store CSRF token
        localStorage.setItem('csrfToken', data.csrf_token);
    });

// POST request - include CSRF token
fetch('/form/api/v1/form/submit', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRF-TOKEN': localStorage.getItem('csrfToken'),
        'Authorization': `Bearer ${accessToken}`
    },
    body: JSON.stringify({ data: formData })
});
```

### 4. Cookie-Based Auth with CSRF

```python
# With Flask-JWT-Extended cookie auth
@bp.route("/api/protected", methods=["POST"])
@jwt_required()
def protected_route():
    # CSRF token in X-CSRF-TOKEN-ACCESS header
    # Required for state-changing requests with cookie auth
    data = request.json
    # ... process ...
    return success_response(data=data)
```

---

## Integration with Flask-JWT-Extended

### JWT Cookie Configuration

```python
# app.py
app.config.from_mapping({
    # JWT cookie settings
    JWT_TOKEN_LOCATION=["headers", "cookies"],
    JWT_ACCESS_COOKIE_PATH="/form/api/",
    JWT_REFRESH_COOKIE_PATH="/form/api/v1/auth/refresh",
    JWT_COOKIE_SECURE=not settings.DEBUG,
    JWT_COOKIE_HTTPONLY=True,
    JWT_COOKIE_SAMESITE="Lax",  # Changed from Strict for cookie auth
    JWT_COOKIE_CSRF_PROTECT=True,
    JWT_ACCESS_CSRF_HEADER_NAME="X-CSRF-TOKEN-ACCESS",
    JWT_REFRESH_CSRF_HEADER_NAME="X-CSRF-TOKEN-REFRESH",
})
```

### Request Flow

```
1. Login
   POST /form/api/v1/auth/login
   Response: Set access_token cookie, Set csrf_token cookie

2. GET Request
   GET /form/api/v1/form/data
   Headers: Cookie: access_token=xxx, csrf_token=yyy

3. POST Request
   POST /form/api/v1/form/submit
   Headers:
     Cookie: access_token=xxx, csrf_token=yyy
     X-CSRF-TOKEN-ACCESS: yyy (matches csrf_token)
     Content-Type: application/json
```

---

## Best Practices

### 1. Always Include CSRF Token for State Changes

```javascript
// CORRECT
fetch('/api/submit', {
    method: 'POST',
    headers: {
        'X-CSRF-TOKEN': csrfToken,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
});

// WRONG - No CSRF token
fetch('/api/submit', {
    method: 'POST',
    body: JSON.stringify(data)
});
```

### 2. Use Constant-Time Comparison

```python
# CORRECT - Use secrets.compare_digest
if secrets.compare_digest(header_token, cookie_token):
    return True

# WRONG - Prone to timing attacks
if header_token == cookie_token:
    return True
```

### 3. Regenerate Tokens Frequently

```python
# Generate new token on each GET request
def get_data():
    data = {"data": sensitive_info}
    response = jsonify(data)
    csrf.add_csrf_token_to_response(response)
    return response
```

### 4. Log Validation Failures

```python
from logger.unified_logger import audit_logger

def _block_request(self, reason: str):
    audit_logger.warning(
        f"CSRF validation failed: {reason} - "
        f"IP: {request.remote_addr} - Path: {request.path}"
    )
    abort(403, description=reason)
```

### 5. Use HttpOnly Cookies

```python
# CORRECT - HttpOnly prevents JavaScript access
response.set_cookie(
    "csrf_token",
    value=token,
    httponly=True
)

# WRONG - JavaScript can steal token
response.set_cookie("csrf_token", value=token)
```

---

## Security Considerations

### 1. SameSite Cookie Attribute

**Strict:** Cookie not sent with cross-site requests (most secure)

**Lax:** Cookie sent with top-level navigation (needed for cookie auth)

**Recommendation:** Use `SameSite=Strict` for CSRF token, `SameSite=Lax` for JWT cookie

### 2. Secure Cookie Attribute

**Development:** `Secure=False` (works with HTTP)

**Production:** `Secure=True` (only sent over HTTPS)

**Configuration:**
```python
secure=not self.app.debug
```

### 3. Token Entropy

32 bytes = 256 bits of entropy

**Probability of Guessing:**
- 1 in 2^256 (practically impossible)
- Brute force not feasible

### 4. Token Expiration

**24-hour expiration:** Balances security and usability

**Risks:**
- Short expiration: Users need to re-authenticate
- Long expiration: Increased window for token theft

**Recommendation:** 24 hours is standard for session-based applications

---

## Testing

### Unit Tests

```python
def test_token_generation():
    from utils.csrf_protection import CSRFProtection

    csrf = CSRFProtection(app)
    token = csrf.generate_csrf_token()

    assert len(token) == 64  # 32 bytes = 64 hex chars
    assert all(c in "0123456789abcdef" for c in token)

def test_token_expiration():
    from utils.csrf_protection import CSRFProtection

    csrf = CSRFProtection(app)

    # Set old timestamp
    session["csrf_secret_timestamp"] = time.time() - 25 * 3600

    with pytest.raises(abort) as exc_info:
        csrf._validate_token_expiration("token")

    assert exc_info.value.code == 403
    assert "expired" in str(exc_info.value.description).lower()

def test_exempt_paths():
    from utils.csrf_protection import CSRFProtection

    csrf = CSRFProtection(app)

    with app.test_request_context("/form/api/v1/auth/login"):
        assert csrf._is_csrf_exempt_path() == True

    with app.test_request_context("/form/api/v1/form/submit"):
        assert csrf._is_csrf_exempt_path() == False
```

---

## Configuration Reference

### CSRF Protection Constants

```python
# utils/csrf_protection.py
CSRF_TOKEN_LENGTH = 32
CSRF_TOKEN_EXPIRE_HOURS = 24
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-TOKEN"
SESSION_KEY = "csrf_secret"
```

### Flask-JWT-Extended Configuration

```python
# app.py
JWT_COOKIE_CSRF_PROTECT = True
JWT_ACCESS_CSRF_HEADER_NAME = "X-CSRF-TOKEN-ACCESS"
JWT_REFRESH_CSRF_HEADER_NAME = "X-CSRF-TOKEN-REFRESH"
JWT_COOKIE_SAMESITE = "Lax"
JWT_COOKIE_SECURE = not DEBUG
JWT_COOKIE_HTTPONLY = True
```

---

## References

- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP Synchronizer Token Pattern](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#synchronizer-token-pattern)
- [CWE-352: Cross-Site Request Forgery (CSRF)](https://cwe.mitre.org/data/definitions/352.html)
- [RFC 7231 - HTTP Semantics](https://tools.ietf.org/html/rfc7231)
