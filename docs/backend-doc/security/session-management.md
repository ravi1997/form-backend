# Session Management

**Purpose:** Documentation for JWT token lifecycle, session timeout configuration, concurrent session limits, and session invalidation.

**Scope:** Session timeout, concurrent limits, cleanup procedures, token invalidation, and JWT-based session management.

---

## Overview

The system uses JWT (JSON Web Tokens) for stateless session management. JWTs provide authentication and authorization without server-side session storage, improving scalability and simplifying architecture. This document covers JWT token lifecycle, security considerations, and session management best practices.

**Key Components:**
- Flask-JWT-Extended for token generation and validation
- Token expiration and refresh mechanisms
- Token rotation on password change
- Token invalidation workflows

---

## JWT Token Architecture

### Token Types

| Token Type | Purpose | Expiration | Storage |
|-------------|---------|------------|---------|
| Access Token | API authentication | 60 minutes | Cookie + Header |
| Refresh Token | Get new access token | 30 days | HttpOnly Cookie |

### Token Payload

```python
{
    "sub": user_id,                      # User ID (subject)
    "email": user.email,                 # User email
    "organization_id": org_id,           # Organization ID (tenant)
    "role": user.role,                   # User role
    "iat": issued_at,                    # Issued at timestamp
    "exp": expires_at,                   # Expiration timestamp
    "jti": token_id,                     # JWT ID (for revocation)
    "type": "access" | "refresh"        # Token type
}
```

### Token Storage

**Cookie Storage:**
```python
# config/settings.py
JWT_TOKEN_LOCATION = ["headers", "cookies"]
JWT_ACCESS_COOKIE_PATH = "/form/api/"
JWT_REFRESH_COOKIE_PATH = "/form/api/v1/auth/refresh"
JWT_COOKIE_SECURE = not DEBUG
JWT_COOKIE_HTTPONLY = True
JWT_COOKIE_SAMESITE = "Lax"
JWT_COOKIE_CSRF_PROTECT = True
```

**Header Storage:**
```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## Token Lifecycle

### 1. Token Generation

```python
# routes/v1/auth_route.py
from flask_jwt_extended import create_access_token, create_refresh_token

@bp.route("/login", methods=["POST"])
def login():
    email = request.json.get("email")
    password = request.json.get("password")

    # Authenticate user
    user = authenticate_user(email, password)

    if not user:
        return error_response(message="Invalid credentials", status_code=401)

    # Generate tokens
    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={
            "email": user.email,
            "organization_id": str(user.organization_id),
            "role": user.role
        }
    )

    refresh_token = create_refresh_token(identity=str(user.id))

    # Set cookies
    response = jsonify({
        "access_token": access_token,
        "user": user.to_dict()
    })

    set_access_cookies(response, access_token)
    set_refresh_cookies(response, refresh_token)

    # Log login
    audit_logger.info(
        f"User login successful: {user.email}"
    )

    return response
```

### 2. Token Validation

```python
# Automatic via Flask-JWT-Extended decorators
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

@bp.route("/protected", methods=["GET"])
@jwt_required()
def protected_endpoint():
    # Get JWT identity (user ID)
    user_id = get_jwt_identity()

    # Get JWT claims (additional data)
    jwt_data = get_jwt()
    organization_id = jwt_data.get("organization_id")
    role = jwt_data.get("role")

    # Verify tenant isolation
    user = User.objects(
        id=user_id,
        organization_id=organization_id
    ).first()

    if not user:
        return error_response(message="User not found", status_code=404)

    # ... process request ...
    return success_response(data={})
```

### 3. Token Refresh

```python
@bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    # Get current refresh token
    current_user_id = get_jwt_identity()

    # Generate new access token
    new_access_token = create_access_token(identity=current_user_id)

    # Set new access token cookie
    response = jsonify({"access_token": new_access_token})
    set_access_cookies(response, new_access_token)

    return response
```

### 4. Token Expiration

**Access Token:** 60 minutes (configurable)
```python
# config/settings.py
JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
```

**Refresh Token:** 30 days (configurable)
```python
# config/settings.py
JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
```

---

## Session Timeout Configuration

### Short vs Long Sessions

**Short Sessions (High Security):**
- Access token: 15 minutes
- Refresh token: 7 days
- Use case: Financial applications, admin panels

**Long Sessions (High Usability):**
- Access token: 60 minutes
- Refresh token: 30 days
- Use case: General applications, user dashboards

**Configuration:**
```python
# config/settings.py
JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=15, le=1440)
JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, ge=1, le=365)
```

### Timeout Enforcement

```python
# Flask-JWT-Extended automatically enforces expiration
# If token is expired, 401 Unauthorized is returned

@bp.route("/protected", methods=["GET"])
@jwt_required()
def protected_endpoint():
    # If token is expired, this endpoint won't be reached
    # Client will receive 401 Unauthorized
    return success_response(data={})
```

---

## Concurrent Session Limits

### Purpose

Limit number of active sessions per user to prevent unauthorized access and resource abuse.

### Implementation (Planned)

```python
# models/User.py (future)
class User(Document):
    # ... existing fields ...

    active_sessions = ListField(StringField())
    max_concurrent_sessions = IntField(default=5)
    last_session_activity = DateTimeField()

