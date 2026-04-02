# Integration Contract Guide — RIDP Form Platform

## 1. Purpose

This document is the primary reference for frontend developers, QA engineers, and automation teams integrating with the RIDP Form Platform backend. It defines every API contract, authentication flow, request format, response format, and behavioral invariant needed to build reliable integrations.

---

## 2. Base URL and Versioning

All API requests use the following base:

```
https://<host>/form/api/v1/
```

In development:
```
http://localhost:5000/form/api/v1/
```

Swagger UI (interactive documentation):
```
http://localhost:5000/form/docs
```

OpenAPI spec (machine-readable):
```
http://localhost:5000/form/apispec_1.json
```

---

## 3. Authentication

### 3.1 Obtaining Tokens

**Password Login:**
```http
POST /form/api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secret123"
}
```

**OTP Login (step 1 — request OTP):**
```http
POST /form/api/v1/auth/request-otp
Content-Type: application/json

{ "mobile": "9876543210" }
```

**OTP Login (step 2 — submit OTP):**
```http
POST /form/api/v1/auth/login
Content-Type: application/json

{ "mobile": "9876543210", "otp": "123456" }
```

**Login Response:**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "user": { "id": "...", "email": "...", "roles": ["user"] }
  },
  "message": "Login successful"
}
```

Cookies are also set automatically by the server (`access_token`, `refresh_token` HttpOnly cookies).

### 3.2 Using Tokens

**Option A: Bearer header (recommended for programmatic clients):**
```http
Authorization: Bearer <access_token>
```

**Option B: Cookie (recommended for browser clients):**
Cookies are set automatically on login. For state-changing requests, include the CSRF token:
```http
X-CSRF-TOKEN-ACCESS: <csrf_token_from_cookie>
```

### 3.3 Refreshing Tokens

```http
POST /form/api/v1/auth/refresh
Authorization: Bearer <refresh_token>
```

OR send the refresh cookie with:
```http
X-CSRF-TOKEN-REFRESH: <refresh_csrf_token>
```

Response is identical to login response (new access + refresh tokens).

### 3.4 Logout

```http
POST /form/api/v1/auth/logout
Authorization: Bearer <access_token>
```

This invalidates the current access token JTI. Cookies are also cleared.

### 3.5 Revoke All Sessions

```http
POST /form/api/v1/auth/revoke-all
Authorization: Bearer <access_token>
```

Invalidates all active sessions for the authenticated user.

---

## 4. User API

### 4.1 Get Own Profile

```http
GET /form/api/v1/user/profile
Authorization: Bearer <access_token>
```

Also available at: `GET /form/api/v1/user/status`

Response:
```json
{
  "success": true,
  "data": {
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "username": "john_doe",
      "roles": ["user"],
      "organization_id": "org-uuid",
      "is_active": true
    }
  }
}
```

### 4.2 Change Password

```http
POST /form/api/v1/user/change-password
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "current_password": "old_secret",
  "new_password": "new_secret123"
}
```

Rate limited: 3 per hour.

### 4.3 Admin: List Users

```http
GET /form/api/v1/user/users?page=1&page_size=20
Authorization: Bearer <admin_token>
```

Requires role: `admin` or `superadmin`.

### 4.4 Admin: Create User

```http
POST /form/api/v1/user/users
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "email": "newuser@example.com",
  "username": "new_user",
  "password": "pass123",
  "roles": ["user"]
}
```

### 4.5 Admin: Update User

```http
PUT /form/api/v1/user/users/<user_id>
Authorization: Bearer <admin_token>
Content-Type: application/json

{ "roles": ["admin"] }
```

### 4.6 Admin: Update Roles

```http
PUT /form/api/v1/user/users/<user_id>/roles
Authorization: Bearer <admin_token>
Content-Type: application/json

{ "roles": ["admin", "manager"] }
```

### 4.7 Admin: Lock / Unlock Account

```http
POST /form/api/v1/user/users/<user_id>/lock
POST /form/api/v1/user/users/<user_id>/unlock
Authorization: Bearer <admin_token>
```

### 4.8 Admin: Get Lock Status

```http
GET /form/api/v1/user/security/lock-status/<user_id>
Authorization: Bearer <admin_token>
```

Response:
```json
{
  "success": true,
  "data": {
    "is_locked": true,
    "lock_until": "2026-04-02T12:00:00Z",
    "failed_login_attempts": 5
  }
}
```

---

## 5. Forms API

### 5.1 Create Form

```http
POST /form/api/v1/forms/
Authorization: Bearer <token>
Content-Type: application/json

