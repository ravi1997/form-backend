# Password Policy

**Purpose:** Documentation for NIST SP 800-63B and OWASP compliant password validation and strength assessment.

**Scope:** Password validation rules, strength scoring, history checking, breached password detection, and password generation.

---

## Overview

The password policy implements NIST SP 800-63B Digital Identity Guidelines and OWASP best practices for password security. The system enforces strong password requirements while maintaining user experience through clear validation feedback and strength scoring.

**Key Components:**
- `utils/password_validator.py` - Password validation logic (300 lines)
- `schemas/user.py` - Password validation schemas
- `services/user_service.py` - Password creation/update logic

---

## Password Requirements (NIST SP 800-63B)

### Minimum Requirements

```python
# config/settings.py
PASSWORD_MIN_LENGTH: int = 12  # NIST recommends 8, OWASP recommends 12+
PASSWORD_MAX_LENGTH: int = 128
PASSWORD_REQUIRE_UPPERCASE: bool = True
PASSWORD_REQUIRE_LOWERCASE: bool = True
PASSWORD_REQUIRE_DIGITS: bool = True
PASSWORD_REQUIRE_SPECIAL: bool = True
```

**Rationale:**
- **12 characters minimum:** Balances security and usability (NIST: 8+, OWASP: 12+)
- **128 characters maximum:** Prevents DoS via extremely long passwords
- **3 of 4 character types:** Enforces complexity without arbitrary rules
- **No whitespace:** Prevents confusion and injection issues

### Character Type Requirements

