# Rate Limiting Strategy

**Purpose:** Documentation for rate limiting strategy, per-endpoint limits, tenant-aware limits, and DDoS mitigation.

**Scope:** Rate limiting configuration, progressive delays, auto-ban thresholds, and monitoring for rate limit violations.

---

## Overview

Rate limiting protects the API from abuse, DDoS attacks, and resource exhaustion. The system uses Flask-Limiter with Redis storage to enforce per-endpoint and per-user rate limits while maintaining tenant isolation.

**Key Components:**
- Flask-Limiter with Redis backend
- Per-endpoint rate limit decorators
- Progressive delay for failed attempts
- Tenant-aware rate limiting (future)

---

## Rate Limiting Philosophy

### Defense in Depth

Rate limiting is one layer of a multi-layered defense:

```
Layer 1: WAF (security_waf.py) → Block malicious patterns
Layer 2: Rate Limiting (Flask-Limiter) → Limit request frequency
Layer 3: Authentication → Verify user identity
Layer 4: Authorization → Verify permissions
Layer 5: Business Logic → Validate operations
```

### Rate Limiting Goals

1. **Prevent Abuse:** Limit malicious automated requests
2. **Protect Resources:** Prevent server overload
3. **Maintain Availability:** Ensure fair access for legitimate users
4. **Detect Attacks:** Identify and respond to DDoS attempts

---

## Rate Limit Configuration

### Current Limits

```python
# config/settings.py
class Settings(BaseSettings):
    # Rate limiting
    RATE_LIMIT_LOGIN_ATTEMPTS: str = "5 per minute"
    RATE_LIMIT_PASSWORD_CHANGE: str = "3 per hour"
    RATE_LIMIT_FILE_UPLOAD: str = "10 per minute"
    RATE_LIMIT_EXPORT: str = "5 per hour"
    RATE_LIMIT_OTP_REQUEST: str = "5 per minute"
```

### Per-Endpoint Limits

| Endpoint | Limit | Rationale |
|----------|-------|-----------|
| `POST /auth/login` | 5 per minute | Limit brute force attacks |
| `POST /auth/request-otp` | 5 per minute | Limit SMS abuse |
| `POST /user/change-password` | 3 per hour | Limit password reset abuse |
| `POST /forms/upload` | 10 per minute | Limit file upload abuse |
| `POST /forms/signatures` | 10 per minute | Limit signature abuse |
| `GET /forms/<id>/export/csv` | 5 per hour | Limit export abuse |
| `GET /forms/<id>/export/json` | 5 per hour | Limit export abuse |
| `POST /sms/single` | 10 per minute | Limit SMS abuse |
| `POST /sms/otp` | 5 per minute | Limit OTP abuse |

---

## Implementation

### Flask-Limiter Setup

```python
# app.py
from extensions import limiter

# Configure Limiter with Redis
limiter.init_app(app)

# Storage backend (configured in extensions.py)
# storage_uri = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{limiter_db}"
```

### Basic Rate Limiting

```python
from extensions import limiter

@bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    # ... login logic ...
    return success_response(data={"token": jwt_token})
```

### Key-Based Rate Limiting

```python
# Limit by IP address
@bp.route("/public-endpoint", methods=["GET"])
@limiter.limit("100 per hour", key_func=get_remote_address)
def public_endpoint():
    # ... logic ...
    return success_response(data={})

# Limit by user ID
@bp.route("/protected-endpoint", methods=["GET"])
@jwt_required()
@limiter.limit("1000 per hour", key_func=lambda: get_jwt_identity())
def protected_endpoint():
    # ... logic ...
    return success_response(data={})
```

### Custom Key Function

```python
def get_tenant_and_user_limit_key():
    """Rate limit by tenant and user combination."""
    user = get_current_user()
    return f"tenant:{user.organization_id}:user:{user.id}"

@bp.route("/forms", methods=["GET"])
@jwt_required()
@limiter.limit("100 per minute", key_func=get_tenant_and_user_limit_key)
def list_forms():
    # ... logic ...
    return success_response(data=forms)
```

---

## Progressive Delay (Future)

### Purpose

Implement progressive delays for repeated failures to slow down brute force attacks.

### Implementation (Planned)