{
  "title": "Patient Intake Form",
  "description": "Collect patient information",
  "slug": "patient-intake",
  "default_language": "en",
  "supported_languages": ["en", "hi"]
}
```

Response:
```json
{
  "success": true,
  "data": { "form_id": "uuid" },
  "message": "Form created"
}
```

If `slug` is omitted, it is auto-generated from the `title`. Status code: 201.

### 5.2 List Forms

```http
GET /form/api/v1/forms/?page=1&page_size=50
Authorization: Bearer <token>
```

Optional query param: `is_template=true` to list templates only.

### 5.3 Get Form

```http
GET /form/api/v1/forms/<form_id>
Authorization: Bearer <token>
```

Optional: `?lang=hi` to get the form with translations applied.

Returns the full form document including sections, questions, and options.

### 5.4 Update Form

```http
PUT /form/api/v1/forms/<form_id>
Authorization: Bearer <token>
Content-Type: application/json

{ "title": "Updated Title", "description": "Updated desc" }
```

Requires `edit` permission on the form.

### 5.5 Delete Form (Soft Delete)

```http
DELETE /form/api/v1/forms/<form_id>
Authorization: Bearer <token>
```

Requires `delete_form` permission. The form is soft-deleted (excluded from queries) but not removed from MongoDB.

### 5.6 Publish Form

```http
POST /form/api/v1/forms/<form_id>/publish
Authorization: Bearer <token>
Content-Type: application/json

{ "major": false, "minor": true }
```

Returns 202 immediately. Publishing happens asynchronously via Celery.

Response:
```json
{
  "success": true,
  "data": { "task_id": "celery-task-uuid" },
  "message": "Form publishing initiated in background"
}
```

### 5.7 Clone Form

```http
POST /form/api/v1/forms/<form_id>/clone
Authorization: Bearer <token>
Content-Type: application/json

{ "title": "Copy of Patient Intake", "slug": "patient-intake-copy" }
```

Returns 202. Cloning happens asynchronously via Celery.

### 5.8 Check Slug Availability

```http
GET /form/api/v1/forms/slug-available?slug=my-form-slug
Authorization: Bearer <token>
```

Response: `{ "data": { "available": true } }`

### 5.9 Import Form

```http
POST /form/api/v1/forms/import
Authorization: Bearer <token>
Content-Type: application/json

{
  "title": "Imported Form",
  "slug": "imported-form",
  "sections": [ ... ]
}
```

### 5.10 Templates

```http
GET /form/api/v1/forms/templates
GET /form/api/v1/forms/templates/<template_id>
Authorization: Bearer <token>
```

Also accessible via alias prefix `/form/api/v1/templates`.

---

## 6. Sections API

All section routes are nested under forms:

```http
POST   /form/api/v1/forms/<form_id>/sections
GET    /form/api/v1/forms/<form_id>/sections
PUT    /form/api/v1/forms/<form_id>/sections/<section_id>
DELETE /form/api/v1/forms/<form_id>/sections/<section_id>
PUT    /form/api/v1/forms/<form_id>/sections/reorder
```

**Reorder payload:**
```json
{ "section_ids": ["id1", "id2", "id3"] }
```

---

## 7. Form Translations (Manual)

Set translation strings for a specific language:

```http
POST /form/api/v1/forms/<form_id>/translations
Authorization: Bearer <token>
Content-Type: application/json

{
  "lang_code": "hi",
  "translations": {
    "title": "मरीज फॉर्म",
    "questions": {
      "q_name": "नाम"
    }
  }
}
```

Requires `edit` permission on the form.

---

## 8. Form Responses API

### 8.1 Submit Response (Authenticated)

```http
POST /form/api/v1/forms/<form_id>/responses
Authorization: Bearer <token>
Content-Type: application/json

{
  "data": {
    "patient_name": "John Doe",
    "age": 35,
    "symptoms": ["fever", "cough"]
  }
}
```

Pre-conditions checked:
- Form exists and belongs to user's org
- User has `submit` permission on form
- Form is not expired (`expires_at`)
- Form is not scheduled in future (`publish_at`)

Response (201):
```json
{
  "success": true,
  "data": { "response_id": "uuid" },
  "message": "Response submitted successfully"
}
```

### 8.2 Submit Response (Anonymous / Public)

```http
POST /form/api/v1/forms/<form_id>/public-submit
Content-Type: application/json

