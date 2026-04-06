# Security Best Practices

**Purpose:** Documentation for secure coding standards, input validation, authentication security, authorization, error handling, and logging.

**Scope:** OWASP ASVS Level 1-2 compliance, input validation framework, authentication security, authorization design patterns, error handling standards, logging requirements, secure data handling, session management, and code review checklist.

---

## Overview

This document outlines security best practices for the RIDP Form Platform, ensuring secure coding practices throughout the development lifecycle.

**Target Audience:** Backend developers, code reviewers, security engineers

---

## Secure Coding Checklist

### OWASP ASVS Level 1-2 Compliance

**Level 1:**
- [x] Verify security for all inputs
- [x] Implement access controls
- [x] Output encoding and escaping
- [x] Cryptographic practices
- [x] Error handling and logging
- [x] Data protection
- [x] Communication security
- [x] Malicious file upload
- [x] API and web service security

**Level 2:**
- [x] Multi-factor authentication
- [x] Session management
- [x] Password strength
- [x] Multi-factor authentication
- [x] Input validation
- [x] Output encoding
- [x] Cryptographic storage
- [x] Memory protection
- [x] Logging and monitoring

---

## Input Validation

### Validate All Inputs

**Pydantic Schemas:**

```python
# schemas/form.py
from pydantic import BaseModel, Field, EmailStr, validator

class FormCreateSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., max_length=5000)
    slug: str = Field(..., min_length=1, max_length=100)
    status: str = Field(default="draft", regex="^(draft|published|archived)$")

    @validator('slug')
    def validate_slug(cls, v):
        if not v.isidentifier():
            raise ValueError("Slug must be a valid identifier")
        return v
```

### Validation in Routes:**

```python
# CORRECT - Use Pydantic schema
@bp.route("/forms", methods=["POST"])
def create_form():
    schema = FormCreateSchema(**request.get_json())
    form = form_service.create(schema)
    return success_response(data=form.to_dict(), status_code=201)

# WRONG - No validation
@bp.route("/forms", methods=["POST"])
def create_form():
    data = request.get_json()
    form = Form(**data)  # No validation!
    form.save()
    return success_response(data=form.to_dict())
```

### NoSQL Injection Prevention

```python
# CORRECT - Use NoSQLInjector
from utils.mongodb_query_helper import NoSQLInjector

query_field = request.json.get("field")
query_value = request.json.get("value")

safe_field = NoSQLInjector.sanitize_key(query_field)
safe_value = NoSQLInjector.escape_value(query_value)

results = MyModel.objects(__raw__={safe_field: safe_value})

# WRONG - Direct user input in queries
query_field = request.json.get("field")
query_value = request.json.get("value")

results = MyModel.objects(__raw__={query_field: query_value})  # VULNERABLE!
```

---

## Authentication Security

### JWT Token Security

**Secret Key Management:**

```python
# CORRECT - Use strong, random secret
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if len(JWT_SECRET_KEY) < 32:
    raise ValueError("JWT_SECRET_KEY must be at least 32 characters")

# WRONG - Hardcoded weak secret
JWT_SECRET_KEY = "secret"  # Easily guessable
```

**Token Expiration:**

```python
# CORRECT - Short expiration
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60  # 1 hour
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 30  # 30 days

# WRONG - Very long expiration
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 525600  # 1 year (too long)
```

**Token Validation:**

```python
# CORRECT - Validate token on every request
@bp.route("/protected", methods=["GET"])
@jwt_required()
def protected():
    user = get_current_user()
    return success_response(data=user.to_dict())

# WRONG - No token validation
@bp.route("/protected", methods=["GET"])
def protected():
    user_id = request.headers.get("X-User-ID")  # Easily spoofed
    user = User.objects(id=user_id).first()
    return success_response(data=user.to_dict())
```

### Password Security

**Strong Password Policy:**

```python
from utils.password_validator import password_validator

# CORRECT - Use strong password policy
result = password_validator.validate(password)

if not result.is_valid:
    return error_response(
        message="Password validation failed",
        errors=result.errors,
        status_code=400
    )

# WRONG - Weak password policy
if len(password) < 6:  # Too short
    return error_response(message="Password too short")
```

**Password Hashing:**

