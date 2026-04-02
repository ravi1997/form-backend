# Blueprint: Forms — Responses (`form_bp` responses module)

## Registration

| Property | Value |
|----------|-------|
| Blueprint | `form_bp` (shared with core form CRUD) |
| URL prefix | `/form/api/v1/forms` |
| Module | `routes/v1/form/responses.py` |
| Services used | `FormResponseService` |

---

## Overview

This module handles form response submission and listing. All operations enforce organization isolation and per-form permission checks. The submission pipeline includes lifecycle validation (expiry, publish schedule) in addition to permission checks.

---

## Route Reference

### POST /form/api/v1/forms/`<form_id>`/responses

**Summary:** Submit a response to a form (authenticated).

**Authentication:** `@jwt_required()`

**Path parameters:** `form_id` — UUID

**Request body:**
```json
{
  "data": {
    "patient_name": "John Doe",
    "age": 35,
    "symptoms": ["fever", "cough"],
    "department": "radiology"
  }
}
```

The `data` field is a free-form dict mapping question variable names to their values.

**Pre-condition validation (in order):**
1. `form_id` must be a valid UUID (400 if not)
2. Form must exist, belong to `current_user.organization_id`, and not be deleted (404 if not)
3. User must have `submit` permission on the form (403 if not)
4. Form must not be expired: `form.expires_at < now` → 400 "This form has expired"
5. Form must not be scheduled in future: `form.publish_at > now` → 400 "This form is not yet available"

**Submission data recorded:**
- `form` — form ID
- `organization_id` — current user's org
- `data` — submitted field values
- `submitted_by` — `current_user.id`
- `ip_address` — `request.remote_addr`
- `user_agent` — `request.user_agent.string`
- `project` — if form has an associated project

**Success response (201):**
```json
{
  "success": true,
  "data": { "response_id": "uuid" },
  "message": "Response submitted successfully"
}
```

**Error responses:**
- `400` — Invalid UUID format
- `400` — Form expired
- `400` — Form not yet available
- `400` — Other validation errors
- `403` — No submit permission
- `404` — Form not found

**Audit log:**
```
User <user_id> submitted response <response_id> to form <form_id>
```
With structured extra: `user_id`, `form_id`, `response_id`, `organization_id`, `action: submit_response`

---

### GET /form/api/v1/forms/`<form_id>`/responses

**Summary:** List responses for a specific form (paginated).

**Authentication:** `@jwt_required()`

**Path parameters:** `form_id` — UUID

**Query parameters:**
- `page` (int, default: 1)
- `page_size` (int, default: 20)

**Permission check:** User must have `view_responses` permission on the form (403 if not).

**Response (200):**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "uuid",
        "form": "form-uuid",
        "organization_id": "org-uuid",
        "data": { ... },
        "submitted_by": "user-uuid",
        "submitted_at": "2026-04-01T10:30:00Z",
        "status": "submitted",
        "ip_address": "10.0.0.1",
        "user_agent": "Mozilla/5.0..."
      }
    ],
    "total": 100,
    "page": 1,
    "page_size": 20,
    "total_pages": 5
  }
}
```

**Error responses:**
- `403` — No view_responses permission
- `404` — Form not found
- `400` — Unexpected error

---

## Dependencies

- `FormResponseService` (`services/response_service.py`)
- `FormResponseCreateSchema` (Pydantic schema in `services/response_service.py`)
- `has_form_permission` (`routes/v1/form/helper.py`)
- `Form`, `FormVersion` (`models/Form.py`)

---

## Notes

- Anonymous (public) submission is handled in `misc.py` at `POST /forms/<form_id>/public-submit` — not in this module
- This route (`POST /responses`) requires authentication; public-submit does not
- The `submitted_by` field uses the authenticated user's ID string; anonymous submissions use `"anonymous"`
- `ip_address` and `user_agent` are recorded for all submissions