{
  "data": { "field": "value" }
}
```

No authentication required. Form must have `is_public = true` and `status = "published"`. `submitted_by` is set to `"anonymous"`.

### 8.3 List Responses

```http
GET /form/api/v1/forms/<form_id>/responses?page=1&page_size=20
Authorization: Bearer <token>
```

Requires `view_responses` permission.

### 8.4 Count Responses

```http
GET /form/api/v1/forms/<form_id>/responses/count
Authorization: Bearer <token>
```

### 8.5 Last Response

```http
GET /form/api/v1/forms/<form_id>/responses/last
Authorization: Bearer <token>
```

### 8.6 Check Duplicate Submission

```http
POST /form/api/v1/forms/<form_id>/check-duplicate
Authorization: Bearer <token>
Content-Type: application/json

{ "data": { "patient_name": "John Doe" } }
```

Response: `{ "data": { "duplicate": false } }`

### 8.7 Delete All Responses (Admin, Irreversible)

```http
DELETE /form/api/v1/forms/<form_id>/responses
Authorization: Bearer <admin_token>
```

Permanently (hard) deletes all FormResponse documents for this form. This is irreversible.

---

## 9. Form Admin Operations

### 9.1 Archive / Restore

```http
PATCH /form/api/v1/forms/<form_id>/archive
PATCH /form/api/v1/forms/<form_id>/restore
Authorization: Bearer <admin_token>
```

Requires role: `admin` or `superadmin`.

### 9.2 Toggle Public Access

```http
PATCH /form/api/v1/forms/<form_id>/toggle-public
Authorization: Bearer <admin_token>
```

Toggles `is_public`. Returns new state: `{ "data": { "is_public": true } }`.

### 9.3 Share Form (Grant Permissions)

```http
POST /form/api/v1/forms/<form_id>/share
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "editors": ["user-id-1"],
  "viewers": ["user-id-2"],
  "submitters": ["user-id-3"]
}
```

### 9.4 Set Form Expiration

```http
PATCH /form/api/v1/forms/<form_id>/expire
Authorization: Bearer <admin_token>
Content-Type: application/json

{ "expires_at": "2026-12-31T23:59:59Z" }
```

### 9.5 List Expired Forms

```http
GET /form/api/v1/forms/expired
Authorization: Bearer <admin_token>
```

---

## 10. Export API

### 10.1 Streaming CSV Export

```http
GET /form/api/v1/forms/<form_id>/export/csv
Authorization: Bearer <token>
```

Returns a streaming `text/csv` file. Column headers are derived from the form's active version snapshot. Requires `view_responses` permission.

Optional: `?version_id=<id>` to export against a specific version's schema.

Response headers:
```
Content-Disposition: attachment;filename=form_<id>_<timestamp>.csv
Content-Type: text/csv
X-Content-Type-Options: nosniff
```

### 10.2 Streaming JSON Export

```http
GET /form/api/v1/forms/<form_id>/export/json
Authorization: Bearer <token>
```

Returns streaming `application/json`:
```json
{
  "form_metadata": { "id": "...", "title": "...", ... },
  "responses": [ ... ]
}
```

### 10.3 Bulk Export (Async)

**Start bulk export:**
```http
POST /form/api/v1/forms/export/bulk
Authorization: Bearer <token>
Content-Type: application/json