```python
# CORRECT - Use strong hashing algorithm
from werkzeug.security import generate_password_hash, check_password_hash

password_hash = generate_password_hash(password, method='pbkdf2:sha256')

# WRONG - Weak hashing algorithm
import hashlib
password_hash = hashlib.md5(password.encode()).hexdigest()  # Too weak
```

---

## Authorization Security

### Role-Based Access Control

```python
# CORRECT - Use role-based access control
from utils.security import require_roles

@bp.route("/admin/users", methods=["GET"])
@require_roles("admin", "superadmin")
def list_users():
    users = User.objects(is_deleted=False).all()
    return success_response(data=users)

# WRONG - No authorization
@bp.route("/admin/users", methods=["GET"])
def list_users():
    users = User.objects.all()  # Anyone can access!
    return success_response(data=users)
```

### Resource-Level Authorization

```python
# CORRECT - Check resource ownership
from routes.v1.form.helper import has_form_permission

@bp.route("/forms/<form_id>", methods=["GET"])
def get_form(form_id):
    user = get_current_user()
    form = Form.objects.get(id=form_id, organization_id=user.organization_id)

    if not has_form_permission(user, form, "view"):
        return error_response(message="Permission denied", status_code=403)

    return success_response(data=form.to_dict())

# WRONG - No ownership check
@bp.route("/forms/<form_id>", methods=["GET"])
def get_form(form_id):
    form = Form.objects.get(id=form_id)  # Anyone can access any form!
    return success_response(data=form.to_dict())
```

---

## Error Handling Security

### Don't Expose Internal Details

```python
# CORRECT - Generic error in production
if settings.APP_ENV == "production":
    message = "An error occurred while processing your request"
else:
    message = str(error)

# WRONG - Expose internal details
return jsonify({
    "error": "Database connection failed",
    "details": str(e)  # Reveals database connection string
})
```

### Log All Security Events

```python
# CORRECT - Log security events
audit_logger.warning(
    f"Authentication failed: {email} from {ip_address}"
)

# WRONG - No logging
# Can't detect brute force attacks
```

---

## Logging Security

### Sensitive Data Redaction

```python
# CORRECT - Redact sensitive data in logs
from utils.sensitive_data_redaction import safe_log_info

safe_log_info(
    app_logger,
    "User %s logged in from %s",
    email,
    ip_address
)
# Output: "User [REDACTED_EMAIL] logged in from [REDACTED_IP]"

# WRONG - Log sensitive data
app_logger.info(f"User {email} logged in from {ip_address}")
# Email and IP exposed in logs!
```

### Audit Logging

```python
# CORRECT - Audit all state changes
audit_logger.info(
    f"Form {form_id} published by user {user_id}"
)

# WRONG - No audit logging
# No record of who changed what
```

---

## Data Security

### Encrypt Sensitive Data

```python
# CORRECT - Encrypt sensitive fields at rest
from cryptography.fernet import Fernet

encryption_key = get_encryption_key()
cipher_suite = Fernet(encryption_key)

def encrypt_data(data: str) -> str:
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    return cipher_suite.decrypt(encrypted_data.encode()).decode()

# WRONG - Store sensitive data in plain text
# Anyone with database access can read sensitive data
```

### Sensitive Data in Memory

```python
# CORRECT - Clear sensitive data after use
password = request.json.get("password")

# Use password
user = authenticate_user(email, password)

# Clear password from memory
password = None  # Don't leave in memory longer than needed

# WRONG - Leave sensitive data in memory
password = request.json.get("password")
# ... processing ...
# Password remains in memory
```

---

## Session Security

### CSRF Protection

```python
# CORRECT - Use CSRF tokens
from utils.csrf_protection import csrf_protection

csrf_protection.init_csrf_protection(app)

@bp.route("/forms/<form_id>", methods=["POST"])
@csrf_protection.require_csrf_token
def update_form(form_id):
    # ... update form ...

# WRONG - No CSRF protection
# Vulnerable to CSRF attacks
```

### Session Timeout

```python
# CORRECT - Use short session timeout
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60  # 1 hour

# WRONG - Very long session timeout
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 525600  # 1 year
```

---

## File Upload Security

### Validate File Uploads

```python
# CORRECT - Use file_validator
from utils.file_validator import validate_upload

is_valid, error = validate_upload(file)
if not is_valid:
    return error_response(message=error, status_code=400)

# WRONG - No file validation
file.save("/uploads/" + file.filename)  # Allows malicious files
```