```python
# utils/rate_limiting.py (future)
from datetime import datetime, timedelta
import time

def get_progressive_delay(attempt_count: int) -> int:
    """
    Calculate progressive delay based on attempt count.
    Exponential backoff: 2^(attempt_count) seconds, max 60 seconds
    """
    delay = min(2 ** attempt_count, 60)
    return delay

def check_progressive_delay(ip_address: str, endpoint: str):
    """Check if IP should be delayed."""
    redis_key = f"progressive_delay:{endpoint}:{ip_address}"

    # Get attempt count
    attempt_count = redis_client.incr(redis_key)
    redis_client.expire(redis_key, 3600)  # 1 hour TTL

    # If too many attempts, apply delay
    if attempt_count > 5:
        delay = get_progressive_delay(attempt_count - 5)
        time.sleep(delay)

        audit_logger.warning(
            f"Progressive delay applied: {delay}s for "
            f"IP {ip_address} on {endpoint} "
            f"(attempt {attempt_count})"
        )
```

### Usage

```python
@bp.route("/login", methods=["POST"])
def login():
    ip_address = request.remote_addr

    # Apply progressive delay
    check_progressive_delay(ip_address, "/auth/login")

    # ... login logic ...
    return success_response(data={"token": jwt_token})
```

---

## Auto-Ban (Future)

### Purpose

Automatically ban IPs that exceed rate limits repeatedly.

### Implementation (Planned)

```python
# utils/auto_ban.py (future)
def check_auto_ban(ip_address: str):
    """Check if IP is auto-banned."""
    ban_key = f"auto_ban:{ip_address}"
    return redis_client.exists(ban_key)

def apply_auto_ban(ip_address: str, reason: str, duration: int = 3600):
    """Apply auto-ban to IP."""
    ban_key = f"auto_ban:{ip_address}"
    violation_key = f"violations:{ip_address}"

    # Count violations
    violations = redis_client.incr(violation_key)
    redis_client.expire(violation_key, 3600)  # 1 hour

    # If violations exceed threshold, apply ban
    if violations >= 10:
        redis_client.setex(ban_key, duration, reason)

        audit_logger.critical(
            f"Auto-ban applied to IP {ip_address}: "
            f"{reason} (duration: {duration}s, violations: {violations})"
        )
```

### Usage

```python
# WAF middleware
def _block_request(self, attack_type, source, value, client_ip, request_id):
    # ... log violation ...

    # Check for auto-ban
    from utils.auto_ban import apply_auto_ban
    apply_auto_ban(client_ip, f"WAF violation: {attack_type}")

    abort(403, description="Access blocked by security policy.")
```

---

## Tenant-Aware Rate Limiting (Future)

### Purpose

Prevent one tenant from affecting others by implementing per-tenant rate limits.

### Implementation (Planned)

```python
def get_tenant_limit_key():
    """Rate limit by tenant organization ID."""
    user = get_current_user()
    return f"tenant:{user.organization_id}"

@bp.route("/forms", methods=["POST"])
@jwt_required()
@limiter.limit("100 per minute", key_func=get_tenant_limit_key)
def create_form():
    # ... form creation logic ...
    return success_response(data=form)
```

### Benefits

1. **Fair Allocation:** Each tenant gets fair share of resources
2. **Noisy Tenant Isolation:** One abusive tenant doesn't affect others
3. **Tiered Pricing:** Implement different limits per subscription tier

---

## DDoS Mitigation

### Multi-Layer Defense

```
1. Network Layer (Cloudflare, AWS WAF)
   ↓
2. Application Layer (security_waf.py)
   ↓
3. Rate Limiting (Flask-Limiter)
   ↓
4. Auto-Ban (Violations)
   ↓
5. Progressive Delay (Repeated failures)
```

### DDoS Response Procedures

**1. Detection**
```python
# Monitor rate limit violations
if rate_limit_violations_per_minute > 1000:
    trigger_ddos_alert()
```

**2. Containment**
```python
# Tighten limits
current_limit = "100 per minute"
emergency_limit = "10 per minute"

# Enable CAPTCHA
enable_captcha_for_all_requests()
```

**3. Mitigation**
```python
# Block attack IPs
for ip in attack_ips:
    apply_auto_ban(ip, "DDoS attack", duration=86400)  # 24 hours
```

**4. Recovery**
```python
# Gradually restore limits
restore_rate_limits_gradually()
```

---

## Monitoring and Alerting

### Metrics to Track