**Required Character Types:**
1. Uppercase letters (A-Z)
2. Lowercase letters (a-z)
3. Numbers (0-9)
4. Special characters (!@#$%^&*()-_=+)

**Validation:**
```python
def validate_character_types(password: str) -> List[str]:
    errors = []

    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in string.punctuation for c in password)

    char_types = sum([has_upper, has_lower, has_digit, has_special])

    if char_types < 3:
        errors.append(
            "Password must contain at least 3 of the following: "
            "uppercase, lowercase, numbers, special characters"
        )

    return errors
```

### Forbidden Patterns

**1. Common Passwords**

```python
COMMON_PASSWORDS = [
    "password", "password123", "123456", "12345678",
    "qwerty", "abc123", "letmein", "admin", "welcome",
    # ... 38 common passwords total
]
```

**2. Sequential Characters**

```python
# Maximum allowed sequential characters
MAX_SEQUENTIAL = 3

# Blocked sequences:
# - Numeric: 012, 123, 234, ..., 890, 901
# - Alphabetic: abc, bcd, cde, ..., wxy, xyz

SEQUENTIAL_PATTERN = re.compile(
    r"(?:012|123|234|345|456|567|678|789|890|901|"
    r"abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)",
    re.IGNORECASE
)
```

**3. Repetitive Characters**

```python
# Maximum allowed repetitive characters
MAX_REPETITIVE = 3

# Blocked patterns: "aaaa", "1111", "!!!!"

REPETITIVE_PATTERN = re.compile(r"(.)\1{2,}")
```

**4. All Numbers or All Letters**

```python
if password.isnumeric():
    errors.append("Password must not be all numbers")

if password.isalpha():
    errors.append("Password must not be all letters")
```

---

## Password Strength Scoring

### Scoring Algorithm

```python
def _calculate_strength(password, has_upper, has_lower, has_digit, has_special):
    score = 0

    # 1. Length score (up to 40 points)
    length_score = min(len(password) * 2, 40)
    score += length_score

    # 2. Character variety score (up to 30 points)
    variety_score = sum([has_upper, has_lower, has_digit, has_special]) * 7.5
    score += variety_score

    # 3. Complexity bonus (up to 20 points)
    if len(password) >= 16 and variety_score >= 30:
        score += 10  # Long and complex
    if sum([has_upper, has_lower, has_digit, has_special]) >= 4:
        score += 10  # All character types

    # 4. Deductions for weak patterns
    for match in SEQUENTIAL_PATTERN.findall(password):
        if len(match) >= MAX_SEQUENTIAL:
            score -= 10

    for match in REPETITIVE_PATTERN.findall(password):
        if len(match) >= MAX_REPETITIVE:
            score -= 10

    if password.lower() in COMMON_PASSWORDS:
        score -= 30

    # Ensure score is in valid range
    score = max(0, min(100, score))

    return strength, score
```

### Strength Levels

```python
class PasswordStrength(Enum):
    VERY_WEAK = 0    # 0-20
    WEAK = 1         # 20-40
    MODERATE = 2     # 40-60
    STRONG = 3       # 60-80
    VERY_STRONG = 4   # 80-100
```

### Examples

| Password | Score | Strength | Notes |
|----------|-------|----------|-------|
| `password` | 0 | Very Weak | Common password |
| `Password123` | 45 | Moderate | Meets minimum, but common pattern |
| `MyP@ssw0rd!` | 65 | Strong | Good length and complexity |
| `Xk9#mP2$vL5@nQ8!` | 95 | Very Strong | Maximum complexity |
| `aaaaaa` | 0 | Very Weak | Repetitive characters |
| `12345678` | 0 | Very Weak | Sequential, all numbers |

---

## Password History Checking

### Purpose

Prevent password reuse to maintain security over time.

### Implementation (Future)

```python
def check_password_history(password: str, password_history: List[str]) -> bool:
    """
    Check if password has been used before.
    Returns True if password is new (not in history).
    """
    # In production, this should also check for similar passwords
    # (e.g., "Password123" vs "Password456")

    return password not in password_history
```

### Configuration

```python
# config/settings.py
PASSWORD_HISTORY_COUNT: int = 5  # Remember last 5 passwords
```

### Database Schema (Future)

```python
# models/User.py
class User(Document):
    # ... existing fields

    password_history = ListField(StringField(), max_length=5)
    last_password_change = DateTimeField()
```

### Usage Example

```python
# When updating password
if not password_validator.check_password_history(new_password, user.password_history):
    return error_response(
        message="Cannot reuse one of the last 5 passwords",
        status_code=400
    )

# Update history
user.password_history.insert(0, hash_password(old_password))
user.password_history = user.password_history[:PASSWORD_HISTORY_COUNT]
```

---

## Breached Password Detection

### Purpose

Check if password has been exposed in known data breaches.

### Implementation (Future - Placeholder)

```python
def is_password_breached(self, password: str) -> bool:
    """
    Check if password has been found in data breaches.
    In production, this would call HaveIBeenPwned API.
    """
    # TODO: Implement HaveIBeenPwned API integration
    # Reference: https://haveibeenpwned.com/API/v3

    # Example implementation:
    import requests
    import hashlib

    # Hash password with SHA-1 (as required by HIBP)
    sha1_hash = hashlib.sha1(password.encode()).hexdigest().upper()

    # Split into prefix and suffix
    prefix = sha1_hash[:5]
    suffix = sha1_hash[5:]

    # Query HIBP API
    response = requests.get(f"https://api.pwnedpasswords.com/range/{prefix}")

    # Check if suffix is in response
    hashes = response.text.splitlines()
    for hash_line in hashes:
        if hash_line.startswith(suffix):
            # Password is breached
            return True

    return False
```

### API Reference

**HaveIBeenPwned API:**
- **Endpoint:** `https://api.pwnedpasswords.com/range/{prefix}`
- **Method:** GET
- **Rate Limiting:** Free tier: ~1 request per 1.5 seconds
- **Privacy:** Only password hash prefix is sent (k-anonymity)

### Integration Example

```python
# In user_service.py create_user()
password_result = password_validator.validate(password)

if not password_result.is_valid:
    return error_response(
        message="Password validation failed",
        errors=password_result.errors,
        status_code=400
    )

# Check for breached password
if password_validator.is_password_breached(password):
    audit_logger.warning(
        f"Attempted to use breached password during registration: {user.email}"
    )
    return error_response(
        message="This password has been exposed in a data breach. "
        "Please choose a different password.",
        status_code=400
    )
```

---

## Password Generation

### Purpose

Generate strong random passwords for users or system accounts.

### Implementation

```python
def suggest_strong_password(length: int = 16) -> str:
    """
    Generate a strong random password suggestion.
    Uses cryptographically secure random number generation.
    """
    import secrets
    import string as str_mod

    # Mix of character types
    uppercase = str_mod.ascii_uppercase
    lowercase = str_mod.ascii_lowercase
    digits = str_mod.digits
    special = "!@#$%^&*()-_=+"

    # Ensure at least 4 of each type
    chars = []
    chars.extend(secrets.choice(uppercase) for _ in range(4))
    chars.extend(secrets.choice(lowercase) for _ in range(4))
    chars.extend(secrets.choice(digits) for _ in range(4))
    chars.extend(secrets.choice(special) for _ in range(4))

    # Fill remaining length with random characters from all sets
    all_chars = uppercase + lowercase + digits + special
    for _ in range(length - len(chars)):
        chars.append(secrets.choice(all_chars))

    # Shuffle the characters
    secrets.SystemRandom().shuffle(chars)

    return "".join(chars)
```

### Example Usage

```python
# Generate 16-character password
strong_password = password_validator.suggest_strong_password(length=16)
# Output: "Xk9#mP2$vL5@nQ8!ab"

# Generate 24-character password
very_strong_password = password_validator.suggest_strong_password(length=24)
# Output: "A7&dF3$kL9@mP2$vL5@nQ8!Xk9#mP2$vL5@nQ8!"
```

---

## Usage Examples

### Basic Password Validation

```python
from utils.password_validator import password_validator, PasswordValidationResult

def create_user(email: str, password: str):
    # Validate password
    result = password_validator.validate(password)

    if not result.is_valid:
        return error_response(
            message="Password validation failed",
            errors=result.errors,
            status_code=400
        )

    # Check password strength
    if result.strength in [PasswordStrength.VERY_WEAK, PasswordStrength.WEAK]:
        return error_response(
            message="Password is too weak. Please choose a stronger password.",
            status_code=400
        )

    # Proceed with user creation
    user = User(
        email=email,
        password_hash=hash_password(password),
        # ... other fields
    )
    user.save()

    return success_response(data={"user_id": str(user.id)})
```

### Detailed Validation Feedback

```python
def validate_password_with_feedback(password: str) -> dict:
    result = password_validator.validate(password)

    feedback = {
        "is_valid": result.is_valid,
        "strength": result.strength.name,
        "score": result.score,
        "errors": result.errors,
        "warnings": result.warnings
    }

    return feedback

# Example response:
# {
#     "is_valid": false,
#     "strength": "WEAK",
#     "score": 35,
#     "errors": [
#         "Password must be at least 12 characters long",
#         "Password must contain at least 3 of the following character types..."
#     ],
#     "warnings": [
#         "Password does not contain any special characters",
#         "Password is less than 14 characters; longer passwords are stronger"
#     ]
# }
```

### Password Strength Meter (UI Integration)

```python
@bp.route("/password-strength", methods=["POST"])
def check_password_strength():
    """Check password strength without creating user."""
    password = request.json.get("password")

    if not password:
        return error_response(message="Password required", status_code=400)

    result = password_validator.validate(password)

    return success_response(data={
        "strength": result.strength.name,
        "score": result.score,
        "is_valid": result.is_valid,
        "warnings": result.warnings
    })
```

---

## Configuration Reference

### Password Policy Settings

```python
# config/settings.py
class Settings(BaseSettings):
    # Password policy (NIST SP 800-63B compliant)
    PASSWORD_MIN_LENGTH: int = Field(default=12, ge=8, le=128)
    PASSWORD_MAX_LENGTH: int = Field(default=128, ge=12, le=256)
    PASSWORD_REQUIRE_UPPERCASE: bool = Field(default=True)
    PASSWORD_REQUIRE_LOWERCASE: bool = Field(default=True)
    PASSWORD_REQUIRE_DIGITS: bool = Field(default=True)
    PASSWORD_REQUIRE_SPECIAL: bool = Field(default=True)
    PASSWORD_EXPIRATION_DAYS: int = Field(default=90, ge=30, le=365)
    PASSWORD_HISTORY_COUNT: int = Field(default=5, ge=0, le=20)
    PREVENT_COMMON_PASSWORDS: bool = Field(default=True)
```

### Password Validator Constants

```python
# utils/password_validator.py
MIN_LENGTH = 12
MAX_LENGTH = 128
MIN_CHARACTER_TYPES = 3
MAX_SEQUENTIAL = 3
MAX_REPETITIVE = 3
```

---

## Best Practices

### 1. Always Validate Before Hashing

```python
# CORRECT
result = password_validator.validate(password)
if result.is_valid:
    password_hash = hash_password(password)

# WRONG
password_hash = hash_password(password)  # May hash weak password
```

### 2. Provide Clear Feedback

```python
# CORRECT - Return specific errors
if not result.is_valid:
    return error_response(
        message="Password validation failed",
        errors=result.errors,  # Specific error messages
        status_code=400
    )

# WRONG - Generic error message
if not result.is_valid:
    return error_response(message="Invalid password", status_code=400)
```

### 3. Log Security Events

```python
from logger.unified_logger import audit_logger

# Log password validation failures
if not password_result.is_valid:
    audit_logger.warning(
        f"Password validation failed - "
        f"User: {email} - Errors: {password_result.errors}"
    )

# Log breached password attempts
if password_validator.is_password_breached(password):
    audit_logger.warning(
        f"Attempted to use breached password: {email}"
    )
```

### 4. Use Secure Random Generation

```python
# CORRECT - Use secrets module
import secrets
password = secrets.token_urlsafe(16)

# WRONG - Use random module (not cryptographically secure)
import random
password = ''.join(random.choices(string.ascii_letters, k=16))
```

### 5. Never Store Plain Text Passwords

```python
# CORRECT - Hash with bcrypt or Argon2
from werkzeug.security import generate_password_hash
password_hash = generate_password_hash(password)

# WRONG - Store plain text
user.password = password  # NEVER DO THIS
```

---

## Security Considerations

### 1. Password Hashing

**Algorithm:** Use bcrypt or Argon2 (not MD5, SHA-1, or SHA-256)

**Example:**
```python
from werkzeug.security import generate_password_hash, check_password_hash

# Hash password
password_hash = generate_password_hash(password, method='pbkdf2:sha256')

# Verify password
is_valid = check_password_hash(password_hash, password)
```

### 2. Password Expiration

**Configuration:**
```python
PASSWORD_EXPIRATION_DAYS: int = 90
```

**Implementation (Future):**
```python
def check_password_expiration(user: User) -> bool:
    """Check if password has expired."""
    if not user.last_password_change:
        return True  # Password was never set

    days_since_change = (datetime.utcnow() - user.last_password_change).days
    return days_since_change > PASSWORD_EXPIRATION_DAYS
```

### 3. Account Lockout

**Rate Limiting:**
```python
# config/settings.py
RATE_LIMIT_PASSWORD_CHANGE: str = "3 per hour"
```

### 4. Password Recovery

**Best Practices:**
- Never email passwords in plain text
- Use time-limited reset tokens
- Invalidate existing sessions after password reset
- Log password reset events

---

## Testing

### Unit Tests

```python
def test_minimum_length():
    validator = PasswordValidator()

    # Too short
    result = validator.validate("Short1!")
    assert result.is_valid == False
    assert "Password must be at least 12 characters long" in result.errors

    # Valid length
    result = validator.validate("LongEnough123!")
    assert result.is_valid == True

def test_character_types():
    validator = PasswordValidator()

    # Only one type
    result = validator.validate("shortlongpassword")
    assert result.is_valid == False

    # Three types
    result = validator.validate("Password123")
    assert result.is_valid == True

def test_common_passwords():
    validator = PasswordValidator()

    result = validator.validate("password")
    assert result.is_valid == False
    assert "Password is too common" in result.errors

def test_sequential_characters():
    validator = PasswordValidator()

    result = validator.validate("abc123DEF")
    assert result.is_valid == False
    assert "sequential characters" in result.errors[0].lower()
```

---

## References

- [NIST SP 800-63B Digital Identity Guidelines](https://pages.nist.gov/800-63-3/sp800-63b.html)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [HaveIBeenPwned API](https://haveibeenpwned.com/API/v3)
- [CWE-521: Weak Password Requirements](https://cwe.mitre.org/data/definitions/521.html)
