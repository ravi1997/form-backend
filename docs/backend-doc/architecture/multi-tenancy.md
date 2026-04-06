# Multi-Tenancy Patterns

**Purpose:** Documentation for multi-tenancy architecture, tenant isolation, and data segregation patterns.

**Scope:** Multi-tenancy patterns, organization_id scoping, TenantIsolatedSoftDeleteQuerySet, tenant isolation enforcement, and cross-tenant data prevention.

---

## Overview

The RIDP Form Platform implements multi-tenancy to support multiple organizations while ensuring complete data isolation. Each organization's data is segregated using `organization_id`, with enforced scoping at the application and database levels.

**Target Audience:** System architects, backend developers, database administrators

---

## Multi-Tenancy Strategy

### Tenant Isolation Model

**Model:** Database-level isolation using `organization_id`

**Architecture:**
```
┌─────────────────────────────────────────────────┐
│               Application Layer               │
│  ┌──────────────┐  ┌──────────────┐         │
│  │  Tenant A    │  │  Tenant B    │  ...     │
│  │ (Org 1)      │  │ (Org 2)      │         │
│  └──────────────┘  └──────────────┘         │
│         │                 │                │
│         └─────────────────┘                │
│                   │                        │
│                   ▼                        │
│         ┌──────────────────┐               │
│         │   Database       │               │
│         │  MongoDB        │               │
│         │  (Shared DB)    │               │
│         └──────────────────┘               │
│                                           │
│  Data Segregated by organization_id       │
└───────────────────────────────────────────┘
```

### Tenant Identification

**JWT Token:**

```python
# JWT Payload
{
    "sub": "user_id",
    "email": "user@example.com",
    "organization_id": "507f1f77bcf86cd799439011",
    "role": "admin"
}
```

**Middleware Extraction:**

```python
# middleware/tenant_db.py
from flask import g, request
from flask_jwt_extended import get_jwt
from mongoengine import connection

def set_tenant_context():
    """Extract organization_id from JWT and set in g."""
    try:
        jwt_data = get_jwt()
        organization_id = jwt_data.get("organization_id")

        if not organization_id:
            raise ValueError("organization_id not found in JWT")

        # Set in Flask g object
        g.organization_id = organization_id

        # Set MongoDB tenant context
        db = connection.get_db()
        db.organization_id = organization_id

    except Exception as e:
        error_logger.error(
            f"Failed to set tenant context: {str(e)}",
            exc_info=True
        )
        raise
```

---

## TenantIsolatedSoftDeleteQuerySet

### QuerySet Class

**Implementation:**

```python
# models/base.py
from mongoengine import QuerySet

class TenantIsolatedSoftDeleteQuerySet(QuerySet):
    """
    QuerySet that automatically filters by organization_id and is_deleted.
    Provides tenant isolation and soft delete functionality.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Auto-apply organization_id filter if available
        if hasattr(g, 'organization_id') and g.organization_id:
            self = self.filter(organization_id=g.organization_id)

        # Auto-apply is_deleted filter
        self = self.filter(is_deleted=False)

    def get(self, *args, **kwargs):
        """
        Override get to include organization_id filter.

        WARNING: get() bypasses the queryset class, so
        organization_id must be added explicitly.
        """
        # Get the query dict
        query = self._query

        # Ensure organization_id is present
        if hasattr(g, 'organization_id') and g.organization_id:
            if 'organization_id' not in query:
                query['organization_id'] = g.organization_id

        # Ensure is_deleted is present
        if 'is_deleted' not in query:
            query['is_deleted'] = False

        # Call parent get
        return super().get(*args, **kwargs)
```

### Usage

**In Model Definitions:**

```python
# models/Form.py
from models.base import TenantIsolatedSoftDeleteQuerySet

class Form(Document):
    meta = {
        "collection": "forms",
        "queryset_class": TenantIsolatedSoftDeleteQuerySet,
    }

    organization_id = StringField(required=True)
    name = StringField(required=True)
    status = StringField(default="draft")
    is_deleted = BooleanField(default=False)
```

**In Queries:**

```python
# Standard query - auto-filters organization_id and is_deleted
forms = Form.objects(name="My Form")  # Scoped to current user's org

# get() - must include organization_id explicitly
form = Form.objects.get(
    id=form_id,
    organization_id=g.organization_id  # Required for get()
)
```

---

## Tenant Isolation Enforcement

### Service Layer Enforcement

**BaseService:**

```python
# services/base.py
class BaseService:
    """Base service with tenant isolation."""

    def __init__(self):
        self.organization_id = g.organization_id if hasattr(g, 'organization_id') else None

    def list(self, model_class, **filters):
        """List with tenant isolation."""
        # Add organization_id filter
        filters['organization_id'] = self.organization_id
        filters['is_deleted'] = False

        return model_class.objects(**filters)

    def get(self, model_class, id):
        """Get with tenant isolation."""
        return model_class.objects.get(
            id=id,
            organization_id=self.organization_id,
            is_deleted=False
        )

    def create(self, schema):
        """Create with tenant isolation."""
        model = self._from_schema(schema)
        model.organization_id = self.organization_id
        model.save()
        return model
```