```python
# Rate limit violations
rate_limit_violations_total = Counter(
    'rate_limit_violations_total',
    'Total rate limit violations',
    ['endpoint', 'limit_type']
)

# Blocked requests
blocked_requests_total = Counter(
    'blocked_requests_total',
    'Total blocked requests',
    ['reason', 'ip_address']
)

# Auto-bans applied
auto_bans_total = Counter(
    'auto_bans_total',
    'Total auto-bans applied',
    ['reason', 'duration']
)
```

### Alert Conditions

```python
# Alert on high violation rate
if rate_limit_violations_per_minute > 100:
    send_alert("High rate limit violations detected")

# Alert on auto-ban spike
if auto_bans_per_hour > 10:
    send_alert("High auto-ban rate detected")

# Alert on DDoS patterns
if concurrent_requests_per_second > 1000:
    send_alert("Potential DDoS attack")
```

### Dashboard Metrics

1. **Rate Limit Violations:** By endpoint, by IP
2. **Blocked Requests:** By reason, by time
3. **Auto-Bans:** Applied, active, expired
4. **Tenant Resource Usage:** Requests per tenant
5. **Response Times:** Under load

---

## Emergency Rate Limit Adjustment

### Procedure

```python
# 1. Update environment variable
export RATE_LIMIT_EMERGENCY="10 per minute"

# 2. Or update settings dynamically
settings.RATE_LIMIT_LOGIN_ATTEMPTS = "2 per minute"

# 3. Restart application
make restart

# 4. Monitor impact
# Watch logs for rate limit violations
# Check system resources
# Verify legitimate users can still access
```

### Rollback

```python
# Restore normal limits
settings.RATE_LIMIT_LOGIN_ATTEMPTS = "5 per minute"
make restart
```

---

## Best Practices

### 1. Use Appropriate Limits

```python
# CORRECT - Sensitive endpoints have stricter limits
@limiter.limit("5 per minute")
def login():
    pass

@limiter.limit("1000 per hour")
def list_forms():
    pass

# WRONG - All endpoints have same limit
@limiter.limit("100 per minute")
def login():
    pass

@limiter.limit("100 per minute")
def list_forms():
    pass
```

### 2. Use Meaningful Keys

```python
# CORRECT - Tenant and user isolation
@limiter.limit("100 per minute", key_func=lambda: f"{tenant_id}:{user_id}")

# WRONG - IP-based limit (not tenant-aware)
@limiter.limit("100 per minute", key_func=get_remote_address)
```

### 3. Log Violations

```python
# CORRECT - Log rate limit violations
audit_logger.warning(
    f"Rate limit exceeded: {limit} for "
    f"IP {ip_address} on endpoint {endpoint}"
)

# WRONG - No logging
@limiter.limit("100 per minute")
def endpoint():
    pass
```

### 4. Handle 429 Responses

```python
# Client-side retry logic
if response.status_code == 429:
    retry_after = int(response.headers.get("Retry-After", 60))
    time.sleep(retry_after)
    retry_request()
```

---

## Configuration Reference

### Rate Limit Settings

```python
# config/settings.py
class Settings(BaseSettings):
    RATE_LIMIT_LOGIN_ATTEMPTS: str = "5 per minute"
    RATE_LIMIT_PASSWORD_CHANGE: str = "3 per hour"
    RATE_LIMIT_FILE_UPLOAD: str = "10 per minute"
    RATE_LIMIT_EXPORT: str = "5 per hour"
    RATE_LIMIT_OTP_REQUEST: str = "5 per minute"
```

### Flask-Limiter Configuration

```python
# extensions.py
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/2",
    strategy="fixed-window",  # or "moving-window"
    storage_options={"socket_connect_timeout": 30},
)
```

---

## Testing

### Unit Tests

```python
def test_rate_limiting():
    """Test that rate limits are enforced."""
    with app.test_client() as client:
        # Make 5 requests (within limit)
        for i in range(5):
            response = client.post("/auth/login", json={...})
            assert response.status_code == 200

        # 6th request should be rate limited
        response = client.post("/auth/login", json={...})
        assert response.status_code == 429
```

---

## References

- [Flask-Limiter Documentation](https://flask-limiter.readthedocs.io/)
- [OWASP Rate Limiting Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Rate_Limiting_Cheat_Sheet.html)
- [NIST SP 800-53: SC-5 Denial of Service Protection](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)
- [Cloudflare DDoS Protection](https://www.cloudflare.com/learning/ddos/what-is-a-ddos-attack/)