{ "form_ids": ["uuid1", "uuid2"] }
```

Response (202):
```json
{
  "success": true,
  "data": { "job_id": "uuid", "status": "pending" },
  "message": "Bulk export job accepted"
}
```

**Check status:**
```http
GET /form/api/v1/forms/export/bulk/<job_id>
Authorization: Bearer <token>
```

**Download completed export:**
```http
GET /form/api/v1/forms/export/bulk/<job_id>/download
Authorization: Bearer <token>
```

Returns a ZIP file when status is `"completed"`.

---

## 11. Submission History

```http
GET /form/api/v1/forms/<form_id>/history?question_id=<id>&primary_value=<value>
Authorization: Bearer <token>
```

Returns chronological list of submissions where `data[question_id] == primary_value`. Useful for tracking record history across submissions (e.g., patient ID lookup).

---

## 12. Workflow Integration

```http
GET /form/api/v1/forms/<form_id>/next-action
Authorization: Bearer <token>
```

Optional: `?response_id=<id>` to check workflows triggered by a specific response.

Response without response_id (list available workflows):
```json
{
  "form_id": "uuid",
  "workflows": [
    { "id": "wf-uuid", "name": "Approval Flow", "steps_count": 3 }
  ],
  "count": 1
}
```

---

## 13. Access Control API

### 13.1 Get Current User's Permissions

```http
GET /form/api/v1/forms/<form_id>/access-control
Authorization: Bearer <token>
```

Response:
```json
{
  "form_id": "uuid",
  "title": "Patient Intake",
  "current_user": { "id": "...", "roles": ["user"] },
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
  }
}
```

### 13.2 Update Access Policy

```http
POST /form/api/v1/forms/<form_id>/access-policy
PUT  /form/api/v1/forms/<form_id>/access-policy
Authorization: Bearer <token>
Content-Type: application/json

{
  "form_visibility": "private",
  "response_visibility": "own_only",
  "allowed_departments": ["radiology"],
  "can_view_responses": true,
  "can_edit_design": false
}
```

Requires `manage_access` permission.

---

## 14. Advanced Response Queries

These are registered on the `advanced_responses_bp` at `/form/api/v1/forms`:

### 14.1 Cross-Form Data Lookup

```http
GET /form/api/v1/forms/fetch/external?form_id=<id>&question_id=<id>&value=<val>
Authorization: Bearer <token>
```

Finds responses in another form where `question_id == value`.

### 14.2 Same-Form Data Lookup

```http
GET /form/api/v1/forms/<form_id>/fetch/same?question_id=<id>&value=<val>
Authorization: Bearer <token>
```

### 14.3 Specific Questions Only

```http
GET /form/api/v1/forms/<form_id>/responses/questions?question_ids=q1,q2,q3
Authorization: Bearer <token>
```

Returns only the specified question values from all responses.

### 14.4 Response Meta

```http
GET /form/api/v1/forms/<form_id>/responses/meta
Authorization: Bearer <token>
```

Response:
```json
{
  "form_id": "uuid",
  "total_responses": 100,
  "draft_count": 5,
  "submitted_count": 95,
  "last_submission": "2026-04-01T10:30:00Z"
}
```

---

## 15. Summarization API

### 15.1 Generate Summary

```http
POST /form/api/v1/forms/<form_id>/summarize
Authorization: Bearer <token>
Content-Type: application/json

{ "response_ids": ["id1", "id2"] }
```

`response_ids` is optional — omit to summarize all responses. Requires at least 2 responses.

Response:
```json
{
  "success": true,
  "summary": "The majority of respondents reported...",
  "form_id": "uuid"
}
```

### 15.2 Streaming Summary (SSE)

```http
POST /form/api/v1/forms/<form_id>/summarize-stream
Authorization: Bearer <token>
Content-Type: application/json

{ "response_ids": [] }
```

Response: `Content-Type: text/event-stream`

```
data: {"content": "The majority of...", "done": true}
```

Client must handle SSE protocol.

---

## 16. Translation API

The translation blueprint is registered at `/form/api/v1/forms/translations`.

### 16.1 Get Translations

```http
GET /form/api/v1/forms/translations?form_id=<id>&language=hi
Authorization: Bearer <token>
```

Omit `language` to get all languages.

### 16.2 Save Translations

```http
POST /form/api/v1/forms/translations
Authorization: Bearer <token>
Content-Type: application/json

{
  "form_id": "uuid",
  "language": "hi",
  "translations": { "title": "मरीज फॉर्म", "q_name": "नाम" }
}
```

Requires `edit` permission on the form.

### 16.3 Supported Languages List

```http
GET /form/api/v1/forms/translations/languages
Authorization: Bearer <token>
```

Returns 12 supported languages with code, name, and native_name.

### 16.4 Translation Preview

```http
POST /form/api/v1/forms/translations/preview
Authorization: Bearer <token>
Content-Type: application/json

{
  "text": "Patient Name",
  "source_language": "en",
  "target_language": "hi"
}
```

### 16.5 Translation Jobs

**Start a job (AI batch translation):**
```http
POST /form/api/v1/forms/translations/jobs
Authorization: Bearer <token>
Content-Type: application/json