### Route Layer Enforcement

**Get Current User:**

```python
# utils/security_helpers.py
from flask_jwt_extended import get_jwt
from models.base import g

def get_current_user():
    """Retrieve current authenticated user from JWT identity."""
    user_id = get_jwt_identity()
    if not user_id:
        return None

    # Get JWT data for organization_id
    jwt_data = get_jwt()
    organization_id = jwt_data.get("organization_id")

    # Query user with organization_id for proper tenant isolation
    user = User.objects(
        id=user_id,
        organization_id=organization_id
    ).first()

    return user
```

**Permission Check:**

```python
# routes/v1/form/helper.py
def has_form_permission(user, form, permission: str):
    """Check if user has permission on form."""
    # Verify form belongs to user's organization
    if form.organization_id != user.organization_id:
        audit_logger.warning(
            f"Cross-tenant access attempt: user={user.email}, "
            f"user_org={user.organization_id}, "
            f"form_org={form.organization_id}"
        )
        return False

    # Check permission
    # ... permission logic ...

    return True
```

---

## Cross-Tenant Data Prevention

### Validation Middleware

**Prevent Cross-Tenant Access:**

```python
# middleware/tenant_validation.py
def validate_tenant_access():
    """Validate that request doesn't access cross-tenant data."""
    # Get current user's organization_id
    jwt_data = get_jwt()
    user_org_id = jwt_data.get("organization_id")

    # Validate all query parameters
    for param in request.args:
        if param == "organization_id":
            requested_org_id = request.args.get(param)

            if requested_org_id != user_org_id:
                audit_logger.critical(
                    f"Cross-tenant access attempt: "
                    f"user_org={user_org_id}, "
                    f"requested_org={requested_org_id}"
                )
                abort(403, description="Cross-tenant access not allowed")

    # Validate request body
    if request.is_json:
        body = request.get_json()

        if "organization_id" in body:
            requested_org_id = body.get("organization_id")

            if requested_org_id != user_org_id:
                audit_logger.critical(
                    f"Cross-tenant modification attempt: "
                    f"user_org={user_org_id}, "
                    f"requested_org={requested_org_id}"
                )
                abort(403, description="Cross-tenant modification not allowed")
```

### Superadmin Exception

**Superadmin Bypass:**

```python
# utils/security.py
def is_superadmin(user):
    """Check if user is superadmin."""
    return user.role == "superadmin"

def get_accessible_organizations(user):
    """Get organizations user can access."""
    if is_superadmin(user):
        # Superadmin can access all organizations
        return Organization.objects(is_deleted=False)

    # Regular users can only access their own organization
    return [Organization.objects.get(id=user.organization_id)]
```

---

## Data Segregation Patterns

### Organization-Level Segregation

**Collection Structure:**

```
forms collection:
{
  "_id": ObjectId(...),
  "organization_id": "org_123",
  "name": "My Form",
  "status": "published",
  "is_deleted": false
}

users collection:
{
  "_id": ObjectId(...),
  "organization_id": "org_123",
  "email": "user@example.com",
  "role": "admin"
}

responses collection:
{
  "_id": ObjectId(...),
  "organization_id": "org_123",
  "form_id": "form_456",
  "submitted_by": "user_789",
  "data": {...},
  "is_deleted": false
}
```

### Indexes

**Tenant-Aware Indexes:**

```python
# models/Form.py
class Form(Document):
    meta = {
        "indexes": [
            # Compound index for tenant queries
            {
                "fields": [("organization_id", 1), ("created_at", -1)]
            },
            # Unique index per tenant
            {
                "fields": [("organization_id", 1), ("slug", 1)],
                "unique": True,
                "sparse": True
            }
        ]
    }
```

---

## Tenant Management

### Organization Creation

```python
# routes/v1/organization_route.py
@bp.route("/organizations", methods=["POST"])
@require_roles("superadmin")
def create_organization():
    """Create new organization (superadmin only)."""
    schema = OrganizationCreateSchema(**request.get_json())

    # Create organization
    org = Organization(
        name=schema.name,
        slug=schema.slug,
        plan=schema.plan,
        is_deleted=False
    )
    org.save()

    # Create admin user
    admin_user = User(
        email=schema.admin_email,
        password_hash=generate_password_hash(schema.admin_password),
        organization_id=str(org.id),
        role="admin",
        is_deleted=False
    )
    admin_user.save()

    audit_logger.info(
        f"Organization created: {org.name} (id={org.id}) "
        f"by superadmin {get_current_user().email}"
    )

    return success_response(
        data=org.to_dict(),
        status_code=201
    )
```

### Organization Deletion

