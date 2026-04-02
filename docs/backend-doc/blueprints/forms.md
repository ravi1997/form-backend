# Blueprint: Forms — Core CRUD (`form_bp`)

## Registration

| Property | Value |
|----------|-------|
| Blueprint name | `form_bp` |
| URL prefix | `/form/api/v1/forms` |
| Module | `routes/v1/form/form.py` (+ additional modules imported into the same blueprint) |
| Services used | `FormService`, `SectionService` |

---

## Overview

The `form_bp` blueprint is the central blueprint of the system. It handles core Form CRUD, publish, clone, templates, import, sections CRUD, and form-level translations. Multiple route modules are combined into this single blueprint via Python imports:

- `form.py` — Core CRUD, publish, clone, templates, import, sections, translations
- `responses.py` — Submit + list responses
- `export.py` — CSV, JSON, bulk export
- `additional.py` — Slug check, share, archive, restore, delete responses, toggle-public, count, last, duplicate check
- `summarization.py` — Summarize, summarize-stream
- `misc.py` — Public submit, history, next-action
- `expire.py` — Set expiration, list expired
- `anomaly.py` — Anomaly detection
- `permissions.py` — Permissions sub-routes
- `files.py` — File upload/download
- `validation.py` — Form validation
- `hooks.py` — Form hooks

---

## Core CRUD Routes

### POST /form/api/v1/forms/

**Summary:** Create a new form.

**Authentication:** `@jwt_required()`

**Request body:**
```json
{
  "title": "Patient Intake Form",
  "description": "Collect patient data",
  "slug": "patient-intake",
  "default_language": "en",
  "supported_languages": ["en", "hi"],
  "is_template": false
}
```

Schema: `FormCreateSchema` (Pydantic)

**Auto-behavior:**
- `created_by` is set to `current_user.id`
- `editors` defaults to `[current_user.id]`
- `organization_id` defaults to `current_user.organization_id`
- `slug` is auto-generated from `title` if not provided: `re.sub(r"[^a-z0-9]+", "-", title.lower())`
- Rejects if `current_user.organization_id` is None

**Success response (201):**
```json
{
  "success": true,
  "data": { "form_id": "uuid" },
  "message": "Form created"
}
```

**Error responses:**
- `401` — User not found in context
- `400` — No organization context, or validation error

**Audit log:** `Form created with ID <id> by user <user_id>`

---

### GET /form/api/v1/forms/

**Summary:** List forms belonging to the current user's organization.

**Authentication:** `@jwt_required()`

**Query parameters:**
- `page` (int, default: 1)
- `page_size` (int, default: 50)
- `is_template` (bool string, default: `false`) — filter for templates only

**Filter applied:** `organization_id = current_user.organization_id`, `is_deleted = False`

**Response (200):**
```json
{
  "success": true,
  "data": {
    "items": [ { sanitized form objects } ],
    "total": 42,
    "page": 1,
    "page_size": 50,
    "total_pages": 1
  }
}
```

Items are sanitized via `FormSerializer.serialize()` before return.

---

### GET /form/api/v1/forms/`<form_id>`

**Summary:** Retrieve a single form, with optional language filtering.

**Authentication:** `@jwt_required()` + `@require_permission("form", "view")`

**Path parameters:** `form_id` — UUID string

**Query parameters:**
- `lang` (optional) — language code (e.g., `hi`). If provided, translations are applied via `apply_translations(form_dict, lang)`.

**Pre-condition checks:**
- `form_id` must be a valid UUID (returns 400 if not)
- Form must belong to `current_user.organization_id`
- If form has `publish_at` set and it is in the future, only users with `edit` permission can access it (others get 403 "Form is not yet available")

**Response (200):**
```json
{
  "success": true,
  "data": { sanitized form dict with sections and questions }
}
```

**Error responses:**
- `400` — Invalid UUID format
- `403` — Form not yet available (scheduled)
- `404` — Form not found

---

### PUT /form/api/v1/forms/`<form_id>`

**Summary:** Update an existing form.

**Authentication:** `@jwt_required()` + `@require_permission("form", "edit")`

**Request body:** Any subset of form fields. The handler merges with existing form data:
```json
{
  "title": "Updated Title",
  "description": "Updated description"
}
```

**Behavior:** Fetches existing form, merges update data on top of existing fields, validates with `FormUpdateSchema`, saves.

**Response (200):**
```json
{
  "success": true,
  "data": { "form_id": "uuid" },
  "message": "Form updated"
}
```

**Audit log:** `Form <form_id> updated by user <user_id>`

---

### DELETE /form/api/v1/forms/`<form_id>`

**Summary:** Soft-delete a form.

**Authentication:** `@jwt_required()` + `@require_permission("form", "delete_form")`

**Behavior:** Sets `is_deleted = True`. Form is excluded from all future queries.

**Response (200):**
```json
{
  "success": true,
  "message": "Form deleted"
}
```

**Audit log:** `Form <form_id> deleted by user <user_id>`

---

## Publish / Clone

### POST /form/api/v1/forms/`<form_id>`/publish

**Summary:** Publish a form asynchronously.

