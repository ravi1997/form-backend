# Web Application Firewall (WAF)

**Purpose:** Documentation for the Web Application Firewall (WAF) implementation protecting against OWASP Top 10 attacks.

**Scope:** WAF patterns, blocked attack vectors, tuning guidelines, exempt paths, and false positive handling.

---

## Overview

The WAF middleware provides a first line of defense against common web application attacks by inspecting and blocking malicious requests before they reach application logic. It implements OWASP Top 10 protections including SQL injection, XSS, path traversal, and command injection.

**Key Components:**
- `middleware/security_waf.py` - WAF implementation (135 lines)
- OWASP Top 10 pattern matching
- Request inspection (path, query, headers, body)
- Logging and alerting

---

## OWASP Top 10 Protections

### 1. SQL Injection Prevention

**Attack Vector:** SQL injection attempts in request parameters.

**Patterns Blocked:**
```python
SQLI_PATTERNS = [
    # Single quote and comment variations
    re.compile(r"(\%27)|(\-\-)|(\%23)|(#)", re.IGNORECASE),
    # Operator and value patterns
    re.compile(r"((\%3D)|(=))[^\n]*((%27)|(\')|(\-\-)|(%3B)|(;))", re.IGNORECASE),
    # OR operator patterns
    re.compile(r"\w*((\%27)|(\'))((\%6F)|o|(\%4F))((\%72)|r|(\%52))", re.IGNORECASE),
    # UNION injection
    re.compile(r"((\%27)|(\'))\s*union", re.IGNORECASE),
    # Stored procedure injection
    re.compile(r"exec(\s|\+)+(s|x)p\w+", re.IGNORECASE),
    # Explicit SQL keywords
    re.compile(r"SELECT\s+.*\s+FROM", re.IGNORECASE),
    re.compile(r"INSERT\s+INTO", re.IGNORECASE),
    re.compile(r"DROP\s+TABLE", re.IGNORECASE),
]
```

**Example Attacks Blocked:**
- `' OR '1'='1`
- `1' UNION SELECT username, password FROM users`
- `'; DROP TABLE users; --`
- `1'; EXEC xp_cmdshell('dir')`

**Note:** This system uses MongoDB (NoSQL), but SQL injection patterns are blocked to prevent:
- Migration to SQL databases
- Integration with external SQL systems
- General injection patterns

### 2. Cross-Site Scripting (XSS) Prevention

**Attack Vector:** Script injection in request parameters.

**Patterns Blocked:**
```python
XSS_PATTERNS = [
    # HTML tag patterns
    re.compile(r"((\%3C)|<)((\%2F)|\/)*[a-z0-9\%]+((\%3E)|>)", re.IGNORECASE),
    # IMG tag patterns
    re.compile(r"((\%3C)|<)((\%69)|i|(\%49))((\%6D)|m|(\%4D))((\%67)|g|(\%47))[^\n]+((\%3E)|>)", re.IGNORECASE),
    # Any HTML tag
    re.compile(r"((\%3C)|<)[^\n]+((\%3E)|>)", re.IGNORECASE),
    # JavaScript URLs
    re.compile(r"javascript:", re.IGNORECASE),
    # Event handlers
    re.compile(r"onerror=", re.IGNORECASE),
    re.compile(r"onload=", re.IGNORECASE),
    # Alert function
    re.compile(r"alert\(", re.IGNORECASE),
]
```

**Example Attacks Blocked:**
- `<script>alert('XSS')</script>`
- `<img src=x onerror=alert('XSS')>`
- `javascript:alert('XSS')`
- `<svg/onload=alert('XSS')>`

### 3. Path Traversal Prevention

**Attack Vector:** Directory traversal attempts to access restricted files.

**Patterns Blocked:**
```python
PATH_TRAVERSAL_PATTERNS = [
    # Parent directory traversal
    re.compile(r"\.\.\/", re.IGNORECASE),
    # System file paths
    re.compile(r"\/etc\/passwd", re.IGNORECASE),
    re.compile(r"\/etc\/shadow", re.IGNORECASE),
    # Windows paths
    re.compile(r"C:\\", re.IGNORECASE),
]
```