# routes/v1/auth_route.py (future)
def login():
    # ... authenticate user ...

    # Check concurrent session limit
    if len(user.active_sessions) >= user.max_concurrent_sessions:
        # Revoke oldest session
        oldest_session = user.active_sessions.pop(0)
        revoke_token(oldest_session)

    # Add new session
    session_id = generate_session_id()
    user.active_sessions.append(session_id)
    user.last_session_activity = datetime.utcnow()
    user.save()

    # ... generate and return tokens ...
```

### Client Handling

```python
# Handle session limit exceeded
if response.status_code == 403:
    error_data = response.json()
    if error_data.get("code") == "SESSION_LIMIT_EXCEEDED":
        # Show user message about concurrent sessions
        show_message(
            "You have reached the maximum number of concurrent sessions. "
            "Please log out from another device."
        )
```

---

## Session Cleanup

### Token Expiration Cleanup

**Automatic:** Tokens expire naturally based on JWT `exp` claim.

**No Server-Side Storage:** JWTs are stateless, so no cleanup needed for expired tokens.

### Redis Cache Cleanup (If Using Caching)

```python
# Cache JWT claims for performance
def cache_jwt_claims(jti: str, claims: dict):
    """Cache JWT claims with expiration."""
    redis_client.setex(
        f"jwt_claims:{jti}",
        3600,  # 1 hour TTL
        json.dumps(claims)
    )

# Automatic cleanup via Redis TTL
```

### Background Session Cleanup (Future)

```python
# tasks/session_tasks.py (future)
@celery.task
def cleanup_inactive_sessions():
    """Remove inactive sessions from user records."""
    inactive_threshold = datetime.utcnow() - timedelta(days=30)

    users = User.objects(
        last_session_activity__lt=inactive_threshold
    )

    for user in users:
        user.active_sessions = []
        user.save()

    app_logger.info(f"Cleaned up {len(users)} inactive users")
```

---

## Session Invalidation

### 1. Logout

```python
@bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    # Revoke current tokens
    response = jsonify({"message": "Logged out successfully"})

    # Unset cookies
    unset_jwt_cookies(response)

    # Log logout
    audit_logger.info(
        f"User logout: {get_jwt_identity()}"
    )

    return response
```

### 2. Logout All Sessions (Future)

```python
@bp.route("/logout-all", methods=["POST"])
@jwt_required()
def logout_all():
    user = get_current_user()

    # Clear all active sessions
    user.active_sessions = []
    user.save()

    # Revoke all tokens for user
    for session_id in user.active_sessions:
        revoke_token(session_id)

    # Unset cookies
    response = jsonify({"message": "Logged out from all devices"})
    unset_jwt_cookies(response)

    # Log logout all
    audit_logger.info(
        f"User logged out from all devices: {user.email}"
    )

    return response
```

### 3. Token Revocation on Password Change

```python
# services/user_service.py
def change_password(user_id: str, old_password: str, new_password: str):
    user = User.objects.get(id=user_id)

    # Verify old password
    if not check_password_hash(user.password_hash, old_password):
        raise ValueError("Invalid current password")

    # Update password
    user.password_hash = generate_password_hash(new_password)
    user.last_password_change = datetime.utcnow()
    user.save()

    # Log password change
    audit_logger.info(
        f"Password changed for user: {user.email}"
    )

    # Note: Existing tokens will be invalidated on next refresh
    # due to last_password_change check
```

### 4. Admin-Initiated Logout

```python
@bp.route("/admin/users/<user_id>/logout", methods=["POST"])
@require_roles("admin", "superadmin")
def admin_logout_user(user_id):
    user = User.objects.get(id=user_id)

    # Revoke all user sessions
    user.active_sessions = []
    user.save()

    # Log admin action
    audit_logger.info(
        f"Admin {get_current_user().email} logged out user {user.email}"
    )

    return success_response(message="User logged out")
```

---

## Session Fixation Prevention

### Prevention Strategies

**1. Token Rotation:**
- Generate new token on each refresh
- Old tokens invalidated

**2. Secure Token Storage:**
- HttpOnly cookies (prevent JavaScript access)
- Secure flag (HTTPS only in production)
- SameSite attribute (prevent CSRF)

**3. Unique Session IDs:**
- Each login generates new session
- Session IDs not guessable

### Implementation

```python
# Secure cookie configuration
JWT_COOKIE_HTTPONLY = True
JWT_COOKIE_SECURE = not DEBUG
JWT_COOKIE_SAMESITE = "Lax"
JWT_COOKIE_CSRF_PROTECT = True
```

---

## Session Monitoring

### Active Session Tracking

```python
# Track active sessions per user
def get_active_session_count(user_id: str) -> int:
    """Get number of active sessions for user."""
    user = User.objects(id=user_id).first()
    return len(user.active_sessions) if user else 0

# Track sessions per tenant
def get_tenant_session_count(organization_id: str) -> int:
    """Get total active sessions for tenant."""
    users = User.objects(organization_id=organization_id)
    return sum(len(user.active_sessions) for user in users)