```python
@bp.route("/organizations/<org_id>", methods=["DELETE"])
@require_roles("superadmin")
def delete_organization(org_id):
    """Delete organization (superadmin only)."""
    org = Organization.objects.get(id=org_id)

    # Soft delete organization
    org.is_deleted = True
    org.deleted_at = datetime.utcnow()
    org.save()

    # Soft delete all organization data
    User.objects(organization_id=org_id).update(set__is_deleted=True)
    Form.objects(organization_id=org_id).update(set__is_deleted=True)
    FormResponse.objects(organization_id=org_id).update(set__is_deleted=True)

    audit_logger.info(
        f"Organization deleted: {org.name} (id={org_id}) "
        f"by superadmin {get_current_user().email}"
    )

    return success_response(message="Organization deleted")
```

---

## Performance Considerations

### Database Indexing

**Optimal Indexes:**

```python
# All tenant-scoped queries should have compound index on (organization_id, field)
meta = {
    "indexes": [
        {"fields": [("organization_id", 1), ("created_at", -1)]},
        {"fields": [("organization_id", 1), ("status", 1)]},
        {"fields": [("organization_id", 1), ("is_deleted", 1)]},
    ]
}
```

### Query Optimization

**Use Indexes:**

```python
# CORRECT - Uses index
forms = Form.objects(
    organization_id=g.organization_id,
    status="published"
).all()

# WRONG - May not use index effectively
forms = Form.objects(status="published").all()  # Missing organization_id
```

---

## Security Considerations

### Tenant Enumeration Prevention

**Prevent Organization Discovery:**

```python
@bp.route("/organizations", methods=["GET"])
@require_roles("superadmin")
def list_organizations():
    """List organizations (superadmin only)."""
    # Only superadmin can see all organizations
    # Regular users can only see their own organization via profile

    organizations = Organization.objects(is_deleted=False).all()

    return success_response(data=[org.to_dict() for org in organizations])
```

### Cross-Tenant Resource Access Prevention

**Resource Ownership Validation:**

```python
@bp.route("/forms/<form_id>", methods=["GET"])
def get_form(form_id):
    """Get form with tenant isolation."""
    user = get_current_user()

    # Verify form belongs to user's organization
    form = Form.objects(
        id=form_id,
        organization_id=user.organization_id,
        is_deleted=False
    ).first()

    if not form:
        return error_response(
            message="Form not found",
            status_code=404
        )

    return success_response(data=form.to_dict())
```

---

## Best Practices

### 1. Always Include organization_id

```python
# CORRECT - Include organization_id
form = Form.objects(
    id=form_id,
    organization_id=g.organization_id,
    is_deleted=False
).first()

# WRONG - Missing organization_id
form = Form.objects(id=form_id).first()
```

### 2. Use TenantIsolatedSoftDeleteQuerySet

```python
# CORRECT - Use tenant-isolated queryset
class Form(Document):
    meta = {
        "queryset_class": TenantIsolatedSoftDeleteQuerySet,
    }

# WRONG - Use default queryset
class Form(Document):
    pass  # No tenant isolation
```

### 3. Validate Tenant Access

```python
# CORRECT - Validate tenant ownership
if form.organization_id != user.organization_id:
    return error_response(message="Unauthorized", status_code=403)

# WRONG - No validation
# Users can access any organization's data
```

### 4. Log Cross-Tenant Access Attempts

```python
# CORRECT - Log cross-tenant attempts
if form.organization_id != user.organization_id:
    audit_logger.warning(f"Cross-tenant access: {user.email}")
    return error_response(message="Unauthorized", status_code=403)

# WRONG - No logging
# Can't detect security issues
```

### 5. Test Tenant Isolation

```python
# CORRECT - Test tenant isolation
def test_tenant_isolation():
    # Create users in different organizations
    user1 = create_user(org_id="org_1")
    user2 = create_user(org_id="org_2")

    # Create form in org_1
    form = create_form(org_id="org_1")

    # User2 should not access form from org_1
    with user2_session:
        response = client.get(f"/forms/{form.id}")
        assert response.status_code == 403

# WRONG - No tenant isolation tests
# Cross-tenant bugs may go undetected
```

---

## Configuration Reference

### Tenant Configuration

```python
# config/settings.py
class Settings(BaseSettings):
    # Multi-tenancy
    DEFAULT_ORGANIZATION_ID: str = "default"
    TENANT_ISOLATION_ENABLED: bool = True
    SUPERADMIN_BYPASS_TENANT_ISOLATION: bool = True
```

---

## References

- [Multi-Tenancy Design Patterns](https://docs.microsoft.com/en-us/azure/architecture/patterns/multi-tenancy)
- [MongoDB Multi-Tenancy](https://www.mongodb.com/blog/2016/02/23/multi-tenancy-in-mongodb/)
- [Tenant Isolation Best Practices](https://www.awsarchitectureblog.com/2019/04/08/saas-tenant-strategies/)
- [Database Design for Multi-Tenancy](https://www.kaleidoscope.com/multi-tenant-database-design/)