**Example Attacks Blocked:**
- `../../../etc/passwd`
- `..\\..\\..\\windows\\system32`
- `/etc/passwd`
- `C:\\Windows\\System32`

**Additional Protection:**
```python
# In file_validator.py
def validate_filename(filename: str):
    if ".." in filename or filename.startswith("/"):
        return False, "Invalid filename: path traversal detected"
```

### 4. Command Injection Prevention

**Attack Vector:** OS command injection through request parameters.

**Patterns Blocked:**
```python
CMD_INJECTION_PATTERNS = [
    # Command separators
    re.compile(r"[;\|&><]", re.IGNORECASE),
    # Command substitution
    re.compile(r"\$\(.*\)", re.IGNORECASE),
    # Backtick substitution
    re.compile(r"`.*`", re.IGNORECASE),
]
```

**Example Attacks Blocked:**
- `; cat /etc/passwd`
- `| ls -la`
- `$(whoami)`
- `` `whoami` ``

**Special Handling:**
```python
# Semicolon allowed in headers (e.g., Accept-Language)
if ";" in value and source.startswith("Header"):
    continue  # Don't block
```

---

## WAF Architecture

### Request Inspection Flow

```
Incoming Request
    ↓
Skip OPTIONS requests (CORS preflight)
    ↓
Skip exempt paths (/static, /docs, /health)
    ↓
Inspect Request Path
    ↓
Inspect Query Parameters
    ↓
Inspect Request Headers (skip known headers)
    ↓
Inspect Request Body (if JSON)
    ↓
Check against all patterns
    ↓
Pattern Match? → Block (403) + Log
No Match? → Continue to application
```

### Implementation

```python
# middleware/security_waf.py
class SecurityWAF:
    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        @app.before_request
        def waf_check():
            # Skip OPTIONS requests
            if request.method == "OPTIONS":
                return

            # Skip static assets
            if any(request.path.startswith(p) for p in [
                "/static", "/flasgger_static",
                "/form/static", "/form/flasgger_static",
                "/form/docs"
            ]):
                return

            request_id = getattr(g, "request_id", "unknown")
            client_ip = request.remote_addr

            # Check all parts of request
            self._check_value(request.path, "Path", client_ip, request_id)

            for key, value in request.args.items():
                self._check_value(f"{key}={value}", "Query Params", client_ip, request_id)

            for key, value in request.headers.items():
                # Skip known safe headers
                if key.lower() in [
                    "user-agent", "referer", "cookie", "accept",
                    "accept-language", "accept-encoding", "content-type",
                    "authorization", "if-none-match", "cache-control",
                    "x-csrf-token-access", "x-csrf-token-refresh",
                    "x-organization-id"
                ]:
                    continue

                self._check_value(key, "Header Key", client_ip, request_id)
                self._check_value(value, "Header Value", client_ip, request_id)

            # Check JSON body
            if request.is_json:
                try:
                    body_str = request.get_data(as_text=True)
                    if body_str:
                        self._check_value(body_str, "JSON Body", client_ip, request_id)
                except Exception:
                    pass
```

### Pattern Checking

```python
def _check_value(self, value, source, client_ip, request_id):
    if not value or not isinstance(value, str):
        return

    # 1. SQL Injection Check
    for pattern in SQLI_PATTERNS:
        if pattern.search(value):
            self._block_request("SQL Injection", source, value, client_ip, request_id)

    # 2. XSS Check
    for pattern in XSS_PATTERNS:
        if pattern.search(value):
            self._block_request("XSS", source, value, client_ip, request_id)

    # 3. Path Traversal Check
    for pattern in PATH_TRAVERSAL_PATTERNS:
        if pattern.search(value):
            self._block_request("Path Traversal", source, value, client_ip, request_id)

    # 4. Command Injection Check
    for pattern in CMD_INJECTION_PATTERNS:
        if pattern.search(value):
            if ";" in value and source.startswith("Header"):
                continue  # Allow semicolon in headers
            self._block_request("Command Injection", source, value, client_ip, request_id)
```

### Request Blocking

