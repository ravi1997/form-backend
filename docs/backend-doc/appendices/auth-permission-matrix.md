# Authorization & Permission Matrix

## 1. Role Hierarchy

```
superadmin
    └─ admin
          └─ manager
                └─ user
```

Higher roles subsume all permissions of lower roles. A user may have multiple roles.

---

## 2. Global Role Permissions

| Operation | user | manager | admin | superadmin |
|-----------|------|---------|-------|-----------|
| View own profile | ✓ | ✓ | ✓ | ✓ |
| Change own password | ✓ | ✓ | ✓ | ✓ |
| Submit forms (with permission) | ✓ | ✓ | ✓ | ✓ |
| View analytics dashboard | ✗ | ✓ | ✓ | ✓ |
| Trigger webhook delivery | ✗ | ✓ | ✓ | ✓ |
| Send SMS notification | ✗ | ✓ | ✓ | ✓ |
| View analytics summary | ✗ | ✗ | ✓ | ✓ |
| List all users | ✗ | ✗ | ✓ | ✓ |
| Create/update users | ✗ | ✗ | ✓ | ✓ |
| Update user roles | ✗ | ✗ | ✓ | ✓ |
| Lock/unlock user accounts | ✗ | ✗ | ✓ | ✓ |
| Archive/restore forms | ✗ | ✗ | ✓ | ✓ |
| Share form (grant permissions) | ✗ | ✗ | ✓ | ✓ |
| Toggle form public access | ✗ | ✗ | ✓ | ✓ |
| Delete all form responses | ✗ | ✗ | ✓ | ✓ |
| Set form expiration | ✗ | ✗ | ✓ | ✓ |
| View expired forms | ✗ | ✗ | ✓ | ✓ |
| Send OTP (admin tool) | ✗ | ✗ | ✓ | ✓ |
| Delete user accounts | ✗ | ✗ | ✗ | ✓ |
| Manage env config | ✗ | ✗ | ✗ | ✓ |

---

## 3. Form-Level Permission Matrix

Each form has its own ACL. The `has_form_permission(user, form, action)` function evaluates permissions in this priority order:

| Check | Priority | Grants |
|-------|----------|--------|
| User is `superadmin` | 1 (highest) | All permissions |
| User is `admin` | 2 | Most permissions |
| User ID in `form.created_by` | 3 | All permissions |
| User ID in `form.editors` | 4 | edit, view, view_responses, edit_responses |
| User ID in `form.viewers` | 5 | view only |
| User ID in `form.submitters` | 6 | submit only |
| `form.access_policy` grants | 7 | Policy-defined |
| `form.is_public = True` | 8 | Submit (for public-submit route) |

### Per-Action Requirements

| Action string | Who can perform it |
|--------------|-------------------|
| `view` | Owner, editors, viewers, admins, superadmins |
| `edit` | Owner, editors, admins, superadmins |
| `submit` | Owner, submitters, editors, admins, superadmins (or anyone for public forms) |
| `view_responses` | Owner, editors, admins, superadmins (+ access_policy.can_view_responses) |
| `edit_responses` | Owner, editors, admins (+ access_policy.can_edit_responses) |
| `delete_responses` | Owner, admins, superadmins (+ access_policy.can_delete_responses) |
| `edit_design` | Owner, editors, admins (+ access_policy.can_edit_design) |
| `manage_access` | Owner, admins, superadmins (+ access_policy.can_manage_access) |
| `view_audit` | Owner, admins, superadmins (+ access_policy.can_view_audit_logs) |
| `delete_form` | Owner, admins, superadmins (+ access_policy.can_delete_form) |
| `clone` | Owner, editors, admins (+ access_policy.can_clone_form) |

---

## 4. Resource Permission Decorators

### `@require_roles(*roles)` — `utils/security.py`

Wraps `@jwt_required()`. Verifies that the authenticated user has at least one of the specified roles.

```python
@require_roles("admin", "superadmin")
def admin_only_route():
    ...
```

If role check fails: 403 Forbidden.

### `@require_permission("resource", "action")` — `utils/security_helpers.py`

Used for resource-level permission checks at the route boundary. The resource and action strings map to an internal permission evaluation function.

```python
@require_permission("form", "edit")
def update_form(form_id):
    ...
```

### `has_form_permission(user, form, action)` — `routes/v1/form/helper.py`

Inline function called within route handlers for form-level ACL checks. Returns `True` or `False`.

---

## 5. Authentication Methods

| Method | Header/Cookie | CSRF Required |
|--------|-------------|--------------|
| Bearer token | `Authorization: Bearer <token>` | No |
| Access cookie | `access_token` HttpOnly cookie | Yes: `X-CSRF-TOKEN-ACCESS` |
| Refresh (header) | `Authorization: Bearer <refresh_token>` | No |
| Refresh (cookie) | `refresh_token` HttpOnly cookie | Yes: `X-CSRF-TOKEN-REFRESH` |

---

## 6. Public (No Auth) Endpoints

| Endpoint | Access |
|----------|--------|
| `POST /form/api/v1/auth/register` | Anyone |
| `POST /form/api/v1/auth/login` | Anyone |
| `POST /form/api/v1/auth/request-otp` | Anyone |
| `GET /form/api/v1/ai/health` | Anyone |
| `GET /form/health` | Anyone |
| `POST /form/api/v1/forms/<id>/public-submit` | Anyone (form must be public + published) |
| `GET /form/api/v1/view/` | Anyone (renders HTML) |
| `GET /form/api/v1/view/<form_id>` | Anyone (renders HTML, any form) |

---

## 7. AccessPolicy Document Fields

The `AccessPolicy` embedded document allows fine-grained control at the form level:

| Field | Type | Default | Controls |
|-------|------|---------|---------|
| `can_view_responses` | bool | false | Who can list/read responses |
| `can_edit_responses` | bool | false | Who can modify responses |
| `can_delete_responses` | bool | false | Who can delete responses |
| `can_create_versions` | bool | false | Who can publish new versions |
| `can_edit_design` | bool | false | Who can change form structure |
| `can_clone_form` | bool | false | Who can clone this form |
| `can_manage_access` | bool | false | Who can update this policy |
| `can_view_audit_logs` | bool | false | Who can view audit trail |
| `can_delete_form` | bool | false | Who can soft-delete the form |
| `form_visibility` | string | `"private"` | `"private"` or `"public"` |
| `response_visibility` | string | `"own_only"` | `"own_only"`, `"all"`, etc. |
| `allowed_departments` | list | [] | Department-based access filter |