### Secure Filename Generation

```python
# CORRECT - Use secure filename
from utils.file_validator import generate_secure_filename

secure_filename = generate_secure_filename(file.filename)
filepath = os.path.join(upload_dir, secure_filename)

# WRONG - Use original filename
filepath = os.path.join(upload_dir, file.filename)  # Path traversal risk
```

---

## Rate Limiting

### Protect Sensitive Endpoints

```python
# CORRECT - Rate limit sensitive endpoints
from extensions import limiter

@bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    # ... login logic ...

# WRONG - No rate limiting
@bp.route("/login", methods=["POST"])
def login():
    # ... login logic ...
    # Vulnerable to brute force attacks
```

---

## Security Headers

### Implement Security Headers

```python
# CORRECT - Use Talisman for security headers
from extensions import talisman

talisman.init_app(
    app,
    content_security_policy=settings.CSP_POLICY,
    strict_transport_security=True,
    frame_options='DENY',
    x_content_type_options='nosniff',
    x_xss_protection='1; mode=block',
)

# WRONG - No security headers
# Vulnerable to XSS, clickjacking, etc.
```

---

## Code Review Checklist

### Security Review Checklist

**Input Validation:**
- [ ] All user input validated
- [ ] Input sanitization applied
- [ ] NoSQL injection prevention
- [ ] SQL injection prevention (if applicable)

**Authentication:**
- [ ] Strong password policy
- [ ] Secure password hashing
- [ ] Token expiration
- [ ] Token validation

**Authorization:**
- [ ] Role-based access control
- [ ] Resource-level authorization
- [ ] Tenant isolation enforced
- [ ] Cross-tenant access prevention

**Data Protection:**
- [ ] Sensitive data encrypted at rest
- [ ] Sensitive data encrypted in transit
- [ ] Sensitive data redacted in logs
- [ ] Secure file handling

**Error Handling:**
- [ ] Generic error messages in production
- [ ] No stack traces exposed
- [ ] Security events logged
- [ ] Audit logging

**Session Management:**
- [ ] CSRF protection
- [ ] Session timeout
- [ ] Secure cookie settings
- [ ] Session invalidation

**Rate Limiting:**
- [ ] Rate limiting on sensitive endpoints
- [ ] Brute force protection
- [ ] DDoS mitigation

**Dependencies:**
- [ ] Dependencies up to date
- [ ] No known vulnerabilities
- [ ] Third-party libraries reviewed

---

## Best Practices

### 1. Never Trust User Input

```python
# CORRECT - Always validate and sanitize
field_name = sanitize_key(request.json.get("field"))
field_value = escape_value(request.json.get("value"))

# WRONG - Trust user input
field_name = request.json.get("field")
field_value = request.json.get("value")

MyModel.objects(**{field_name: field_value})  # VULNERABLE!
```

### 2. Use Prepared Statements / Safe Queries

```python
# CORRECT - Use parameterized queries
safe_query = MyModel.objects(
    email=email,
    organization_id=organization_id
)

# WRONG - String concatenation
query_str = f"email='{email}'"
MyModel.objects(__raw__=query_str)  # VULNERABLE!
```

### 3. Implement Least Privilege

```python
# CORRECT - Grant minimum required access
user_role = determine_role(user)

# WRONG - Grant excessive access
user_role = "admin"  # More access than needed
```

### 4. Log Security Events

```python
# CORRECT - Log security events
audit_logger.warning(
    f"Failed login attempt: {email} from {ip_address}"
)

# WRONG - No security logging
# Can't detect attacks
```

### 5. Keep Dependencies Updated

```bash
# CORRECT - Regular updates
pip install --upgrade -r requirements.txt

# WRONG - Never update
# Known vulnerabilities in dependencies
```

---

## References

- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/)
- [OWASP Python Security](https://cheatsheetseries.owasp.org/cheatsheets/Injection_Prevention_Cheat_Sheet.html)
- [NIST SP 800-53](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)
- [MongoDB Security Best Practices](https://www.mongodb.com/docs/manual/administration/security-checklist/)
- [Flask Security Best Practices](https://flask.palletsprojects.com/Flask/1.0.x/security/)