{
  "form_id": "uuid",
  "source_language": "en",
  "target_languages": ["hi", "fr", "de"],
  "total_fields": 50
}
```

Note: Jobs run in Python threads (not Celery). No retry on failure.

**List jobs for a form:**
```http
GET /form/api/v1/forms/translations/jobs?form_id=<id>
Authorization: Bearer <token>
```

**Get job status:**
```http
GET /form/api/v1/forms/translations/jobs/<job_id>
Authorization: Bearer <token>
```

Job status values: `pending` → `inProgress` → `completed` | `failed` | `cancelled`

**Get translated content (completed jobs only):**
```http
GET /form/api/v1/forms/translations/jobs/<job_id>/content
Authorization: Bearer <token>
```

**Cancel a job:**
```http
PATCH /form/api/v1/forms/translations/jobs/<job_id>/cancel
Authorization: Bearer <token>
```

**Delete a job:**
```http
DELETE /form/api/v1/forms/translations/jobs/<job_id>
Authorization: Bearer <token>
```

---

## 17. AI / NLP Search API

### 17.1 AI Service Health (Public)

```http
GET /form/api/v1/ai/health
```

No authentication required.

Response:
```json
{
  "status": "healthy",
  "ollama": {
    "status": "healthy",
    "available": true,
    "models": ["llama3.2", "nomic-embed-text"],
    "default_model": "llama3.2",
    "embedding_model": "nomic-embed-text",
    "latency_ms": 45
  },
  "timestamp": "2026-04-02T10:00:00Z"
}
```

### 17.2 NLP Search

```http
GET /form/api/v1/ai/search/nlp-search?q=patient+fever
Authorization: Bearer <token>
```

### 17.3 Semantic Search

```http
POST /form/api/v1/ai/search/semantic-search
Authorization: Bearer <token>
Content-Type: application/json

{ "query": "patient with fever", "form_id": "uuid" }
```

Results are cached in Redis for 1 hour.

### 17.4 Semantic Search (Streaming)

```http
POST /form/api/v1/ai/search/semantic-search/stream
Authorization: Bearer <token>
Content-Type: application/json

{ "query": "fever symptoms" }
```

Response: SSE stream.

### 17.5 Search Stats / Suggestions / History

```http
GET /form/api/v1/ai/search/search-stats
GET /form/api/v1/ai/search/query-suggestions
GET /form/api/v1/ai/search/popular-queries
GET /form/api/v1/ai/search/search-history
DELETE /form/api/v1/ai/search/search-history
Authorization: Bearer <token>
```

---

## 18. Dashboard API

### 18.1 Create Dashboard

```http
POST /form/api/v1/dashboards/
Authorization: Bearer <token>
Content-Type: application/json

{
  "title": "Patient Overview",
  "slug": "patient-overview",
  "widgets": [
    {
      "title": "Total Submissions",
      "type": "counter",
      "form_id": "uuid"
    }
  ]
}
```

Requires permission: `dashboard.create`.

### 18.2 Get Dashboard (with live widget data)

```http
GET /form/api/v1/dashboards/<slug>
Authorization: Bearer <token>
```

Response includes resolved widget data using MongoDB aggregation. Widget types: `chart_bar`, `chart_pie`, `chart_line`, `counter`, `kpi`, `table`, `list_view`.

### 18.3 Update Dashboard

```http
PUT /form/api/v1/dashboards/<dashboard_id>
Authorization: Bearer <token>
Content-Type: application/json

{ "title": "Updated Title" }
```

---

## 19. Analytics API

### 19.1 Dashboard Statistics

```http
GET /form/api/v1/analytics/dashboard
Authorization: Bearer <token>
```

Requires role: `admin`, `superadmin`, or `manager`.

Response:
```json
{
  "data": {
    "total_forms": 150,
    "active_forms": 42,
    "total_responses": 3200,
    "recent_activity": [
      { "type": "New Submission", "details": "...", "timestamp": "..." }
    ]
  }
}
```

**Warning:** This endpoint queries ALL forms and responses without tenant scope filter (see risks documentation).

### 19.2 Summary

```http
GET /form/api/v1/analytics/summary
Authorization: Bearer <token>
```

Requires role: `admin` or `superadmin`. Also unscoped.

### 19.3 Trends

```http
GET /form/api/v1/analytics/trends
Authorization: Bearer <token>
```

Currently returns empty trends array (stub implementation).

---

## 20. Webhook API

All webhook operations require role: `admin`, `superadmin`, or `manager` (except status GET which requires JWT only).

### 20.1 Deliver Webhook

```http
POST /form/api/v1/webhooks/deliver
Authorization: Bearer <manager_token>
Content-Type: application/json

