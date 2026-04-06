# API Versioning Strategy

**Purpose:** Documentation for API versioning strategy, deprecation policy, backward compatibility, and client migration guides.

**Scope:** Versioning strategy, supported version lifecycle, breaking changes, backward compatibility guarantees, and sunset procedures.

---

## Overview

The RIDP Form Platform API uses URL-based versioning (`/form/api/v1/`) to enable evolution while maintaining backward compatibility. This document outlines the versioning strategy, deprecation policy, and migration procedures.

**Current Version:** `v1`

---

## Versioning Strategy

### URL-Based Versioning

**Pattern:** `/form/api/v{major}/`

**Example:**
```
/form/api/v1/forms/
/form/api/v2/forms/  # Future version
```

### Version Format

**Semantic Versioning:**

```
MAJOR.MINOR.PATCH

MAJOR:    Breaking changes
MINOR:    New features, backward compatible
PATCH:    Bug fixes, backward compatible
```

**Current Version:** `1.0.0`

---

## Version Lifecycle

### Supported Versions

| Version | Status | Deprecation Date | Sunset Date |
|---------|--------|------------------|------------|
| v1 | Current | N/A | N/A |
| v2 | Future | N/A | N/A |

### Lifecycle Stages

**1. Development:**
- Feature development
- Breaking changes allowed
- Not publicly documented

**2. Stable:**
- Released to production
- Backward compatible changes only
- Fully supported

**3. Deprecated:**
- No new features
- Bug fixes only
- Clients should migrate

**4. Sunset:**
- No longer supported
- End of life

---

## Deprecation Policy

### Deprecation Timeline

**Minimum Notice Period:** 6 months

**Timeline:**
```
T0:   New version released (v2)
T0+1m: Old version marked deprecated (v1)
T0+6m: Old version sunset (v1)
```

### Deprecation Process

**1. Announce New Version:**
```
API Deprecation Notice

Version v1 of the RIDP Form Platform API will be deprecated on 2026-10-01.
Version v2 is now available with improved features and performance.

Migration Guide: https://docs.example.com/api/migration/v1-to-v2

If you have questions, contact api-support@example.com.
```

**2. Update Documentation:**
- Mark v1 as deprecated in docs
- Add deprecation warning to responses
- Provide migration guide

**3. Monitor Usage:**
- Track v1 usage metrics
- Identify heavy users
- Provide migration assistance

**4. Sunset v1:**
- Disable v1 endpoints
- Return 410 Gone responses

---

## Breaking Changes

### What Constitutes a Breaking Change

**Examples of Breaking Changes:**
- Removing an endpoint
- Removing a required request parameter
- Removing a response field
- Changing field name or type
- Changing resource structure
- Changing authentication requirements
- Changing error codes

**Non-Breaking Changes:**
- Adding new endpoints
- Adding optional request parameters
- Adding response fields
- Changing field order
- Changing error messages
- Performance improvements

### Breaking Change Checklist

Before making a breaking change:

- [ ] Document breaking change
- [ ] Create migration guide
- [ ] Update Swagger documentation
- [ ] Add deprecation warning (if not removing immediately)
- [ ] Notify API consumers
- [ ] Update integration tests
- [ ] Test migration path

---

## Backward Compatibility

### Compatibility Guarantees

**Within Major Version:**
- Backward compatible for MINOR and PATCH updates
- No breaking changes in MINOR or PATCH updates

**Between Major Versions:**
- Breaking changes allowed
- Migration guide provided
- Parallel support for 6 months

### Maintaining Compatibility

**Field Addition:**
```python
# CORRECT - Add new field (backward compatible)
class FormSchema(BaseModel):
    name: str
    description: Optional[str] = None  # New field

# WRONG - Remove field (breaking change)
class FormSchema(BaseModel):
    name: str
    # description field removed
```

**Endpoint Addition:**
```python
# CORRECT - Add new endpoint (backward compatible)
@bp.route("/forms/<form_id>/archive", methods=["POST"])
def archive_form(form_id):
    # ... implementation ...
    pass

# WRONG - Remove endpoint (breaking change)
# @bp.route("/forms/<form_id>/delete", methods=["DELETE"])
# def delete_form(form_id):
#     # ... removed ...
#     pass
```

---

## Version Negotiation

### Accept Header

**Client specifies version:**

```http
GET /form/api/v1/forms HTTP/1.1
Host: api.example.com
Accept: application/vnd.ridp-form.v1+json
```

### Version Header

**Alternative:**

```http
GET /form/api/forms HTTP/1.1
Host: api.example.com
API-Version: v1
```

### Fallback Strategy

**Default Version:** Latest stable version

