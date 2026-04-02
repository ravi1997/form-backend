# Blueprint: Forms — Admin Operations (`form_bp` additional module)

## Registration

| Property | Value |
|----------|-------|
| Blueprint | `form_bp` (shared with core form CRUD) |
| URL prefix | `/form/api/v1/forms` |
| Module | `routes/v1/form/additional.py` |

---

## Overview

This module contains form management operations that require elevated privileges (admin/superadmin roles). It also includes several authenticated (non-admin) utility routes for response counting, last response retrieval, and duplicate checking.

---

## Route Reference

### GET /form/api/v1/forms/slug-available

**Summary:** Check if a form slug is already taken.

**Authentication:** `@jwt_required()`

**Query parameters:** `slug` (required)

**Behavior:** Queries `Form.objects(slug=slug).first()`. Note: slugs are checked globally (not per-tenant), because slugs are globally unique in this system.

**Response (200):**
```json
{
  "success": true,
  "data": { "available": true }
}
```

**Error responses:**
- `400` — `slug` parameter not provided

---

### POST /form/api/v1/forms/`<form_id>`/share

**Summary:** Grant editor/viewer/submitter permissions for a form. Admin only.

**Authentication:** `@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)`

**Request body:**
```json
{
  "editors": ["user-id-1", "user-id-2"],
  "viewers": ["user-id-3"],
  "submitters": ["user-id-4"]
}
```

**Behavior:** Uses MongoEngine's `add_to_set` operator to append to form's `editors`, `viewers`, and `submitters` lists without duplication. Existing permissions are preserved.

**Response (200):**
```json
{
  "success": true,
  "message": "Permissions updated"
}
```

**Error responses:**
- `404` — Form not found
- `500` — Internal error

**Audit log:** Logs which editors/viewers/submitters were added.

---

### PATCH /form/api/v1/forms/`<form_id>`/archive

**Summary:** Change form status to 'archived'. Admin only.

**Authentication:** `@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)`

**Behavior:** Sets `form.status = "archived"`. Archived forms are not deleted; they are simply excluded from active form listings (depending on query filters).

**Response (200):**
```json
{
  "success": true,
  "message": "Form archived"
}
```

**Audit log:** `User <id> archived form <form_id>`

---

### PATCH /form/api/v1/forms/`<form_id>`/restore

**Summary:** Restore an archived form back to 'draft'. Admin only.

**Authentication:** `@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)`

**Behavior:** Looks up form with `status = "archived"` constraint. If found, sets `status = "draft"`.

**Response (200):**
```json
{
  "success": true,
  "message": "Form restored"
}
```

**Error responses:**
- `404` — "Archived form not found" (form doesn't exist OR is not archived)

**Audit log:** `User <id> restored form <form_id>`

---

### DELETE /form/api/v1/forms/`<form_id>`/responses

**Summary:** Purge ALL responses for a form. Admin only. **IRREVERSIBLE.**

**Authentication:** `@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)`

**Behavior:** Calls `FormResponse.objects(form=form.id).delete()` — a **hard (permanent) delete**. All `FormResponse` documents for this form are permanently removed from MongoDB. This is NOT soft-delete.

**Response (200):**
```json
{
  "success": true,
  "message": "Deleted 247 responses"
}
```

**Warning:** This operation is irreversible. There is no confirmation prompt and no grace period. See `risks-and-gaps.md` R-12.

**Audit log:** `User <id> deleted all responses for form <form_id>. Count: <count>`

---

### PATCH /form/api/v1/forms/`<form_id>`/toggle-public

**Summary:** Toggle public access for a form. Admin only.

**Authentication:** `@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)`

**Behavior:** Reads current `is_public` value, inverts it, and saves. When `is_public = True`, the form becomes accessible for anonymous submission via `public-submit`.

**Response (200):**
```json
{
  "success": true,
  "data": { "is_public": true },
  "message": "Form public access toggled"
}
```

**Audit log:** `User <id> toggled public access for form <form_id> to <new_value>`

---

### GET /form/api/v1/forms/`<form_id>`/responses/count

**Summary:** Get total submission count for a form.

**Authentication:** `@jwt_required()`

**Behavior:** Queries `FormResponse.objects(form=form.id).count()`. Enforces org isolation via form lookup. Does NOT filter by `is_deleted` on responses — counts all responses.

**Response (200):**
```json
{
  "success": true,
  "data": {
    "form_id": "uuid",
    "response_count": 247
  }
}
```

---

### GET /form/api/v1/forms/`<form_id>`/responses/last

**Summary:** Fetch the most recent response record for a form.

**Authentication:** `@jwt_required()`

**Behavior:** Queries `FormResponse.objects(form=form.id).order_by("-submitted_at").first()`. Returns 404 if no responses exist.

**Response (200):**
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "form": "form-uuid",
    "data": { ... },
    "submitted_at": "2026-04-01T10:30:00Z",
    ...
  }
}
```

---

### POST /form/api/v1/forms/`<form_id>`/check-duplicate

**Summary:** Check if the current user has already submitted this exact data.

**Authentication:** `@jwt_required()`

**Request body:**
```json
{
  "data": { "field": "value", "field2": "value2" }
}
```

**Behavior:** Queries `FormResponse.objects(form=form.id, submitted_by=user_id, data=submitted_data).first()`. The `data` field comparison is an exact match against the provided dict. Returns `duplicate: true` if a match is found.

**Response (200):**
```json
{
  "success": true,
  "data": { "duplicate": false }
}
```

---

## Route Summary

| Method | Path | Auth | Role |
|--------|------|------|------|
| GET | `/forms/slug-available` | JWT | any |
| POST | `/forms/<id>/share` | JWT | admin |
| PATCH | `/forms/<id>/archive` | JWT | admin |
| PATCH | `/forms/<id>/restore` | JWT | admin |
| DELETE | `/forms/<id>/responses` | JWT | admin |
| PATCH | `/forms/<id>/toggle-public` | JWT | admin |
| GET | `/forms/<id>/responses/count` | JWT | any |
| GET | `/forms/<id>/responses/last` | JWT | any |
| POST | `/forms/<id>/check-duplicate` | JWT | any |

---

## Dependencies

- `Form`, `FormResponse` models
- `require_roles` (`utils/security.py`)
- `get_current_user` (local helper)
- `audit_logger`, `app_logger`, `error_logger`