```

### Session Activity Monitoring

```python
# Monitor session activity patterns
def detect_suspicious_activity(user: User) -> bool:
    """Detect suspicious session activity."""
    # Check for rapid session creation
    recent_logins = Session.objects(
        user_id=user.id,
        created_at__gte=datetime.utcnow() - timedelta(hours=1)
    )

    if len(recent_logins) > 5:
        # Too many sessions in short time
        return True

    # Check for geographically impossible logins
    # (requires IP geolocation)

    return False
```

### Alerting

```python
# Alert on suspicious session activity
if detect_suspicious_activity(user):
    send_alert(
        f"Suspicious session activity detected for user: {user.email}"
    )
    audit_logger.warning(
        f"Suspicious session activity: {user.email}"
    )
```

---

## Best Practices

### 1. Use Short Token Expiration

```python
# CORRECT - Short access token expiration
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60

# WRONG - Very long expiration
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours
```

### 2. Rotate Tokens

```python
# CORRECT - Generate new token on refresh
new_access_token = create_access_token(identity=user_id)
set_access_cookies(response, new_access_token)

# WRONG - Reuse same token
return jsonify({"access_token": existing_token})
```

### 3. Logout on Password Change

```python
# CORRECT - Invalidate tokens after password change
user.last_password_change = datetime.utcnow()
user.save()

# Token validation checks last_password_change
# Client must re-authenticate

# WRONG - Allow old tokens to continue working
user.password_hash = new_password_hash
user.save()
# Old tokens still valid!
```

### 4. Use Secure Cookie Attributes

```python
# CORRECT - Secure cookie settings
JWT_COOKIE_HTTPONLY = True
JWT_COOKIE_SECURE = not DEBUG
JWT_COOKIE_SAMESITE = "Lax"
JWT_COOKIE_CSRF_PROTECT = True

# WRONG - Insecure cookie settings
JWT_COOKIE_HTTPONLY = False  # JavaScript can access
JWT_COOKIE_SECURE = False    # Sent over HTTP
JWT_COOKIE_SAMESITE = "None"  # No CSRF protection
```

### 5. Monitor Session Activity

```python
# CORRECT - Monitor for suspicious patterns
if detect_suspicious_activity(user):
    send_alert(f"Suspicious activity: {user.email}")
    revoke_all_user_sessions(user)

# WRONG - No monitoring
# Assume all sessions are legitimate
```

---

## Configuration Reference

### JWT Settings

```python
# config/settings.py
class Settings(BaseSettings):
    # JWT
    JWT_SECRET_KEY: str = "super-secret-key-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
```

### Flask-JWT-Extended Configuration

```python
# app.py
app.config.from_mapping({
    # Token locations
    JWT_TOKEN_LOCATION=["headers", "cookies"],

    # Cookie settings
    JWT_ACCESS_COOKIE_PATH="/form/api/",
    JWT_REFRESH_COOKIE_PATH="/form/api/v1/auth/refresh",
    JWT_COOKIE_SECURE=not settings.DEBUG,
    JWT_COOKIE_HTTPONLY=True,
    JWT_COOKIE_SAMESITE="Lax",
    JWT_COOKIE_CSRF_PROTECT=True,

    # CSRF headers
    JWT_ACCESS_CSRF_HEADER_NAME="X-CSRF-TOKEN-ACCESS",
    JWT_REFRESH_CSRF_HEADER_NAME="X-CSRF-TOKEN-REFRESH",
})
```

---

## Testing

### Unit Tests

```python
def test_token_generation():
    """Test JWT token generation."""
    from flask_jwt_extended import create_access_token

    token = create_access_token(identity="user123")
    assert token is not None
    assert isinstance(token, str)

def test_token_validation():
    """Test JWT token validation."""
    with app.test_request_context():
        # Set token in cookie
        token = create_access_token(identity="user123")
        set_access_cookies(jsonify({}), token)

        # Token should be valid
        with pytest.raises(Exception) as exc_info:
            @jwt_required()
            def protected():
                pass

        # Test that token is required
        assert "Missing JWT" in str(exc_info.value)

def test_token_expiration():
    """Test token expiration."""
    from flask_jwt_extended import create_access_token
    from datetime import timedelta

    # Create token with 1 second expiration
    token = create_access_token(
        identity="user123",
        expires_delta=timedelta(seconds=1)
    )

    # Wait for expiration
    time.sleep(2)

    # Token should be expired
    with app.test_request_context(headers={"Authorization": f"Bearer {token}"}):
        @jwt_required()
        def protected():
            return "success"

        response = protected()
        assert "Token has expired" in str(response)
```

---

## References

- [JWT.io Introduction](https://jwt.io/introduction)
- [RFC 7519 - JSON Web Token (JWT)](https://tools.ietf.org/html/rfc7519)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [Flask-JWT-Extended Documentation](https://flask-jwt-extended.readthedocs.io/)
- [NIST SP 800-63B Digital Identity Guidelines](https://pages.nist.gov/800-63-3/sp800-63b.html)
