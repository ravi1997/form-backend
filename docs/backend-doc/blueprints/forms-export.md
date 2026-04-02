# Blueprint: Forms — Export (`form_bp` export module)

## Registration

| Property | Value |
|----------|-------|
| Blueprint | `form_bp` (shared with core form CRUD) |
| URL prefix | `/form/api/v1/forms` |
| Module | `routes/v1/form/export.py` |
| Services used | `BulkExport` model, `async_bulk_export` Celery task |

---

## Overview

This module provides three export mechanisms:
1. **Streaming CSV** — tenant-scoped, version-aware, memory-efficient
2. **Streaming JSON** — tenant-scoped, includes form metadata + responses
3. **Bulk Export (async)** — Celery-backed multi-form ZIP export

All export routes require `view_responses` permission on the form(s) being exported.

---

## Route Reference

### GET /form/api/v1/forms/`<form_id>`/export/csv

**Summary:** Stream all responses for a form as CSV.

**Authentication:** `@jwt_required()`

**Path parameters:** `form_id`

**Query parameters:**
- `version_id` (optional) — export against a specific `FormVersion`'s resolved snapshot. Defaults to the form's active version.

**Permission check:** `has_form_permission(user, form, "view_responses")` — 403 if lacking.

**Behavior:**
- Uses Python generator (`stream_form_csv`) to yield rows incrementally — does not load all responses into memory at once
- Column headers are derived from `FormVersion.resolved_snapshot.sections[].questions[].variable_name` and `label`
- If no version is resolved, falls back to a single `data (raw)` column with JSON-encoded response data
- Response objects are fetched with `.no_cache().timeout(False)` for large dataset safety

**Response headers:**
```
Content-Type: text/csv
Content-Disposition: attachment;filename=form_<form_id>_<timestamp>.csv
X-Content-Type-Options: nosniff
```

**CSV column structure:**
```
response_id, submitted_by, submitted_at, status, [Section Title - ]Question Label, ...
```

If the form has only one section, the section title prefix is omitted. If multiple sections exist, each column is prefixed with the section title.

**Error responses:**
- `403` — No view_responses permission
- `404` — Form not found
- `500` — Internal server error

**Audit log:** `CSV streaming export initiated for form_id: <id> by user: <user_id>`

---

### GET /form/api/v1/forms/`<form_id>`/export/json

**Summary:** Stream all responses for a form as JSON.

**Authentication:** `@jwt_required()`

**Permission check:** `has_form_permission(user, form, "view_responses")` — 403 if lacking.

**Behavior:**
- Uses Python generator (`stream_form_json`) to yield JSON incrementally
- Output is NOT a JSON array — it is a streaming JSON object

**Response structure (streaming):**
```json
{
  "form_metadata": {
    "id": "uuid",
    "title": "Form Title",
    "slug": "form-slug",
    "created_by": "user-id",
    "created_at": "2026-01-01T00:00:00",
    "status": "published",
    "is_public": false,
    "organization_id": "org-uuid"
  },
  "responses": [
    { response objects from to_dict() },
    ...
  ]
}
```

**Response headers:**
```
Content-Type: application/json
Content-Disposition: attachment;filename=form_<form_id>_<timestamp>.json
```

**Error responses:**
- `403` — No view_responses permission
- `404` — Form not found
- `500` — Internal server error

**Audit log:** `JSON streaming export initiated for form_id: <id> by user: <user_id>`

---

### POST /form/api/v1/forms/export/bulk

**Summary:** Initiate an asynchronous bulk export job for multiple forms.

**Authentication:** `@jwt_required()`

**Request body:**
```json
{
  "form_ids": ["uuid1", "uuid2", "uuid3"]
}
```

**Behavior:**
1. Validates `form_ids` is non-empty (400 if empty)
2. Creates a `BulkExport` document with `status = "pending"`
3. Dispatches `async_bulk_export.delay(job_id, organization_id)` to Celery
4. Returns 202 with `job_id`

**Response (202):**
```json
{
  "success": true,
  "data": {
    "job_id": "uuid",
    "status": "pending"
  },
  "message": "Bulk export job accepted"
}
```

**Error responses:**
- `400` — Missing `form_ids` or empty list

**Audit log:** `Async bulk export job <job_id> initiated by user <user_id>`

---

### GET /form/api/v1/forms/export/bulk/`<job_id>`

**Summary:** Check the status of a bulk export job.

**Authentication:** `@jwt_required()`

**Behavior:** Looks up `BulkExport.objects.get(id=job_id, organization_id=current_user.organization_id)` — org-scoped.

**Response (200):**
```json
{
  "success": true,
  "data": {
    "job_id": "uuid",
    "status": "completed",
    "created_at": "2026-04-02T10:00:00Z",
    "completed_at": "2026-04-02T10:05:00Z",
    "error_message": null
  }
}
```

Status values: `pending` → `processing` → `completed` | `failed`

**Error responses:**
- `404` — Job not found (or belongs to different org)

---

### GET /form/api/v1/forms/export/bulk/`<job_id>`/download

**Summary:** Download the completed bulk export ZIP file.

**Authentication:** `@jwt_required()`

**Behavior:**
- Verifies job exists for current org
- Verifies `job.status == "completed"` (400 if not)
- Verifies `job.file_binary` is present (404 if missing)
- Returns binary ZIP data

**Response headers:**
```
Content-Type: application/zip
Content-Disposition: attachment;filename=bulk_export_<timestamp>.zip
```

**Error responses:**
- `400` — Job is not in completed state (includes current status in message)
- `404` — Job not found, or export file not found

---

## Streaming Architecture

### CSV Streaming (`stream_form_csv`)

The generator function writes to an in-memory `io.StringIO` buffer, yields the content, then truncates and resets the buffer for the next row. This approach:
- Never loads more than one response into memory at a time
- Supports exports of arbitrarily large datasets
- Uses MongoEngine's `.no_cache().timeout(False)` cursor options

### JSON Streaming (`stream_form_json`)

Manually constructs valid JSON by yielding string fragments:
1. Yields `{"form_metadata": {...}, "responses": [`
2. Iterates responses, yielding `,` separator before each (except the first)
3. Yields `]}` to close

This bypasses standard JSON serialization to support streaming.

---

## Dependencies

- `BulkExport` model (`models/Response.py`)
- `async_bulk_export` Celery task (`tasks/form_tasks.py`)
- `has_form_permission` (`routes/v1/form/helper.py`)
- `FormVersion` model — for `resolved_snapshot` access
- `FormResponse` model — iterated for streaming