```python
# utils/versioning.py
def get_requested_version():
    """Get requested API version."""
    # Check Accept header
    accept = request.headers.get("Accept", "")

    if "v1" in accept:
        return "v1"
    elif "v2" in accept:
        return "v2"

    # Check API-Version header
    version_header = request.headers.get("API-Version")
    if version_header:
        return version_header

    # Check URL path
    if "/v2/" in request.path:
        return "v2"

    # Default to v1
    return "v1"
```

---

## Migration Guide Template

### v1 to v2 Migration

**Breaking Changes:**

| Change | v1 | v2 | Migration Action |
|--------|-----|-----|----------------|
| Field rename | `form_name` | `name` | Update field name |
| Field type change | String | Integer | Convert to integer |
| Required field | Optional | Required | Provide value |
| Endpoint removal | `/forms/` | `/api/v2/forms/` | Update URL |

**Code Example:**

```python
# v1 Client Code
response = requests.get("https://api.example.com/form/api/v1/forms")
form = response.json()
name = form["form_name"]  # v1 field name

# v2 Client Code
response = requests.get("https://api.example.com/form/api/v2/forms")
form = response.json()
name = form["name"]  # v2 field name
```

**Automated Migration Script:**

```python
# scripts/migrate_v1_to_v2.py
def migrate_v1_client_code(code: str) -> str:
    """Migrate v1 client code to v2."""
    # Replace field names
    code = code.replace("form_name", "name")
    code = code.replace("form_description", "description")

    # Replace URLs
    code = code.replace("/form/api/v1/", "/form/api/v2/")

    return code
```

---

## Sunset Procedures

### Sunset Endpoint

**410 Gone Response:**

```python
# routes/v1/sunset_route.py
@bp.route("/v1/forms", methods=["GET"])
def sunset_v1():
    """Handle requests to sunset v1 API."""
    response = jsonify({
        "error": "Version v1 is sunset",
        "message": "This API version is no longer supported. Please upgrade to v2.",
        "documentation": "https://docs.example.com/api/v2",
        "sunset_date": "2027-04-01"
    })
    response.status_code = 410  # Gone
    return response
```

### Monitoring Sunset

**Track Sunset Version Usage:**

```python
# Monitor usage of sunset versions
def monitor_sunset_usage():
    """Monitor usage of sunset API versions."""
    sunset_versions = ["v1"]

    for version in sunset_versions:
        usage_count = get_version_usage_count(version)

        if usage_count > 0:
            send_alert(
                f"Sunset version {version} still has {usage_count} requests/hour",
                severity="warning"
            )

            # Notify affected users
            notify_affected_users(version)
```

---

## Configuration

### Version Configuration

```python
# config/settings.py
class Settings(BaseSettings):
    # API versioning
    API_CURRENT_VERSION: str = "v1"
    API_SUPPORTED_VERSIONS: list[str] = ["v1"]
    API_DEPRECATED_VERSIONS: list[str] = []
    API_SUNSET_VERSIONS: list[str] = []

    # Deprecation timeline
    API_DEPRECATION_NOTICE_MONTHS: int = 6
```

### Route Configuration

```python
# routes/v1/__init__.py
form_bp = Blueprint('form', __name__, url_prefix='/form/api/v1')

# routes/v2/__init__.py (future)
form_v2_bp = Blueprint('form_v2', __name__, url_prefix='/form/api/v2')
```

---

## Best Practices

### 1. Plan Breaking Changes Carefully

```python
# CORRECT - Plan ahead
# Announce 6 months before breaking change
# Provide migration guide
# Support both versions in parallel

# WRONG - Unplanned breaking change
# Break client code without warning
```

### 2. Document All Changes

```python
# CORRECT - Comprehensive documentation
# Update Swagger docs
# Provide examples
# Explain breaking changes

# WRONG - Minimal documentation
# Assume clients will figure it out
```

### 3. Monitor Version Usage

```python
# CORRECT - Track usage
version_metrics = {
    "v1": 1000,  # requests/hour
    "v2": 5000   # requests/hour
}

# WRONG - No monitoring
# Don't know which versions are used
```

### 4. Provide Migration Tools

```python
# CORRECT - Help clients migrate
# Migration guide
# Automated scripts
# Support contact

# WRONG - Clients on their own
# Figure it out yourself
```

### 5. Test Migration Paths

```python
# CORRECT - Test migration
# Create v1 and v2 test environments
# Test v1 client against v2 API
# Verify migration script

# WRONG - Untested migration
# Hope it works
```

---

## References

- [API Versioning Best Practices](https://restfulapi.net/versioning/)
- [Semantic Versioning](https://semver.org/)
- [HTTP 410 Gone](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/410)
- [Microsoft API Versioning](https://docs.microsoft.com/en-us/azure/architecture/best-practices/api-design/api-versioning)
