# Security Headers

**Purpose:** Documentation for enhanced security headers including CSP, HSTS, Feature-Policy, and X-Frame-Options.

**Scope:** Security header configuration, Content Security Policy, HTTP Strict Transport Security, and header-based attack prevention.

---

## Overview

Security headers protect against various web vulnerabilities including XSS, clickjacking, and MIME type sniffing. The system uses Flask-Talisman to enforce comprehensive security headers across all responses.

**Key Components:**
- Flask-Talisman initialization in `app.py`
- Content Security Policy (CSP) configuration
- HSTS, Feature-Policy, and X-Frame-Options settings
- Configuration in `config/settings.py`

---

## Security Headers Overview

### Headers Enforced by Talisman

| Header | Purpose | Status |
|--------|---------|--------|
| Content-Security-Policy (CSP) | Prevent XSS and data injection | ✅ Enabled |
| Strict-Transport-Security (HSTS) | Enforce HTTPS connections | ✅ Enabled |
| X-Content-Type-Options | Prevent MIME sniffing | ✅ Enabled |
| X-Frame-Options | Prevent clickjacking | ✅ Enabled |
| X-XSS-Protection | Enable browser XSS filter | ✅ Enabled |
| Feature-Policy | Control browser feature access | ✅ Enabled |
| Referrer-Policy | Control referrer information | 🔜 Planned |

---

## Content Security Policy (CSP)

### Purpose

CSP restricts the sources from which the application can load resources, preventing XSS attacks and data injection.

### Configuration

```python
# config/settings.py
CSP_POLICY: Optional[str] = Field(
    default="default-src 'self'; script-src 'none'; object-src 'none';",
    description="Content-Security-Policy header value"
)
```

### Policy Breakdown

```http
Content-Security-Policy:
    default-src 'self';          # Default to same-origin only
    script-src 'none';          # No inline scripts (REST API)
    object-src 'none';          # No plugins/objects
    base-uri 'self';            # Base URL must be same-origin
    form-action 'self';         # Form submissions to same-origin
    frame-ancestors 'none';    # Cannot be embedded in frames
    upgrade-insecure-requests;  # Upgrade HTTP to HTTPS
```

### Why Strict for REST API

Since this is a REST API (not a web application), we can use strict policies:

- **No scripts needed:** REST APIs return JSON, not HTML
- **No objects needed:** No Flash, Java applets, etc.
- **No frames allowed:** API should not be embedded in iframes

### Relaxation for UI Integration

If the API serves static assets or integrates with frontend:

```python
# More permissive CSP for UI
CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.example.com; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none';"
)
```

### CSP Violation Reporting

```python
# TODO: Implement CSP violation reporting
CSP_REPORT_URI = "https://csp-report.example.com/api/v1/report"

CSP_POLICY = (
    f"default-src 'self'; "
    f"script-src 'none'; "
    f"object-src 'none'; "
    f"report-uri {CSP_REPORT_URI};"
)
```

---

## HTTP Strict Transport Security (HSTS)

### Purpose

HSTS enforces HTTPS connections, preventing SSL stripping attacks.

### Configuration

```python
# config/settings.py
HSTS_MAX_AGE: int = Field(default=31536000, ge=0)  # 1 year in seconds
HSTS_INCLUDE_SUBDOMAINS: bool = Field(default=True)
HSTS_PRELOAD: bool = Field(default=True)
```

### Header Value

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

### Breakdown

- **max-age=31536000:** 1 year (31536000 seconds)
- **includeSubDomains:** Apply to all subdomains
- **preload:** Include in browser HSTS preload list

### Why 1 Year?

Industry standard for HSTS:
- **Short duration:** Not effective (browsers forget quickly)
- **Long duration:** Difficult to revoke
- **1 year:** Balance between effectiveness and revocation

### Preload Considerations

**Benefits:**
- Browsers automatically use HTTPS before first visit
- Protection from day one for new users

**Requirements:**
- Must serve HTTPS on all subdomains
- Must not have valid HSTS errors
- Must submit to preload list

**Submission:**
```bash
# Check preload eligibility
curl -I https://yourdomain.com

# Submit to preload list
https://hstspreload.org/
```

