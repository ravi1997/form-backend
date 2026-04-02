# Blueprint: Forms — Advanced Responses (`advanced_responses_bp`)

## Registration

| Property | Value |
|----------|-------|
| Blueprint name | `advanced_responses` |
| URL prefix | `/form/api/v1/forms` (same as `form_bp`) |
| Module | `routes/v1/form/advanced_responses.py` |

**Note:** This blueprint shares the URL prefix `/form/api/v1/forms` with `form_bp`. Both blueprints are registered and active. Route conflicts are avoided because `advanced_responses_bp` routes use distinct path patterns (`/fetch/external`, `/<form_id>/fetch/same`, etc.).

---

## Overview

This module provides specialized response query capabilities:
- Cross-form data lookup (find responses in another form matching a value)
- Same-form data lookup by question value
- Specific question extraction across all responses
- Response metadata summary
- Per-user permission report for a form
- Access policy management

All routes return raw `jsonify()` responses (not `success_response()`) — clients should check the HTTP status code rather than a `success` field for these routes.

---

## Route Reference

### GET /form/api/v1/forms/fetch/external

**Summary:** Fetch data from another form's responses where a specific question matches a value.

**Authentication:** `@jwt_required()`

**Query parameters (all required):**
- `form_id` — ID of the target form (can be any form visible to the user)
- `question_id` — question ID to match against
- `value` — value to search for

**Behavior:**
1. Looks up form by `form_id` (no org filter — **gap**, see risks R-09)
2. Checks `has_form_permission(user, form, "view")`
3. Searches `FormResponse` documents where `data.<section_id>.<question_id> == value` across all sections of the latest version
4. Returns matching response documents

**Important limitation:** The query constructs `$or` conditions using `form.versions[-1].sections`. If the form has no versions, the `$or` clause is empty, which may return no results or all results depending on MongoDB behavior.

**Response (200):** Array of raw MongoEngine `to_mongo().to_dict()` response objects.

**Error responses:**
- `400` — Missing `form_id`, `question_id`, or `value`
- `403` — Unauthorized to view form
- `404` — Form not found
- `500` — Query error

---

### GET /form/api/v1/forms/`<form_id>`/fetch/same

**Summary:** Fetch responses from the same form where a specific question matches a value.

**Authentication:** `@jwt_required()`

**Query parameters:**
- `question_id` (required)
- `value` (required)

**Behavior:** Same as `fetch/external` but targets the form specified in the path parameter. Uses `form.versions[-1].sections` for query construction.

**Response (200):** Array of matching response documents.

**Error responses:**
- `400` — Missing `question_id` or `value`
- `403` — Unauthorized
- `404` — Form not found
- `500` — Error

---

### GET /form/api/v1/forms/`<form_id>`/responses/questions

**Summary:** Extract specific question values from all responses for a form.

**Authentication:** `@jwt_required()`

**Query parameters:**
- `question_ids` (required) — comma-separated list: `?question_ids=q1,q2,q3`

**Behavior:**
1. Fetches all non-deleted responses for the form
2. For each response, iterates all sections in `response.data`
3. Extracts values for the requested question IDs from each section
4. Returns extracted data per response

**Response (200):**
```json
[
  {
    "response_id": "uuid",
    "data": {
      "q1": "value1",
      "q2": "value2"
    },
    "submitted_at": "2026-04-01T10:30:00Z"
  }
]
```

**Error responses:**
- `400` — Missing `question_ids`
- `403` — Unauthorized
- `404` — Form not found
- `500` — Error

---

### GET /form/api/v1/forms/`<form_id>`/responses/meta

**Summary:** Get meta information about form responses.

**Authentication:** `@jwt_required()`

**Behavior:** Performs 3 separate MongoDB count queries:
1. Total non-deleted responses
2. Draft (incomplete) responses
3. Submitted = total - draft

Also fetches the most recent submission timestamp.

**Response (200):**
```json
{
  "form_id": "uuid",
  "total_responses": 100,
  "draft_count": 5,
  "submitted_count": 95,
  "last_submission": "2026-04-01T10:30:00Z"
}
```

`last_submission` is `null` if no responses exist.

**Error responses:**
- `403` — Unauthorized
- `404` — Form not found
- `500` — Error

---

### GET /form/api/v1/forms/micro-info

**Summary:** Placeholder route. Returns empty data.

**Authentication:** `@jwt_required()`

**Response (200):**
```json
{ "message": "Micro information retrieved", "data": {} }
```

**Status:** Stub/placeholder. Not implemented.

---

### GET /form/api/v1/forms/`<form_id>`/access-control

**Summary:** Get the current user's full permission report for a form.

**Authentication:** `@jwt_required()`

**Behavior:** Evaluates all supported permission types for the current user against the form. Does NOT require any specific permission — any authenticated user can query their own access report.

**Response (200):**
```json
{
  "form_id": "uuid",
  "title": "Patient Intake",
  "current_user": {
    "id": "user-uuid",
    "roles": ["user"],
    "department": "radiology"
  },
  "is_public": false,
  "permissions": {
    "view_form": true,
    "submit_form": true,
    "edit_design": false,
    "manage_access": false,
    "view_responses": false,
    "edit_responses": false,
    "delete_responses": false,
    "view_audit": false,
    "delete_form": false
  },
  "policy_summary": {
    "visibility": "private",
    "response_scope": "own_only",
    "allowed_departments": ["radiology"]
  }
}
```

`policy_summary` is `null` if the form has no `access_policy` document embedded.

---

### POST /form/api/v1/forms/`<form_id>`/access-policy

### PUT /form/api/v1/forms/`<form_id>`/access-policy

**Summary:** Update the access policy for a form.

**Authentication:** `@jwt_required()`

**Permission check:** `has_form_permission(user, form, "manage_access")` — 403 if lacking.

**Request body:**
```json
{
  "form_visibility": "private",
  "response_visibility": "own_only",
  "allowed_departments": ["radiology", "oncology"],
  "can_view_responses": true,
  "can_edit_responses": false,
  "can_delete_responses": false,
  "can_create_versions": true,
  "can_edit_design": true,
  "can_clone_form": true,
  "can_manage_access": false,
  "can_view_audit_logs": true,
  "can_delete_form": false
}
```

All fields are optional. Only provided fields are updated on the embedded `AccessPolicy` document.

**Behavior:**
- If `form.access_policy` is None, creates a new `AccessPolicy` embedded document
- Iterates the known policy fields and updates each one present in the request

**Response (200):**
```json
{
  "message": "Access policy updated successfully",
  "policy": { ... current AccessPolicy fields ... }
}
```

**Audit log:** `User <id> updated access policy for form <form_id>. Updated fields: [...]`

---

## Route Summary

| Method | Path | Auth |
|--------|------|------|
| GET | `/forms/fetch/external` | JWT |
| GET | `/forms/<id>/fetch/same` | JWT |
| GET | `/forms/<id>/responses/questions` | JWT |
| GET | `/forms/<id>/responses/meta` | JWT |
| GET | `/forms/micro-info` | JWT |
| GET | `/forms/<id>/access-control` | JWT |
| POST/PUT | `/forms/<id>/access-policy` | JWT + manage_access permission |

---

## Dependencies

- `Form`, `FormResponse` models
- `AccessPolicy` model (`models/`)
- `has_form_permission` (`routes/v1/form/helper.py`)
- `get_current_user` (local helper)
