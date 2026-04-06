# Getting Started — RIDP Form Platform API

**Audience:** Frontend developers, QA engineers, integration teams.
**Purpose:** Step-by-step walkthrough of every API call in the order you must make them, with no ambiguity about what depends on what.

---

## Table of Contents

1. [Base URL and Conventions](#1-base-url-and-conventions)
2. [Authentication](#2-authentication)
3. [User Management](#3-user-management)
4. [Building a Form](#4-building-a-form)
5. [Publishing a Form](#5-publishing-a-form)
6. [Setting Form Permissions](#6-setting-form-permissions)
7. [File Uploads](#7-file-uploads)
8. [Submitting Responses](#8-submitting-responses)
9. [Viewing and Querying Responses](#9-viewing-and-querying-responses)
10. [Per-Form Analytics](#10-per-form-analytics)
11. [Exporting Data](#11-exporting-data)
12. [Summarization and AI](#12-summarization-and-ai)
13. [Translations](#13-translations)
14. [Dashboard Management](#14-dashboard-management)
15. [Workflows](#15-workflows)
16. [Webhooks](#16-webhooks)
17. [Advanced Queries](#17-advanced-queries)
18. [System-Level Analytics](#18-system-level-analytics)
19. [Admin Operations](#19-admin-operations)
20. [Complete Lifecycle Cheatsheet](#20-complete-lifecycle-cheatsheet)

---

## 1. Base URL and Conventions

```
Base: http://<host>/form/api/v1
Swagger UI: http://<host>/form/docs
Health check: GET http://<host>/form/health
```

**All responses follow this shape:**
```json
{
  "success": true,
  "data": { ... },
  "message": "Human-readable description"
}
```

**Error responses:**
```json
{
  "success": false,
  "message": "What went wrong",
  "error": "Optional detail"
}
```

**Pagination shape** (for list endpoints):
```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5
}
```

**Rate limits are per-user, per-tenant, backed by Redis. If you hit 429, wait and retry.**

---

## 2. Authentication

Every authenticated request needs a valid `access_token`. Follow this flow once per session.

### Step 2.1 — Register a new user (first time only)

```http
POST /form/api/v1/auth/register
Content-Type: application/json
Rate-limit: 5 per minute

{
  "email": "alice@hospital.org",
  "password": "SecurePass123!",
  "username": "alice",
  "organization_id": "org-uuid-here"
}
```

**Response 201:**
```json
{
  "success": true,
  "data": {
    "user": {
      "id": "user-uuid",
      "email": "alice@hospital.org",
      "username": "alice",
      "roles": ["user"],
      "organization_id": "org-uuid-here",
      "is_active": true
    }
  },
  "message": "User registered successfully"
}
```

**Save:** `user.id`

---

### Step 2.2 — Login (password)

```http
POST /form/api/v1/auth/login
Content-Type: application/json
Rate-limit: 5 per minute

{
  "email": "alice@hospital.org",
  "password": "SecurePass123!"
}
```

Alternatively, use `username` or `employee_id` as the identifier key:
```json
{ "username": "alice", "password": "SecurePass123!" }
{ "employee_id": "EMP001", "password": "SecurePass123!" }
```

**Response 200:**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "user": { "id": "...", "email": "...", "roles": ["user"], "organization_id": "..." }
  },
  "message": "Login successful"
}
```

Server also sets `access_token` and `refresh_token` HttpOnly cookies automatically.

**Save:** `access_token`, `refresh_token`, `user.id`, `user.organization_id`

---

### Step 2.3 — Login (OTP — 2-step)

**Step A — Request OTP:**
```http
POST /form/api/v1/auth/request-otp
Content-Type: application/json
Rate-limit: 3 per minute

{ "mobile": "9876543210" }
```

Response 200: `{ "message": "OTP sent successfully" }`

**Step B — Submit OTP:**
```http
POST /form/api/v1/auth/login
Content-Type: application/json

{ "mobile": "9876543210", "otp": "123456" }
```

Same response shape as password login.

---

### Step 2.4 — Using the token

**Every subsequent request requires:**
```http
Authorization: Bearer <access_token>
```

OR if using browser cookies, add the CSRF header on state-changing requests:
```http
X-CSRF-TOKEN-ACCESS: <csrf_token_from_cookie>
```

---

### Step 2.5 — Refresh access token

Access tokens expire. Use the refresh token to get a new one:

```http
POST /form/api/v1/auth/refresh
Authorization: Bearer <refresh_token>
```

**Response 200:**
```json
{
  "data": {
    "access_token": "eyJ...new...",
    "refresh_token": "eyJ...new..."
  }
}
```

Update your stored tokens. Old tokens are invalidated in Redis.

---

### Step 2.6 — Logout

```http
POST /form/api/v1/auth/logout
Authorization: Bearer <access_token>
```

Blocklists the current token in Redis. Unsets cookies.

To revoke ALL sessions for a user:
```http
POST /form/api/v1/auth/revoke-all
Authorization: Bearer <access_token>
```

---

## 3. User Management

### Step 3.1 — Get your own profile

```http
GET /form/api/v1/user/profile
Authorization: Bearer <access_token>
```

Also works at: `GET /form/api/v1/user/status` (same response)

**Response 200:**
```json
{
  "data": {
    "user": {
      "id": "user-uuid",
      "email": "alice@hospital.org",
      "username": "alice",
      "roles": ["user"],
      "organization_id": "org-uuid",
      "is_active": true
    }
  }
}
```

---

### Step 3.2 — Change your password

```http
POST /form/api/v1/user/change-password
Authorization: Bearer <access_token>
Rate-limit: 3 per hour

{
  "current_password": "OldPass123!",
  "new_password": "NewPass456!"
}
```

Response 200: `{ "message": "Password changed successfully" }`

---

### Step 3.3 — Admin: List all users

Requires role `admin` or `superadmin`.

```http
GET /form/api/v1/user/users?page=1&page_size=20
Authorization: Bearer <access_token>
```

Response 200: Paginated list of users.

---

### Step 3.4 — Admin: Create a user

```http
POST /form/api/v1/user/users
Authorization: Bearer <access_token>

{
  "email": "bob@hospital.org",
  "password": "TempPass789!",
  "username": "bob",
  "roles": ["user"],
  "organization_id": "org-uuid"
}
```

Response 201: Created user object.

---

### Step 3.5 — Admin: Update a user

```http
PUT /form/api/v1/user/users/<user_id>
Authorization: Bearer <access_token>

{
  "roles": ["manager"],
  "is_active": true
}
```

---

### Step 3.6 — Admin: Deactivate/Delete a user

```http
DELETE /form/api/v1/user/users/<user_id>
Authorization: Bearer <access_token>
```

Soft-deletes. User cannot log in after this.

---

## 4. Building a Form

### Step 4.1 — Create a form (draft)

```http
POST /form/api/v1/forms/
Authorization: Bearer <access_token>

{
  "title": "Patient Registration",
  "description": "Collect patient demographic data",
  "slug": "patient-registration",
  "default_language": "en",
  "supported_languages": ["en", "hi"],
  "is_public": false
}
```

`slug` is auto-generated from `title` if omitted. Must be unique per org.

**Response 201:**
```json
{
  "data": { "form_id": "form-uuid" },
  "message": "Form created"
}
```

**Save:** `form_id` — you'll use it in every subsequent form call.

---

### Step 4.2 — Retrieve the form

```http
GET /form/api/v1/forms/<form_id>
Authorization: Bearer <access_token>
```

Optional query param: `?lang=hi` — returns field labels translated into Hindi (if translation exists).

**Response 200:** Full form document with `versions`, `sections`, `questions`, `status`, `editors`, `viewers`, `submitters`.

---

### Step 4.3 — List all forms in your org

```http
GET /form/api/v1/forms/?page=1&page_size=50
Authorization: Bearer <access_token>
```

Add `?is_template=true` to list templates only.

---

### Step 4.4 — Add sections to a form

A form must have at least one section before it can be published. Sections hold questions.

```http
POST /form/api/v1/forms/<form_id>/sections
Authorization: Bearer <access_token>

{
  "title": "Personal Information",
  "order": 1,
  "is_repeatable": false,
  "questions": [
    {
      "label": "Full Name",
      "field_type": "text",
      "required": true,
      "order": 1
    },
    {
      "label": "Date of Birth",
      "field_type": "date",
      "required": true,
      "order": 2
    },
    {
      "label": "Gender",
      "field_type": "radio",
      "required": true,
      "order": 3,
      "options": [
        { "label": "Male", "value": "male" },
        { "label": "Female", "value": "female" },
        { "label": "Other", "value": "other" }
      ]
    },
    {
      "label": "Upload ID",
      "field_type": "file_upload",
      "required": false,
      "order": 4
    }
  ]
}
```

Supported `field_type` values: `text`, `textarea`, `number`, `date`, `time`, `datetime`, `email`, `phone`, `radio`, `select`, `checkbox`, `boolean`, `rating`, `file_upload`, `signature`, `calculated`.

**Response 201:** `{ "data": { "section_id": "section-uuid" } }`

**Save:** `section_id` and individual `question.id` values from the returned section data.

---

### Step 4.5 — List sections

```http
GET /form/api/v1/forms/<form_id>/sections
Authorization: Bearer <access_token>
```

Returns all sections with their questions in order.

---

### Step 4.6 — Update a section

```http
PUT /form/api/v1/forms/<form_id>/sections/<section_id>
Authorization: Bearer <access_token>

{
  "title": "Patient Demographics",
  "questions": [ ... ]
}
```

---

### Step 4.7 — Delete a section

```http
DELETE /form/api/v1/forms/<form_id>/sections/<section_id>
Authorization: Bearer <access_token>
```

---

### Step 4.8 — Update form metadata

```http
PUT /form/api/v1/forms/<form_id>
Authorization: Bearer <access_token>

{
  "title": "Patient Registration v2",
  "description": "Updated description",
  "is_public": true,
  "expires_at": "2026-12-31T23:59:59Z",
  "publish_at": "2026-04-10T00:00:00Z"
}
```

All fields are optional. Only changed fields are applied.

---

### Step 4.9 — Clone a form

Creates an identical copy as a new draft. Runs asynchronously.

```http
POST /form/api/v1/forms/<form_id>/clone
Authorization: Bearer <access_token>

{
  "title": "Patient Registration — Copy",
  "slug": "patient-registration-copy"
}
```

**Response 202:**
```json
{
  "data": { "task_id": "celery-task-uuid" },
  "message": "Form cloning initiated in background"
}
```

There is no status poll endpoint for `task_id`. The cloned form appears in `GET /forms/` once complete (typically within seconds).

---

### Step 4.10 — Import a form from JSON

Use this to import a previously exported form structure:

```http
POST /form/api/v1/forms/import
Authorization: Bearer <access_token>

{
  "title": "Imported Form",
  "slug": "imported-form",
  "description": "...",
  "sections": [ ... ],
  "supported_languages": ["en"],
  "default_language": "en"
}
```

Response 201: `{ "form_id": "..." }`

---

### Step 4.11 — Delete a form

Soft-delete. The form is marked `is_deleted=true` and excluded from all queries.

```http
DELETE /form/api/v1/forms/<form_id>
Authorization: Bearer <access_token>
```

---

## 5. Publishing a Form

A form must be `published` before it accepts submissions.

### Step 5.1 — Publish the form

```http
POST /form/api/v1/forms/<form_id>/publish
Authorization: Bearer <access_token>

{
  "minor": true,
  "major": false
}
```

- `minor: true` — increments minor version (e.g., 1.0 → 1.1). Default.
- `major: true` — increments major version (e.g., 1.1 → 2.0). Use when questions change significantly.

**Response 202:**
```json
{
  "data": { "task_id": "celery-task-uuid" },
  "message": "Form publishing initiated in background"
}
```

The form status changes to `published` once the Celery task completes. Poll `GET /forms/<form_id>` and check `form.status == "published"`.

---

### Step 5.2 — Archive a published form

Stops accepting submissions. Does not delete.

```http
POST /form/api/v1/forms/<form_id>/archive
Authorization: Bearer <access_token>
```

---

### Step 5.3 — Restore an archived form

```http
POST /form/api/v1/forms/<form_id>/restore
Authorization: Bearer <access_token>
```

---

### Step 5.4 — Toggle public access

```http
POST /form/api/v1/forms/<form_id>/toggle-public
Authorization: Bearer <access_token>
```

Flips `is_public`. Only public+published forms accept anonymous submissions.

---

### Step 5.5 — Set expiry

```http
POST /form/api/v1/forms/<form_id>/expiry
Authorization: Bearer <access_token>

{
  "expires_at": "2026-12-31T23:59:59Z"
}
```

After this date, all submissions are rejected with 400.

```http
DELETE /form/api/v1/forms/<form_id>/expiry
```

Removes expiry (form accepts submissions indefinitely).

---

## 6. Setting Form Permissions

By default the form creator is the only editor. Explicitly grant access to other users.

### Step 6.1 — View current permissions

```http
GET /form/api/v1/forms/<form_id>/permissions
Authorization: Bearer <access_token>
```

**Response 200:**
```json
{
  "data": {
    "editors": ["user-uuid-1"],
    "viewers": ["user-uuid-2"],
    "submitters": ["user-uuid-3", "user-uuid-4"]
  }
}
```

---

### Step 6.2 — Update permissions

Partial update — only include the lists you want to change.

```http
POST /form/api/v1/forms/<form_id>/permissions
Authorization: Bearer <access_token>

{
  "editors": ["user-uuid-1", "user-uuid-5"],
  "viewers": ["user-uuid-2", "user-uuid-6"],
  "submitters": []
}
```

**Permission meanings:**
- `editors` — can edit form, view responses, run analytics
- `viewers` — can view form structure and responses
- `submitters` — explicitly allowed to submit (if form is not public, only submitters + editors can submit)

Response 200: `{ "message": "Permissions updated" }`

---

## 7. File Uploads

### Step 7.1 — Upload a file (for a file_upload field)

```http
POST /form/api/v1/forms/upload
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

file: <binary>
form_id: <form-uuid>
field_id: <question-uuid>
```

**Response 201:**
```json
{
  "url": "/form/api/v1/forms/<form_id>/files/<field_id>/<filename>",
  "filename": "abc123.pdf",
  "filepath": "uploads/form_id/field_id/abc123.pdf",
  "size": 102400
}
```

**Save:** the `url` — include it in the form submission `data` payload for the corresponding question.

---

### Step 7.2 — Upload a signature (for a signature field)

```http
POST /form/api/v1/forms/signatures
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "form_id": "<form-uuid>",
  "signature": "data:image/png;base64,iVBORw0KGgo..."
}
```

**Response 201:**
```json
{
  "url": "/form/api/v1/forms/<form_id>/files/signatures/<filename>",
  "signature_id": "sig_abc123.png"
}
```

---

### Step 7.3 — Retrieve a file

No auth required if `is_public=true`. JWT required for private forms.

```http
GET /form/api/v1/forms/<form_id>/files/<question_id>/<filename>
Authorization: Bearer <access_token>   # omit if form is public
```

Returns the file with appropriate `Content-Type`.

---

## 8. Submitting Responses

### Step 8.1 — Authenticated submission (form requires login)

```http
POST /form/api/v1/forms/<form_id>/responses
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "data": {
    "<section_id>": {
      "<question_id>": "Alice Smith",
      "<question_id_2>": "1990-05-15",
      "<question_id_3>": "female",
      "<question_id_4>": "/form/api/v1/forms/<form_id>/files/<field_id>/abc123.pdf"
    }
  }
}
```

**Data structure:** `data[section_id][question_id] = value`

For **repeatable sections**, the value is a list of objects:
```json
{
  "data": {
    "<repeatable_section_id>": [
      { "<question_id>": "First entry" },
      { "<question_id>": "Second entry" }
    ]
  }
}
```

**Pre-conditions that must be true before submission succeeds:**
- Form `status` must be `published`
- Form must not be expired (`expires_at` in the past → 400)
- Form must not be scheduled for future (`publish_at` in the future → 400)
- User must have `submit` permission (be in `submitters` list, or be an editor, or form is unrestricted)

**Response 201:**
```json
{
  "data": { "response_id": "response-uuid" },
  "message": "Response submitted successfully"
}
```

**Save:** `response_id`

---

### Step 8.2 — Anonymous / public submission (no login required)

Requires: form is `published`, `is_public=true`, not expired.

```http
POST /form/api/v1/forms/<form_id>/public-submit
Content-Type: application/json

{
  "data": {
    "<section_id>": {
      "<question_id>": "Anonymous User"
    }
  }
}
```

Response 201: `{ "data": { "response_id": "response-uuid" } }`

---

### Step 8.3 — Evaluate conditional logic before submission (optional)

To implement show/hide logic in your UI, evaluate conditions server-side:

```http
POST /form/api/v1/forms/conditions/evaluate
Authorization: Bearer <access_token>

{
  "form_id": "<form-uuid>",
  "conditions": [
    { "field": "<question_id>", "operator": "equals", "value": "female" },
    "responses['<question_id>'] == 'yes'"
  ],
  "responses": {
    "<question_id>": "female",
    "<question_id_2>": "yes"
  }
}
```

Response 200: `{ "data": { "results": { "<condition_key>": true/false, ... } } }`

---

## 9. Viewing and Querying Responses

### Step 9.1 — List responses for a form (paginated)

Requires `view_responses` permission (be an editor or viewer).

```http
GET /form/api/v1/forms/<form_id>/responses?page=1&page_size=20
Authorization: Bearer <access_token>
```

Response 200: Paginated list with `items[]` containing full response data.

---

### Step 9.2 — View submission history for a question value

Look up prior submissions where a specific question had a specific value (useful for longitudinal patient data).

```http
GET /form/api/v1/forms/<form_id>/history?question_id=<question_id>&primary_value=Alice+Smith
Authorization: Bearer <access_token>
```

Response 200: List of `{ "_id": "...", "submitted_at": "..." }` ordered by time.

---

### Step 9.3 — View public form HTML (browser rendering)

```http
GET /form/api/v1/view/<form_id>
```

Returns rendered HTML. No auth required. Only works for `is_public=true` forms.

---

### Step 9.4 — Cross-form queries (advanced)

Requires `manage_access` permission.

**Fetch responses across multiple forms:**
```http
GET /form/api/v1/forms/responses/cross-form?form_ids=<id1>,<id2>&page=1
Authorization: Bearer <access_token>
```

**Set access policy for cross-form query:**
```http
POST /form/api/v1/forms/<form_id>/access-policy
Authorization: Bearer <access_token>

{
  "allowed_forms": ["<form_id_2>", "<form_id_3>"],
  "policy": "read"
}
```

**View access-control config:**
```http
GET /form/api/v1/forms/<form_id>/access-control
Authorization: Bearer <access_token>
```

---

## 10. Per-Form Analytics

All analytics endpoints require the caller to have `view` permission on the form.

### Step 10.1 — Summary (totals + status breakdown)

```http
GET /form/api/v1/forms/<form_id>/analytics/summary
Authorization: Bearer <access_token>
```

**Response 200:**
```json
{
  "data": {
    "total_responses": 142,
    "status_breakdown": { "submitted": 130, "draft": 12 },
    "last_submitted_at": "2026-04-05T14:32:11Z"
  }
}
```

---

### Step 10.2 — Timeline (daily submission counts)

```http
GET /form/api/v1/forms/<form_id>/analytics/timeline?days=30
Authorization: Bearer <access_token>
```

**Response 200:**
```json
{
  "data": {
    "period_days": 30,
    "timeline": [
      { "date": "2026-03-06", "count": 5 },
      { "date": "2026-03-07", "count": 11 }
    ]
  }
}
```

---

### Step 10.3 — Distribution (answer counts for choice fields)

```http
GET /form/api/v1/forms/<form_id>/analytics/distribution
Authorization: Bearer <access_token>
```

Aggregates answer counts for `radio`, `select`, `checkbox`, `rating`, `boolean` fields.

**Response 200:**
```json
{
  "data": {
    "distribution": [
      {
        "question_id": "q-uuid",
        "label": "Gender",
        "type": "radio",
        "counts": { "male": 72, "female": 65, "other": 5 }
      }
    ]
  }
}
```

---

### Step 10.4 — Full analytics (combined)

```http
GET /form/api/v1/forms/<form_id>/analytics
Authorization: Bearer <access_token>
```

**Response 200:**
```json
{
  "data": {
    "totalSubmissions": 142,
    "completionRate": 0.85,
    "trends": [
      { "date": "2026-03-31", "value": 8 },
      { "date": "2026-04-01", "value": 15 }
    ],
    "fieldDistributions": {
      "Gender": [
        { "label": "male", "count": 72, "percentage": 50.7 }
      ]
    }
  }
}
```

> **Note:** `completionRate` is currently hardcoded to `0.85`. Do not use it for reporting.

---

## 11. Exporting Data

### Step 11.1 — Export responses as CSV (streaming)

```http
GET /form/api/v1/forms/<form_id>/export/csv
Authorization: Bearer <access_token>
```

Returns a streaming `text/csv` response. No pagination — downloads all responses.

---

### Step 11.2 — Export responses as JSON (streaming)

```http
GET /form/api/v1/forms/<form_id>/export/json
Authorization: Bearer <access_token>
```

Returns a streaming `application/json` array.

---

### Step 11.3 — Bulk async export (large datasets)

For very large response sets, trigger an async export:

```http
POST /form/api/v1/forms/export/bulk
Authorization: Bearer <access_token>

{
  "form_ids": ["<form_id_1>", "<form_id_2>"],
  "format": "csv"
}
```

**Response 202:** `{ "data": { "job_id": "job-uuid" } }`

The export file is generated asynchronously. Poll `GET /forms/export/bulk/<job_id>/status` to check completion, then download from the returned URL.

---

## 12. Summarization and AI

### Step 12.1 — Check AI service health

```http
GET /form/api/v1/ai/health
```

No auth required.

**Response 200:** `{ "status": "healthy", "provider": "ollama" }` (or `openai`, `local`)

---

### Step 12.2 — Summarize form responses (streaming SSE)

```http
POST /form/api/v1/forms/<form_id>/summarize
Authorization: Bearer <access_token>
Accept: text/event-stream

{
  "response_ids": ["resp-uuid-1", "resp-uuid-2"],
  "prompt": "Summarize key health concerns from these submissions"
}
```

Returns Server-Sent Events (SSE). Each event is a token from the LLM:
```
data: {"token": "The"}
data: {"token": " key"}
data: {"token": " health"}
...
data: {"done": true}
```

Use `EventSource` in the browser or a streaming HTTP client.

---

### Step 12.3 — NLP semantic search

```http
POST /form/api/v1/ai/search/semantic-search
Authorization: Bearer <access_token>
Accept: text/event-stream

{
  "query": "patients with diabetes and hypertension",
  "form_ids": ["<form_id>"],
  "top_k": 10
}
```

Returns SSE stream of matching responses with relevance scores.

---

### Step 12.4 — Search history

```http
GET /form/api/v1/ai/search/search-history
Authorization: Bearer <access_token>
```

Returns previous search queries made by the current user.

---

## 13. Translations

### Step 13.1 — List supported languages

```http
GET /form/api/v1/forms/translations/languages
Authorization: Bearer <access_token>
```

---

### Step 13.2 — List translation jobs for a form

```http
GET /form/api/v1/forms/translations/jobs?form_id=<form_id>
Authorization: Bearer <access_token>
```

---

### Step 13.3 — Create a translation job

Triggers AI translation for a specific language. Runs via Celery.

```http
POST /form/api/v1/forms/translations/jobs
Authorization: Bearer <access_token>

{
  "form_id": "<form-uuid>",
  "target_language": "hi"
}
```

**Response 202:** `{ "data": { "job_id": "job-uuid" }, "message": "Translation initiated" }`

---

### Step 13.4 — Check translation job status

```http
GET /form/api/v1/forms/translations/jobs/<job_id>
Authorization: Bearer <access_token>
```

**Response 200:** `{ "status": "completed" | "pending" | "failed", "progress": 85 }`

Wait for `status == "completed"` before fetching translated content.

---

### Step 13.5 — Fetch translated content

```http
GET /form/api/v1/forms/translations/jobs/<job_id>/content
Authorization: Bearer <access_token>
```

Returns translated labels/options for all questions.

---

### Step 13.6 — Preview a translation

```http
POST /form/api/v1/forms/translations/preview
Authorization: Bearer <access_token>

{
  "form_id": "<form-uuid>",
  "language": "hi",
  "text": "Full Name"
}
```

---

### Step 13.7 — Cancel a translation job

```http
POST /form/api/v1/forms/translations/jobs/<job_id>/cancel
Authorization: Bearer <access_token>
```

---

### Step 13.8 — Fetch form with translation applied

Add `?lang=hi` to any `GET /forms/<form_id>` call:

```http
GET /form/api/v1/forms/<form_id>?lang=hi
Authorization: Bearer <access_token>
```

Field labels and options are returned in Hindi if a completed translation exists.

---

## 14. Dashboard Management

### Step 14.1 — Create a dashboard

```http
POST /form/api/v1/dashboards/
Authorization: Bearer <access_token>

{
  "name": "Patient Intake Overview",
  "slug": "patient-intake",
  "description": "Key metrics for patient registration",
  "widgets": [
    {
      "widget_type": "response_count",
      "title": "Total Submissions",
      "form_id": "<form_id>",
      "position": { "x": 0, "y": 0 },
      "size": { "w": 2, "h": 1 }
    },
    {
      "widget_type": "field_distribution",
      "title": "Gender Breakdown",
      "form_id": "<form_id>",
      "question_id": "<question_id>",
      "position": { "x": 2, "y": 0 },
      "size": { "w": 2, "h": 2 }
    }
  ]
}
```

**Response 201:** `{ "data": { "dashboard_id": "dash-uuid", "slug": "patient-intake" } }`

---

### Step 14.2 — Get a dashboard (with live widget data)

```http
GET /form/api/v1/dashboards/<slug>
Authorization: Bearer <access_token>
```

Widget data is resolved live from MongoDB aggregation on each call.

**Response 200:** Full dashboard with `widgets[]` each containing a `data` field with the latest aggregated value.

---

### Step 14.3 — Update a dashboard

```http
PUT /form/api/v1/dashboards/<dashboard_id>
Authorization: Bearer <access_token>

{
  "name": "Updated Dashboard Name",
  "widgets": [ ... ]
}
```

---

### Step 14.4 — Delete a dashboard

```http
DELETE /form/api/v1/dashboards/<dashboard_id>
Authorization: Bearer <access_token>
```

---

### Step 14.5 — Get/update personal dashboard settings

```http
GET /form/api/v1/dashboard-settings/settings
Authorization: Bearer <access_token>
```

```http
PUT /form/api/v1/dashboard-settings/settings
Authorization: Bearer <access_token>

{
  "theme": "dark",
  "language": "en",
  "timezone": "Asia/Kolkata",
  "layout_config": {}
}
```

---

### Step 14.6 — Update widget positions (drag-and-drop)

```http
PUT /form/api/v1/dashboard-settings/widgets/positions
Authorization: Bearer <access_token>

{
  "positions": {
    "<widget_id_1>": { "x": 0, "y": 0 },
    "<widget_id_2>": { "x": 2, "y": 0 }
  }
}
```

---

### Step 14.7 — Update layout configuration

```http
PUT /form/api/v1/dashboard-settings/layout
Authorization: Bearer <access_token>

{
  "columns": 4,
  "rowHeight": 120,
  "margin": [15, 15],
  "compactType": "vertical"
}
```

---

### Step 14.8 — Reset settings to defaults

```http
POST /form/api/v1/dashboard-settings/reset
Authorization: Bearer <access_token>
```

---

## 15. Workflows

Approval workflows are multi-step processes triggered by a form submission.

### Step 15.1 — Create a workflow

```http
POST /form/api/v1/workflows/
Authorization: Bearer <access_token>

{
  "name": "Patient Registration Approval",
  "description": "Two-step approval for new patient records",
  "trigger_form_id": "<form_id>",
  "status": "active",
  "is_template": false,
  "steps": [
    {
      "step_name": "Nurse Review",
      "order": 1,
      "concurrency_type": "serial",
      "approvers": ["<user_id_nurse>"],
      "required_approvals": 1,
      "timeout_hours": 24,
      "escalation_action": "notify_admin"
    },
    {
      "step_name": "Doctor Sign-off",
      "order": 2,
      "concurrency_type": "serial",
      "approvers": ["<user_id_doctor>"],
      "required_approvals": 1,
      "timeout_hours": 48,
      "escalation_action": "notify_admin"
    }
  ]
}
```

**Response 201:** `{ "data": { "id": "workflow-uuid" } }`

---

### Step 15.2 — List workflows

```http
GET /form/api/v1/workflows/?trigger_form_id=<form_id>
Authorization: Bearer <access_token>
```

---

### Step 15.3 — Get a workflow

```http
GET /form/api/v1/workflows/<workflow_id>
Authorization: Bearer <access_token>
```

---

### Step 15.4 — Check what workflows apply to a submission

After submitting a response, check which workflows it triggers:

```http
GET /form/api/v1/forms/<form_id>/next-action?response_id=<response_id>
Authorization: Bearer <access_token>
```

**Response 200:**
```json
{
  "form_id": "...",
  "response_id": "...",
  "triggered_workflows": [
    {
      "workflow_id": "wf-uuid",
      "workflow_name": "Patient Registration Approval",
      "first_step": "Nurse Review"
    }
  ]
}
```

Without `?response_id`, returns all active workflows attached to that form.

---

### Step 15.5 — Update a workflow

```http
PUT /form/api/v1/workflows/<workflow_id>
Authorization: Bearer <access_token>

{
  "status": "paused",
  "steps": [ ... ]
}
```

---

### Step 15.6 — Delete (soft) a workflow

```http
DELETE /form/api/v1/workflows/<workflow_id>
Authorization: Bearer <access_token>
```

---

## 16. Webhooks

Webhooks fire an HTTP POST to a configured URL when a form response is submitted.

### Step 16.1 — Deliver a webhook (test)

```http
POST /form/api/v1/webhooks/deliver
Authorization: Bearer <access_token>    # requires manager role

{
  "url": "https://my-service.internal/form-hook",
  "payload": { "event": "response.submitted", "form_id": "...", "response_id": "..." },
  "headers": { "X-Secret": "my-shared-secret" }
}
```

---

### Step 16.2 — Check webhook delivery status

```http
GET /form/api/v1/webhooks/<webhook_id>/status
Authorization: Bearer <access_token>
```

---

### Step 16.3 — Retry a failed webhook

```http
POST /form/api/v1/webhooks/<webhook_id>/retry
Authorization: Bearer <access_token>
```

---

## 17. Advanced Queries

### Step 17.1 — System analytics summary (manager and above)

```http
GET /form/api/v1/analytics/dashboard
Authorization: Bearer <access_token>
```

Returns cross-form metrics: total forms, responses, active users, recent submissions.

---

### Step 17.2 — Admin analytics summary

Requires `admin` or `superadmin` role.

```http
GET /form/api/v1/analytics/summary
Authorization: Bearer <access_token>
```

---

### Step 17.3 — SMS operations (manager role)

**Send a single SMS:**
```http
POST /form/api/v1/sms/single
Authorization: Bearer <access_token>
Rate-limit: 10 per minute

{
  "mobile": "9876543210",
  "message": "Your form submission has been received."
}
```

**Send OTP via SMS:**
```http
POST /form/api/v1/sms/otp
Authorization: Bearer <access_token>
Rate-limit: 5 per minute

{
  "mobile": "9876543210"
}
```

**Check SMS service health:**
```http
GET /form/api/v1/sms/health
Authorization: Bearer <access_token>
```

---

## 18. System-Level Analytics

### Step 18.1 — Event bus health (superadmin only)

```http
GET /form/api/v1/system/event-health
Authorization: Bearer <access_token>
```

Returns consumer lag, DLQ sizes, stream lengths.

---

### Step 18.2 — OLAP analytics trends (admin or superadmin)

```http
GET /form/api/v1/system/analytics-trends/<org_id>
Authorization: Bearer <access_token>
```

Returns submission trends from the OLAP engine (DuckDB or ClickHouse).

---

## 19. Admin Operations

### Step 19.1 — Get system settings (admin or superadmin)

```http
GET /form/api/v1/admin/system-settings/
Authorization: Bearer <access_token>
```

---

### Step 19.2 — Update system settings (admin or superadmin)

```http
PUT /form/api/v1/admin/system-settings/
Authorization: Bearer <access_token>

{
  "max_upload_size_mb": 10,
  "allowed_file_types": ["pdf", "jpg", "png"],
  "session_timeout_minutes": 60
}
```

---

### Step 19.3 — View environment configuration (superadmin only)

```http
GET /form/api/v1/admin/env-config/
Authorization: Bearer <access_token>
```

Returns all `.env` key/value pairs. **Sensitive — superadmin only.**

---

### Step 19.4 — Update environment configuration (superadmin only)

```http
PUT /form/api/v1/admin/env-config/
Authorization: Bearer <access_token>

{
  "AI_PROVIDER": "openai",
  "OLAP_ENGINE": "clickhouse"
}
```

Changes are written to `.env` via `set_key()`. **Restart required for most variables to take effect.**

---

## 20. Complete Lifecycle Cheatsheet

The correct order for the most common workflow — building and using a form end-to-end:

```
 1. POST   /auth/register                    # Create account (once)
 2. POST   /auth/login                       # Get access_token + refresh_token
 3. GET    /user/profile                     # Verify identity and org context
 4. POST   /forms/                           # Create form (draft)
 5. POST   /forms/<id>/sections              # Add sections + questions
 6. POST   /forms/<id>/permissions           # Grant access to other users (if needed)
 7. POST   /forms/upload                     # Pre-upload any default attachments (optional)
 8. POST   /forms/<id>/publish               # Initiate publish (202 — async)
             └── poll GET /forms/<id>        # Wait for status == "published"
 9. POST   /forms/<id>/responses             # Submit authenticated response
    OR
    POST   /forms/<id>/public-submit         # Submit anonymous response (if is_public)
10. GET    /forms/<id>/responses             # View submitted responses
11. GET    /forms/<id>/analytics/summary     # Get totals and status breakdown
12. GET    /forms/<id>/export/csv            # Download all responses
13. POST   /dashboards/                      # Create dashboard with widgets
14. GET    /dashboards/<slug>                # View live dashboard data
15. POST   /auth/logout                      # End session
```

**Token refresh (do this automatically when you receive 401):**
```
POST /auth/refresh  →  update access_token  →  retry original request
```

**Error handling quick reference:**

| HTTP | Meaning | Action |
|------|---------|--------|
| 400 | Bad request / validation error | Fix request body |
| 401 | Token missing or expired | Refresh token → retry |
| 403 | Insufficient permissions | Check role or form ACL |
| 404 | Resource not found | Verify ID is correct and in your org |
| 429 | Rate limited | Wait, then retry |
| 202 | Accepted (async) | Poll for completion |
| 500 | Server error | Check logs, report if persistent |
