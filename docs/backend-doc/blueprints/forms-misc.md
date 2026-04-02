# Blueprint: Forms — Miscellaneous (`form_bp` misc module)

## Registration

| Property | Value |
|----------|-------|
| Blueprint | `form_bp` (shared) |
| URL prefix | `/form/api/v1/forms` |
| Module | `routes/v1/form/misc.py` |

---

## Overview

This module contains three route categories:
1. **Public (anonymous) submission** — the only unauthenticated write endpoint in the system
2. **Submission history lookup** — chronological history of responses by a primary identifier value
3. **Workflow next-action check** — identifies applicable workflows for a form or response

---

## Route Reference

### POST /form/api/v1/forms/`<form_id>`/public-submit

**Summary:** Submit a response to a public form without authentication.

**Authentication:** None — no `@jwt_required()` decorator

**Request body:**
```json
{
  "data": {
    "field_name": "value",
    "another_field": "another_value"
  }
}
```

**Pre-condition checks (in order):**
1. Form must exist (`is_deleted = False`) — 404 if not
2. Form must be `published` — 403 "Form is {status}, not accepting submissions"
3. Form must not be expired: `expires_at < now` — 403 "Form has expired"
4. Form must not be scheduled in future: `publish_at > now` — 403 "Form is not yet available"
5. Form must have `is_public = True` — 403 "Form is not public"

**Note on form lookup:** `Form.objects.get(id=form_id, is_deleted=False)` — NO `organization_id` filter. Any public form can be submitted by anyone who has the UUID, regardless of which organization owns it.

**Submission data recorded:**
- `submitted_by` = `"anonymous"` (literal string, not a user ID)
- `organization_id` = `form.organization_id` (taken from the form document)
- `ip_address` = `request.remote_addr`
- `user_agent` = `request.user_agent.string`

**Success response (201):**
```json
{
  "success": true,
  "data": { "response_id": "uuid" },
  "message": "Response submitted anonymously"
}
```

**Error responses:**
- `403` — Form not published / expired / scheduled / not public
- `404` — Form not found
- `400` — Validation error

**Audit log:** `Anonymous response <response_id> submitted for form <form_id>`

---

### GET /form/api/v1/forms/`<form_id>`/history

**Summary:** Get the submission history for a specific question value.

**Authentication:** `@jwt_required()`

**Query parameters (both required):**
- `question_id` — the question field name to search on
- `primary_value` — the value to match (e.g., a patient ID, registration number)

**Behavior:**
1. Validates both parameters are present (400 if missing)
2. Queries: `FormResponse.objects(data__<question_id>=primary_value, form=form_id, organization_id=current_user.organization_id, is_deleted=False).order_by("submitted_at").limit(100)`
3. Returns chronological list of matching submission IDs and timestamps

**Response (200):**
```json
{
  "success": true,
  "data": [
    { "_id": "response-uuid-1", "submitted_at": "2026-01-01T10:00:00Z" },
    { "_id": "response-uuid-2", "submitted_at": "2026-02-15T14:30:00Z" }
  ]
}
```

Returns at most 100 records (hard limit). Sorted ascending by `submitted_at`.

**Error responses:**
- `400` — Missing `question_id` or `primary_value`
- `500` — Internal server error

**Use case:** Track all form submissions associated with a particular patient ID, employee number, or other primary identifier across time.

---

### GET /form/api/v1/forms/`<form_id>`/next-action

**Summary:** Check applicable workflows for a form or a specific response.

**Authentication:** `@jwt_required()`

**Query parameters:**
- `response_id` (optional) — if provided, evaluates workflows for a specific submitted response

**Behavior (without `response_id`):**
- Lists all active `ApprovalWorkflow` documents where `trigger_form_id = form_id` and `organization_id = current_user.organization_id`
- Returns workflow summaries

**Response (without response_id):**
```json
{
  "form_id": "uuid",
  "workflows": [
    {
      "id": "wf-uuid",
      "name": "Patient Approval Flow",
      "description": "Approval required for new patients",
      "steps_count": 3
    }
  ],
  "count": 1
}
```

**Behavior (with `response_id`):**
- Verifies the response exists for the form and org
- Finds active workflows for the form
- Returns triggered workflow identifiers and first step names

**Response (with response_id):**
```json
{
  "success": true,
  "data": {
    "form_id": "uuid",
    "response_id": "response-uuid",
    "triggered_workflows": [
      {
        "workflow_id": "wf-uuid",
        "workflow_name": "Patient Approval Flow",
        "first_step": "Department Review"
      }
    ]
  }
}
```

**Error responses:**
- `401` — User not found in context
- `404` — Form not found (returns raw `jsonify`)
- `404` — Response not found (when `response_id` provided)
- `400` — Other errors

---

## Dependencies

- `Form`, `FormResponse` models
- `ApprovalWorkflow` model (`models/Workflow.py`)
- `FormResponseService` (instantiated locally in `public-submit`)
- `execute_safe_script` (`utils/script_engine.py`) — imported but not directly used in these routes
- `get_current_user` (`routes/v1/form/helper.py`)