---

## X-Content-Type-Options

### Purpose

Prevents MIME type sniffing by browsers, ensuring files are treated as declared.

### Configuration

```python
# app.py (via Talisman)
x_content_type_options='nosniff'
```

### Header Value

```http
X-Content-Type-Options: nosniff
```

### Attack Prevented

**MIME Sniffing Attack:**
```
1. Attacker uploads malicious.php renamed to image.jpg
2. Server declares Content-Type: image/jpeg
3. Browser sniffs content, detects PHP
4. Browser executes PHP code
```

**With nosniff:**
```
1. Attacker uploads malicious.php renamed to image.jpg
2. Server declares Content-Type: image/jpeg
3. Browser trusts Content-Type (no sniffing)
4. Browser treats as image, not executable
```

---

## X-Frame-Options

### Purpose

Prevents clickjacking attacks by blocking framing.

### Configuration

```python
# app.py (via Talisman)
frame_options='DENY'
```

### Header Value

```http
X-Frame-Options: DENY
```

### Options

| Value | Meaning |
|-------|---------|
| `DENY` | No framing allowed (strictest) |
| `SAMEORIGIN` | Allow framing from same origin only |

### Why DENY?

Since this is a REST API:
- No UI elements to frame
- Should never be embedded in iframes
- DENY provides strongest protection

### Clickjacking Prevention

```
Without X-Frame-Options:
┌─────────────────────────────────┐
│ Malicious Site (evil.com)       │
│ ┌───────────────────────────┐  │
│ │ Transparent iframe over    │  │
│ │ legitimate site (api.com) │  │
│ └───────────────────────────┘  │
│ [Click to win prize!]          │
└─────────────────────────────────┘

With X-Frame-Options: DENY:
┌─────────────────────────────────┐
│ Malicious Site (evil.com)       │
│ [Blocked: X-Frame-Options: DENY]│
└─────────────────────────────────┘
```

---

## X-XSS-Protection

### Purpose

Enables browser's built-in XSS filter.

### Configuration

```python
# app.py (via Talisman)
x_xss_protection='1; mode=block'
```

### Header Value

```http
X-XSS-Protection: 1; mode=block
```

### Breakdown

- **1:** Enable XSS filter
- **mode=block:** Block page if XSS detected (vs. sanitizing)

### Modern Relevance

**Note:** Modern browsers (Chrome, Firefox, Safari) ignore this header in favor of CSP.

**Reason for Keeping:**
- Older browsers still use it
- Defense in depth
- No harm in enabling

---

## Feature-Policy

### Purpose

Controls which browser features the application can use.

### Configuration

```python
# app.py (via Talisman)
feature_policy={
    "accelerometer": "'none'",
    "ambient-light-sensor": "'none'",
    "autoplay": "'none'",
    "battery": "'none'",
    "camera": "'none'",
    "display-capture": "'none'",
    "document-domain": "'none'",
    "encrypted-media": "'none'",
    "execution-while-not-rendered": "'none'",
    "fullscreen": "'none'",
    "geolocation": "'none'",
    "gyroscope": "'none'",
    "magnetometer": "'none'",
    "microphone": "'none'",
    "midi": "'none'",
    "navigation-override": "'none'",
    "payment": "'none'",
    "picture-in-picture": "'none'",
    "publickey-credentials-get": "'none'",
    "speaker": "'none'",
    "sync-xhr": "'none'",
    "usb": "'none'",
    "vr": "'none'",
}
```

### Why Disable All Features?

As a REST API:
- No access to device sensors needed
- No camera/microphone access
- No geolocation
- Disabling reduces attack surface

### For UI Integration

If serving frontend:

```python
feature_policy={
    "camera": "'self'",
    "microphone": "'self'",
    "geolocation": "'self'",
    "fullscreen": "'self'",
    # ... other features as needed
}
```

---

## Referrer-Policy (Planned)

### Purpose

Controls how much referrer information is sent with requests.

### Planned Configuration

```python
# Future addition
referrer_policy = "strict-origin-when-cross-origin"
```

### Options

