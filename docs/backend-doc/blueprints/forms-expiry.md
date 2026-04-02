# Blueprint: Forms — Expiry Management (`form_bp` expire module)

## Registration

| Property | Value |
|----------|-------|
| Blueprint | `form_bp` (shared) |
| URL prefix | `/form/api/v1/forms` |
| Module | `routes/v1/form/expire.py` |

---

## Overview

Provides admin-only endpoints for managing form expiration. Forms can be configured to automatically become unavailable after a specific date. Expired forms reject new submissions.

---

## Route Reference

### PATCH /form/api/v1/forms/`<form_id>`/expire

**Summary:** Set a form's expiration date. Admin only.

**Authentication:** `@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)`

**Request body:**
```json
{
  "expires_at": "2026-12-31T23:59:59Z"
}
```

The `expires_at` field must be a valid ISO 8601 datetime string. Both offset-aware (`2026-12-31T23:59:59Z`) and naive formats are accepted; naive datetimes are treated as UTC.

**Behavior:**
1. Validates `expires_at` is present (400 if missing)
2. Parses the datetime string with `datetime.fromisoformat()`; replaces `"Z"` with `"+00:00"` for compatibility
3. If parsed datetime is timezone-naive, attaches UTC timezone
4. Updates `form.expires_at` using MongoEngine's `form.update(set__expires_at=exp_dt)`

**Form lookup:** `Form.objects.get(id=form_id)` — no `organization_id` filter. Any admin can set expiry on any form.

**Response (200):**
```json
{ "message": "Form expiration updated to 2026-12-31T23:59:59+00:00" }
```

Note: Returns raw `jsonify()`, not `success_response()`.

**Error responses:**
- `400` — Missing `expires_at`: `{"error": "Expiration date is required"}`
- `400` — Invalid date format: `{"error": "Invalid date format, use ISO 8601"}`
- `404` — Form not found: `{"error": "Form not found"}`
- `400` — Other errors

**Audit log:** `Form expiration updated for form_id: <id> to <datetime> by user: <user_id>`

---

### GET /form/api/v1/forms/expired

**Summary:** List all forms that have passed their expiration date. Admin only.

**Authentication:** `@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)`

**Behavior:**
- Queries `Form.objects(expires_at__lt=now)` — no tenant filter
- Returns ALL expired forms in the system (cross-tenant)
- Each form document is normalized: `_id` renamed to `id`

**Response (200):** Raw `jsonify()` array:
```json
[
  {
    "id": "form-uuid",
    "title": "Old Registration Form",
    "organization_id": "org-uuid",
    "expires_at": "2026-01-01T00:00:00Z",
    "status": "published",
    ...
  }
]
```

**Error responses:**
- `500` — Internal server error: `{"error": "Internal server error"}`

---

## Expiry Enforcement

The expiry date set via this endpoint is enforced at two points:

1. **Authenticated submission** (`responses.py` — `submit_response`):
   ```python
   if form.expires_at and form.expires_at < now:
       return error_response("This form has expired", 400)
   ```

2. **Public submission** (`misc.py` — `submit_public_response`):
   ```python
   if form.expires_at and now > form.expires_at:
       return error_response("Form has expired", 403)
   ```

Note: The expiry check in authenticated submission returns 400; the check in public submission returns 403. This is an inconsistency.

---

## Notes

- No automatic archiving occurs when a form expires — `status` remains `"published"`. Only new submissions are rejected.
- To prevent access to expired form content entirely, manually archive the form.
- The `expired` listing endpoint is cross-tenant (no org scope) — returns expired forms from all organizations.