{
  "url": "https://target.example.com/hook",
  "webhook_id": "wh-uuid",
  "form_id": "form-uuid",
  "payload": { "event": "form_submitted", "data": {} },
  "max_retries": 5,
  "timeout": 10,
  "headers": { "X-Custom-Header": "value" },
  "schedule_for": "2026-04-02T15:00:00Z"
}
```

### 20.2 Webhook Status, History, Retry, Cancel, Test, Logs

```http
GET  /form/api/v1/webhooks/<delivery_id>/status
GET  /form/api/v1/webhooks/<delivery_id>/history
POST /form/api/v1/webhooks/<delivery_id>/retry
POST /form/api/v1/webhooks/<delivery_id>/cancel
POST /form/api/v1/webhooks/<webhook_id>/test
GET  /form/api/v1/webhooks/<webhook_id>/logs
```

---

## 21. SMS API

All SMS operations require role: `admin`, `superadmin`, or `manager` (except OTP which requires `admin`/`superadmin`).

### 21.1 Send SMS

```http
POST /form/api/v1/sms/single
Authorization: Bearer <manager_token>
Content-Type: application/json

{ "mobile": "9876543210", "message": "Your appointment is confirmed." }
```

Rate limited: 10 per minute.

### 21.2 Send OTP (Admin Tool)

```http
POST /form/api/v1/sms/otp
Authorization: Bearer <admin_token>
Content-Type: application/json

{ "mobile": "9876543210", "otp": "123456" }
```

Rate limited: 5 per minute.

### 21.3 Send Notification

```http
POST /form/api/v1/sms/notify
Authorization: Bearer <manager_token>
Content-Type: application/json

{ "mobile": "9876543210", "title": "Reminder", "body": "Please complete your form." }
```

### 21.4 SMS Health Check

```http
GET /form/api/v1/sms/health
Authorization: Bearer <token>
```

---

## 22. Custom Field / Library API

Accessible at two URL prefixes (both point to the same blueprint):
- `/form/api/v1/custom-fields/`
- `/form/api/v1/templates/`

Standard CRUD for custom field templates (reusable question definitions).

---

## 23. View (HTML Render) Routes

These routes render HTML templates — they are NOT JSON API routes.

```http
GET /form/api/v1/view/                 # Renders login.html
GET /form/api/v1/view/<form_id>        # Renders view.html with form data
```

No authentication required. Optional `?lang=<code>` applies translations.

**Warning:** No organization scoping — any form_id renders regardless of tenant.

---

## 24. Health Check

```http
GET /form/health
```

Returns 200 if the application is running. No authentication required.

---

## 25. Common Error Responses

| Scenario | HTTP Code | Response |
|---------|---------|---------|
| Missing/invalid JWT | 401 | `{"success": false, "message": "Missing or invalid token"}` |
| Expired JWT | 401 | `{"success": false, "message": "Token expired"}` |
| Insufficient role | 403 | `{"success": false, "message": "Insufficient permissions"}` |
| Form not found | 404 | `{"success": false, "message": "Form not found"}` |
| Rate limit exceeded | 429 | Flask-Limiter default response |
| Validation error | 400 | `{"success": false, "message": "<Pydantic error detail>"}` |
| Server error | 500 | `{"success": false, "message": "Authentication failed"}` (generic) |

---

## 26. Client Integration Checklist

For browser clients (cookie mode):
- [ ] On login, store CSRF tokens from cookies for subsequent requests
- [ ] Send `X-CSRF-TOKEN-ACCESS` on all state-changing requests
- [ ] Handle 401 by attempting token refresh, then re-login
- [ ] Handle 429 with exponential backoff

For programmatic clients (header mode):
- [ ] Store access and refresh tokens from login response body
- [ ] Include `Authorization: Bearer <token>` on all authenticated requests
- [ ] Implement token refresh when access token expires (401 response)
- [ ] Implement re-login when refresh token expires

For all clients:
- [ ] Use `X-Request-ID` header for request correlation in logs
- [ ] Always check `success` field in response before processing `data`
- [ ] Handle 202 responses by polling or using task ID (for async operations)
- [ ] Check `available` field before using form slugs