```python
def _block_request(self, attack_type, source, value, client_ip, request_id):
    error_msg = (
        f"SECURITY ALERT: Blocked {attack_type} attempt from IP {client_ip} "
        f"in {source}. Value: '{value}'"
    )

    error_logger.error(f"[ReqID: {request_id}] {error_msg}")
    audit_logger.warning(f"[ReqID: {request_id}] {error_msg}")

    # Abort with 403 Forbidden
    abort(403, description="Access blocked by security policy.")
```

---

## Exempt Paths

### Default Exemptions

```python
exempt_paths = [
    "/static",                      # Static assets
    "/flasgger_static",            # Swagger UI assets
    "/form/static",                 # Form static assets
    "/form/flasgger_static",       # Form Swagger UI assets
    "/form/docs",                  # API documentation
]
```

### Rationale

**Static Assets:**
- No user input processing
- File system access only to public files
- Performance optimization

**API Documentation:**
- Public endpoint
- No authentication required
- Swagger UI needs to load resources

### Adding Custom Exemptions

```python
# middleware/security_waf.py
def init_app(self, app):
    @app.before_request
    def waf_check():
        # ... existing code ...

        # Add custom exemptions
        if request.path.startswith("/public-endpoint"):
            return

        # ... continue with WAF checks ...
```

---

## Header Skip List

### Headers Not Inspected

```python
SKIP_HEADERS = [
    "user-agent",           # Browser/user info (can contain special chars)
    "referer",             # Referrer URL (can contain query params)
    "cookie",              # Session cookies (can contain base64)
    "accept",              # Accept header (can contain quality values)
    "accept-language",      # Language preferences (can contain hyphens)
    "accept-encoding",      # Compression preferences (can contain commas)
    "content-type",        # Content type (can contain charset)
    "authorization",       # Auth tokens (can contain special chars)
    "if-none-match",       # ETag (can contain hyphens)
    "cache-control",       # Cache directives (can contain commas)
    "x-csrf-token-access",   # CSRF token (can contain special chars)
    "x-csrf-token-refresh",  # CSRF token (can contain special chars)
    "x-organization-id",      # Organization ID (can contain hyphens)
]
```

### Rationale

These headers can legitimately contain special characters that would trigger false positives.

---

## False Positive Handling

### Common False Positives

**1. Semicolon in Headers**
```
Accept-Language: en-US,en;q=0.9
```
**Solution:** Semicolon allowed in headers

**2. Hyphens in IDs**
```
X-Organization-ID: 12345-67890
```
**Solution:** Hyphen not in blocked patterns

**3. Query Parameters with Special Chars**
```
?search=hello+world&filter=status=active
```
**Solution:** Plus sign not blocked (URL encoding)

### Mitigation Strategies

**1. Pattern Refinement**
```python
# More specific patterns
OLD: re.compile(r";", re.IGNORECASE)
NEW: re.compile(r";\s*(cat|ls|whoami|etc)", re.IGNORECASE)
```

**2. Context-Aware Checking**
```python
# Skip known safe contexts
if source.startswith("Header"):
    # More lenient for headers
    pass
```

**3. Allowlist for Specific Endpoints**
```python
# Exempt specific endpoints
if request.path.startswith("/public-search"):
    return  # Skip WAF for this endpoint
```

**4. Gradual Enforcement**
```python
# Log-only mode first
if settings.WAF_LOG_ONLY:
    audit_logger.warning(f"WAF would block: {attack_type}")
    return  # Don't actually block

# After monitoring, enable blocking
if settings.WAF_ENFORCE:
    abort(403, description="Access blocked by security policy.")
```

---

## Monitoring and Alerting

### Log Levels

```python
# error_logger - All WAF blocks
error_logger.error(f"Blocked {attack_type} from {client_ip}")

# audit_logger - Security events
audit_logger.warning(f"WAF violation: {attack_type} by {client_ip}")
```

### Alerting

```python
# Alert on repeated violations
if waf_violations_per_minute > 100:
    send_alert("High WAF violation rate detected")

# Alert on new attack patterns
if attack_type not in SEEN_ATTACK_TYPES:
    send_alert(f"New attack type detected: {attack_type}")

# Alert on high-risk IP
if ip_violation_count > 10:
    send_alert(f"High-risk IP detected: {client_ip}")
```