**Authentication:** `@jwt_required()` + `@require_permission("form", "edit")`

**Request body (optional):**
```json
{ "major": false, "minor": true }
```

`major` bumps the major version number; `minor` (default true) bumps the minor version.

**Behavior:** Dispatches `async_publish_form.delay(form_id, organization_id, major_bump, minor_bump)` to Celery. Returns immediately with 202.

**Response (202):**
```json
{
  "success": true,
  "data": { "task_id": "celery-task-uuid" },
  "message": "Form publishing initiated in background"
}
```

**Audit log:** `Form <form_id> publish initiated by user <user_id> (Task: <task_id>)`

---

### POST /form/api/v1/forms/`<form_id>`/clone

**Summary:** Clone a form asynchronously.

**Authentication:** `@jwt_required()` + `@require_permission("form", "view")`

**Request body (optional):**
```json
{ "title": "Copy of Form", "slug": "copy-of-form" }
```

**Behavior:** Dispatches `async_clone_form.delay(form_id, user_id, organization_id, new_title, new_slug)` to Celery. Returns 202 immediately.

**Response (202):**
```json
{
  "success": true,
  "data": { "task_id": "celery-task-uuid" },
  "message": "Form cloning initiated in background"
}
```

**Audit log:** `Form <form_id> clone initiated by user <user_id> (Task: <task_id>)`

---

## Templates

### GET /form/api/v1/forms/templates

**Summary:** List templates accessible to the current user.

**Authentication:** `@jwt_required()`

**Query:** Forms where `is_template = True` AND (`created_by = user.id` OR `user.id` in `editors`).

**Response (200):**
```json
{
  "success": true,
  "data": [ { form objects with id field normalized } ]
}
```

---

### GET /form/api/v1/forms/templates/`<template_id>`

**Summary:** Retrieve a single template.

**Authentication:** `@jwt_required()`

**Behavior:** Looks up form by `id` and `is_template = True` (no org filter). Then checks `has_form_permission(user, form, "view")`.

**Error responses:**
- `403` — User lacks view permission
- `404` — Template not found

---

## Import

### POST /form/api/v1/forms/import

**Summary:** Import a full form structure from JSON.

**Authentication:** `@jwt_required()`

**Request body:**
```json
{
  "title": "Imported Form",
  "slug": "imported-form",
  "description": "...",
  "sections": [
    {
      "title": "Section 1",
      "order": 0,
      "questions": [...],
      "sections": [ ... ]
    }
  ],
  "supported_languages": ["en"],
  "default_language": "en",
  "translations": {}
}
```

**Known risk:** References `Section` model without explicit import — will raise `NameError` if sections are provided. See `risks-and-gaps.md` R-05.

**Response (201):** Serialized form using `FormSerializer`.

---

## Sections CRUD

All section routes require `@jwt_required()` and enforce `organization_id` in form lookups.

### POST /form/api/v1/forms/`<form_id>`/sections

**Summary:** Add a new section to a form.

Delegates to `section_service.create_section(form_id, data, organization_id)`.

**Known risk:** References `BaseSerializer` without import — will raise `NameError`. See `risks-and-gaps.md` R-06.

---

### GET /form/api/v1/forms/`<form_id>`/sections

**Summary:** List all sections for a form.

Returns all sections in order.

---

### PUT /form/api/v1/forms/`<form_id>`/sections/`<section_id>`

**Summary:** Update a specific section.

Verifies form ownership before updating via `section_service.update()`.

---

### DELETE /form/api/v1/forms/`<form_id>`/sections/`<section_id>`

**Summary:** Remove a section from a form.

Calls `section_service.delete_section(form_id, section_id, organization_id)`.

---

### PUT /form/api/v1/forms/`<form_id>`/sections/reorder

**Summary:** Update section display order.

**Request body:**
```json
{ "section_ids": ["id1", "id2", "id3"] }
```

Calls `section_service.update_section_order(form_id, section_ids, organization_id)`.

---

## Form-Level Translations

### POST /form/api/v1/forms/`<form_id>`/translations

**Summary:** Update translation strings for a specific language code.

**Authentication:** `@jwt_required()`

**Request body:**
```json
{
  "lang_code": "hi",
  "translations": {
    "title": "मरीज फॉर्म",
    "questions": { "q_name": "नाम" }
  }
}
```

**Behavior:**
- Adds `lang_code` to `form.supported_languages` if not already present
- Stores translations under `form.translations[lang_code]`
- Does NOT overwrite other languages

**Access check:** `has_form_permission(user, form, "edit")` — returns 403 if lacking edit permission.

**Audit log:** `Translations for '<lang_code>' updated for form <form_id> by user <user_id>`

---

## Dependencies

- `FormService` (`services/form_service.py`) — form CRUD
- `SectionService` (`services/section_service.py`) — section operations
- `FormCreateSchema`, `FormUpdateSchema` (Pydantic)
- `async_publish_form`, `async_clone_form` (Celery tasks in `tasks/form_tasks.py`)
- `require_permission` (`utils/security_helpers.py`)
- `has_form_permission`, `apply_translations` (`routes/v1/form/helper.py`)
- `FormSerializer` (`utils/response_helper.py`)