| Value | Meaning |
|-------|---------|
| `no-referrer` | No referrer sent |
| `same-origin` | Same-origin only |
| `strict-origin` | Origin only (no path) |
| `strict-origin-when-cross-origin` | Origin for cross-origin, full for same-origin |
| `no-referrer-when-downgrade` | Default (not recommended) |

### Recommendation

Use `strict-origin-when-cross-origin` to balance privacy and functionality.

---

## Implementation

### Talisman Initialization

```python
# app.py
from extensions import talisman

talisman.init_app(
    app,
    # Content-Security-Policy
    content_security_policy=settings.CSP_POLICY,

    # HSTS
    force_https=False,  # Temporarily disabled for local validation
    strict_transport_security=True,
    strict_transport_security_preload=settings.HSTS_PRELOAD,
    strict_transport_security_max_age=settings.HSTS_MAX_AGE,
    strict_transport_security_include_subdomains=settings.HSTS_INCLUDE_SUBDOMAINS,

    # Other headers
    feature_policy={...},
    frame_options='DENY',
    x_content_type_options='nosniff',
    x_xss_protection='1; mode=block',
)
```

### Custom Headers

```python
# Add custom security headers
@app.after_request
def add_custom_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response
```

---

## Best Practices

### 1. Use Strict Defaults

```python
# CORRECT - Strict by default
CSP_POLICY = "default-src 'self'; script-src 'none';"

# WRONG - Overly permissive
CSP_POLICY = "default-src *;"
```

### 2. Enable HSTS Gradually

```python
# Step 1: Short duration
HSTS_MAX_AGE = 300  # 5 minutes

# Step 2: Gradually increase
HSTS_MAX_AGE = 86400  # 1 day

# Step 3: Full duration
HSTS_MAX_AGE = 31536000  # 1 year
```

### 3. Test CSP Before Enforcing

```python
# First, use report-only mode
CSP_REPORT_ONLY = "default-src 'self'; script-src 'none';"

# Monitor reports
# Fix violations

# Then, enforce
CSP_POLICY = "default-src 'self'; script-src 'none';"
```

### 4. Update Headers Regularly

```python
# Review security headers quarterly
# Check for new headers
# Update configurations
# Test with security headers scanner
```

---

## Testing

### Security Header Scanner

```bash
# Test security headers
curl -I https://your-api.com

# Use online scanner
https://securityheaders.com/
https://observatory.mozilla.org/
```

### Automated Testing

```python
def test_security_headers():
    """Test that security headers are present."""
    with app.test_client() as client:
        response = client.get("/health")

        assert "Content-Security-Policy" in response.headers
        assert "Strict-Transport-Security" in response.headers
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers
        assert "X-XSS-Protection" in response.headers
```

---

## Configuration Reference

### Security Header Settings

```python
# config/settings.py
class Settings(BaseSettings):
    # Security headers
    HSTS_MAX_AGE: int = Field(default=31536000, ge=0)  # 1 year
    HSTS_INCLUDE_SUBDOMAINS: bool = Field(default=True)
    HSTS_PRELOAD: bool = Field(default=True)

    # Content Security Policy
    CSP_POLICY: Optional[str] = Field(
        default="default-src 'self'; script-src 'none'; object-src 'none';",
        description="Content-Security-Policy header value"
    )
```

### Talisman Configuration

```python
# app.py
talisman.init_app(
    app,
    content_security_policy=settings.CSP_POLICY,
    force_https=False,
    strict_transport_security=True,
    strict_transport_security_preload=settings.HSTS_PRELOAD,
    strict_transport_security_max_age=settings.HSTS_MAX_AGE,
    strict_transport_security_include_subdomains=settings.HSTS_INCLUDE_SUBDOMAINS,
    feature_policy={...},
    frame_options='DENY',
    x_content_type_options='nosniff',
    x_xss_protection='1; mode=block',
)
```

---

## References

- [OWASP Secure Headers Project](https://owasp.org/www-project-secure-headers/)
- [MDN HTTP Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers)
- [Content Security Policy Level 3](https://www.w3.org/TR/CSP3/)
- [HSTS Preload List](https://hstspreload.org/)
- [Mozilla Observatory](https://observatory.mozilla.org/)
- [Security Headers Scanner](https://securityheaders.com/)