### Metrics

```python
waf_blocks_total = Counter(
    'waf_blocks_total',
    'Total WAF blocks',
    ['attack_type', 'source']
)

waf_blocks_total.labels(attack_type='SQLi', source='Query Params').inc()
```

---

## Tuning Guidelines

### Development vs Production

**Development:**
```python
# More lenient for debugging
WAF_ENFORCE = False
WAF_LOG_ONLY = True
```

**Production:**
```python
# Strict blocking enabled
WAF_ENFORCE = True
WAF_LOG_ONLY = False
```

### Environment-Specific Tuning

```python
# config/settings.py
class Settings(BaseSettings):
    WAF_ENFORCE: bool = Field(default=True)
    WAF_LOG_ONLY: bool = Field(default=False)
    WAF_STRICT_MODE: bool = Field(default=False)

    @model_validator(mode="after")
    def configure_waf(self) -> "Settings":
        if self.APP_ENV == "development":
            self.WAF_ENFORCE = False
            self.WAF_LOG_ONLY = True
        elif self.APP_ENV == "production":
            self.WAF_ENFORCE = True
            self.WAF_LOG_ONLY = False

        return self
```

---

## Best Practices

### 1. Test Patterns Before Enabling

```python
# Test mode first
if settings.WAF_TEST_MODE:
    # Log violations but don't block
    audit_logger.warning(f"Would block: {attack_type}")
    return

# After validation, enable blocking
if settings.WAF_ENFORCE:
    abort(403, description="Access blocked by security policy.")
```

### 2. Monitor False Positives

```python
# Review WAF logs regularly
# Identify patterns causing false positives
# Refine patterns or add exemptions
# Document reasons for exemptions
```

### 3. Update Patterns Regularly

```python
# Subscribe to OWASP updates
# Review new attack vectors
# Test and deploy updated patterns
# Monitor for new false positives
```

### 4. Document Exemptions

```python
# Add comments explaining exemptions
# Exempt static assets (no user input processing)
# Exempt /docs (public API documentation)
# Exempt Accept-Language header (contains semicolons)
```

---

## Configuration Reference

### WAF Configuration

```python
# middleware/security_waf.py
class SecurityWAF:
    def __init__(self, app=None):
        # Patterns are defined at module level
        # SQLI_PATTERNS, XSS_PATTERNS, PATH_TRAVERSAL_PATTERNS, CMD_INJECTION_PATTERNS
```

### Settings

```python
# config/settings.py (future additions)
class Settings(BaseSettings):
    WAF_ENFORCE: bool = Field(default=True)
    WAF_LOG_ONLY: bool = Field(default=False)
    WAF_STRICT_MODE: bool = Field(default=False)
    WAF_EXEMPT_PATHS: list[str] = Field(default=[
        "/static", "/flasgger_static",
        "/form/static", "/form/flasgger_static",
        "/form/docs"
    ])
```

---

## Testing

### Unit Tests

```python
def test_sql_injection_blocking():
    with app.test_client() as client:
        # SQL injection attempt
        response = client.get(
            "/search?q=' OR '1'='1"
        )
        assert response.status_code == 403

def test_xss_blocking():
    with app.test_client() as client:
        # XSS attempt
        response = client.get(
            "/search?q=<script>alert('XSS')</script>"
        )
        assert response.status_code == 403

def test_path_traversal_blocking():
    with app.test_client() as client:
        # Path traversal attempt
        response = client.get(
            "/file?path=../../../etc/passwd"
        )
        assert response.status_code == 403

def test_valid_requests_pass():
    with app.test_client() as client:
        # Valid request
        response = client.get(
            "/search?q=hello+world"
        )
        assert response.status_code == 200
```

---

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [OWASP Web Application Firewall Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Web_Application_Firewall_Cheat_Sheet.html)
- [OWASP Testing Guide](https://owasp.org/www-project-web-security-testing-guide/)
- [ModSecurity Rules](https://github.com/coreruleset/coreruleset)
- [NIST SP 800-53: SI-10 Information Input Validation](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)
