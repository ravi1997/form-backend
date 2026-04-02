# Backend Policy Document — RIDP Form Platform

## 1. Purpose

This document defines the policies that govern how the RIDP Form Platform backend is designed, built, secured, and operated. These are binding rules for all contributors and integrators.

---

## 2. API Design Policy

### 2.1 URL Structure

- All routes are prefixed with `/form` (gateway routing namespace)
- All API routes follow `/form/api/v1/<resource>`
- Blueprint names use snake_case; URL segments use kebab-case
- Resource names are plural nouns (e.g., `/forms`, `/users`, `/dashboards`)
- Sub-resources use nested paths (e.g., `/forms/<form_id>/responses`)

### 2.2 HTTP Method Semantics

| Method | Semantics |
|--------|----------|
| `GET` | Read-only; must not modify state |
| `POST` | Create a resource or trigger an action |
| `PUT` | Full update — replace all mutable fields |
| `PATCH` | Partial update — modify specific fields |
| `DELETE` | Soft-delete (unless explicitly documented as hard delete) |

### 2.3 Response Shape

All endpoints must use `success_response()` and `error_response()` from `utils/response_helper.py`. Raw `jsonify()` is allowed only in legacy or streaming contexts.

**Success:**
```json
{
  "success": true,
  "data": { ... },
  "message": "Optional human-readable message"
}
```

**Error:**
```json
{
  "success": false,
  "message": "Human-readable error description",
  "error": "Optional technical detail (omit in production for security-sensitive errors)"
}
```

### 2.4 HTTP Status Codes

| Situation | Code |
|-----------|------|
| Successful read or action | 200 |
| Resource created | 201 |
| Async task accepted | 202 |
| Validation error | 400 |
| Authentication missing/invalid | 401 |
| Authenticated but not authorized | 403 |
| Resource not found | 404 |
| Rate limit exceeded | 429 |
| Unexpected server failure | 500 |

### 2.5 Pagination

Paginated endpoints accept `page` (default: 1) and `page_size` (default varies per endpoint) as query parameters. Response data is wrapped in a pagination envelope:

```json
{
  "success": true,
  "data": {
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 20,
    "total_pages": 5
  }
}
```

---

## 3. Authentication Policy

### 3.1 Token Strategy

- Access tokens are short-lived JWTs
- Refresh tokens are longer-lived JWTs
- Both tokens are issued simultaneously on login
- Tokens are delivered in **both** HttpOnly cookies AND response body
- Cookie path scoping prevents token re-use across wrong endpoints:
  - Access token cookie: `/form/api/`
  - Refresh token cookie: `/form/api/v1/auth/refresh`

### 3.2 Bearer Token vs Cookie

Both modes are supported and checked in order:
1. `Authorization: Bearer <token>` header
2. `access_token` HttpOnly cookie

When using cookies, the client **must** also send the CSRF token:
- `X-CSRF-TOKEN-ACCESS` for access-token-protected endpoints
- `X-CSRF-TOKEN-REFRESH` for the refresh endpoint

### 3.3 Token Revocation

- On logout: the access token JTI is added to the Redis blocklist (`session` DB)
- On `revoke-all`: all JTIs for the user are invalidated simultaneously
- Blocklisted tokens are rejected by the JWT validation middleware

### 3.4 OTP Flow

- `POST /auth/request-otp` → generates OTP, stores in Redis with TTL, sends via SMS/email
- `POST /auth/login` with `mobile + otp` → verifies OTP from Redis, issues tokens on match
- OTP rate-limited to 3 per minute per identifier

### 3.5 Session Security

- Account lockout: after a configurable number of failed login attempts, `lock_account()` is called on the User model, setting `lock_until` to a future timestamp
- `is_locked()` is checked on every login attempt
- Admins can manually lock/unlock accounts via `POST /user/users/<id>/lock` and `/unlock`

---

## 4. Authorization Policy

### 4.1 Role Hierarchy

Roles are additive — higher roles subsume lower role permissions:

```
superadmin > admin > manager > user
```

The `require_roles(*roles)` decorator accepts one or more role strings. A user passes if any of their assigned roles is in the required set.

### 4.2 Form-Level Access Control

Each form has its own ACL independent of global roles. The `has_form_permission(user, form, action)` function evaluates:

1. Is the user a superadmin? → grant all
2. Is the user's role admin or manager? → grant most
3. Is the user's ID in `form.editors`? → grant edit-level permissions
4. Is the user's ID in `form.viewers`? → grant view-level permissions
5. Is the user's ID in `form.submitters`? → grant submit permission
6. Does the form's `access_policy` grant the permission? → check policy fields
7. Is the user the `created_by` of the form? → grant all

### 4.3 Tenant Isolation

No user can access data from a different organization, except superadmins. Tenant isolation is enforced at three independent layers (see overview.md §6). A user without an `organization_id` cannot create forms or access org-scoped resources.

### 4.4 Public Forms

Forms with `is_public = True` and `status = "published"` allow anonymous submission via `POST /forms/<id>/public-submit` without JWT. This is the only unauthenticated write endpoint. The form must also not be expired or scheduled for the future.

---

## 5. Validation Policy

### 5.1 Input Validation

All structured input (request body) must be validated with a Pydantic v2 schema before reaching service layer. Route handlers instantiate the schema: `schema = MySchema(**data)`. Pydantic raises `ValidationError` on constraint violations, which the global error handler converts to a 400 response.

### 5.2 WAF Pre-Validation

The WAF middleware (`security_waf.py`) runs before JWT validation and before route dispatch. Requests containing OWASP Top-10 attack patterns are rejected with 400 before any application code executes.

### 5.3 Form ID Validation

Form IDs are UUIDs. Routes that accept `form_id` in the path validate UUID format before querying MongoDB. Invalid format returns 400 "Invalid form ID format".

### 5.4 Slug Policy

- Slugs are auto-generated from the form title at creation if not provided: `re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")`
- Slugs are globally unique (not just per tenant)
- `GET /forms/slug-available?slug=<value>` can be used to check availability before creation

---

## 6. Data Persistence Policy

### 6.1 Soft Delete

All documents implement soft delete via `is_deleted` flag. The `TenantIsolatedSoftDeleteQuerySet` excludes `is_deleted=True` documents from all standard queries. Hard deletes are:
- Prohibited for forms, users (use soft delete)
- Permitted only for: all responses for a form (`DELETE /forms/<id>/responses` — admin only, irreversible)

### 6.2 Audit Trail

Every state-changing operation must log to `audit_logger` with:
- `AUDIT:` prefix (for grep-ability)
- Actor identity (user ID)
- Resource affected (form ID, user ID, etc.)
- Action taken
- Timestamp (automatic from logger)

### 6.3 Form Versioning

When a form is published:
1. A `FormVersion` document is created with a `resolved_snapshot` — a complete denormalized copy of the form structure
2. The `active_version_id` on the Form is updated to point to the new version
3. The snapshot is immutable — it is never modified after creation
4. Exports use the resolved_snapshot, not the live form structure

Semantic versioning is applied: `major_bump=True` increments major version; otherwise minor version is incremented.

### 6.4 Organization_ID Enforcement

No service method creates or modifies a document without setting `organization_id`. Forms created by users without an `organization_id` are rejected at the route level (400 "Current user has no organization_id").

---

## 7. Security Policy

### 7.1 Password Hashing

All passwords are hashed with bcrypt via the User model's `set_password()` method. Plaintext passwords are never stored or logged. The PII filter in `config/logging.py` masks any field named `password` in log records.

### 7.2 HTTPS / HSTS

Flask-Talisman enforces `Strict-Transport-Security` (HSTS) in production. In development, `force_https=False`. JWT cookies have `Secure=True` when `DEBUG=False`.

### 7.3 Security Headers

Flask-Talisman provides:
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`

Content Security Policy (CSP) is disabled (`content_security_policy=None`) because this is a REST API serving JSON, not HTML pages.

### 7.4 CORS Policy

CORS is configured via Flask-CORS with:
- `origins` = `ALLOWED_ORIGINS` from settings
- `supports_credentials = True` (required for cookie-based auth)
- Allowed headers: `Content-Type`, `Authorization`, `X-CSRF-TOKEN-ACCESS`, `X-CSRF-TOKEN-REFRESH`, `X-Organization-ID`

Wildcard origins (`*`) are never allowed in production because `supports_credentials=True` requires explicit origin whitelisting.

### 7.5 WAF Policy

The custom WAF middleware blocks requests before authentication. It is not a replacement for parameterized queries (MongoEngine handles this) but provides defense-in-depth against:
- SQL injection
- XSS payloads in request data
- Path traversal
- Command injection
- Template injection

### 7.6 Rate Limiting Policy

Rate limits are enforced using Flask-Limiter with Redis. Limits are defined per-route. When a limit is exceeded, the response is `429 Too Many Requests`. Rate limit keys include tenant context to prevent cross-tenant exhaustion.

### 7.7 Sensitive Data in Responses

- Password fields are never included in API responses
- JWT tokens in response bodies are acceptable for programmatic clients
- `UserOut` schema (Pydantic) explicitly excludes password hashes, internal flags

---

## 8. Observability Policy

### 8.1 Structured Logging

All log entries must include: request ID, log level, logger name, message. For service-layer logs, include relevant entity IDs (form_id, user_id). Use the correct logger for the context.

### 8.2 Distributed Tracing

All Flask requests are automatically instrumented by `FlaskInstrumentor`. Custom spans can be added using the OpenTelemetry API. Traces are exported via OTLP to the configured collector.

### 8.3 Health Endpoints

- `GET /form/health` — liveness check; returns 200 if app is running
- `GET /form/api/v1/ai/health` — AI service health (public, no auth)
- `GET /form/api/v1/sms/health` — SMS service connectivity (requires JWT)

---

## 9. AI / LLM Policy

### 9.1 Approved Models

The system uses Ollama with:
- Default generation model: `llama3.2`
- Embedding model: `nomic-embed-text`

The AI provider is configurable via `AI_PROVIDER` env var. Supported values: `local`, `ollama`, `openai`.

### 9.2 Summarization

The summarization service (`SummarizationService`) requires at least 2 responses before generating a summary. Summaries are generated on-demand (not cached). Streaming summaries use Server-Sent Events (SSE).

### 9.3 NLP Search

Semantic search results are cached in Redis with a 1-hour TTL. The search falls back to keyword search if Ollama embeddings are unavailable. Search history and popular queries are stored per-user.

### 9.4 Translation

AI-powered translation uses `AIService.translate_bulk()`. Translation jobs run in Python threads (not Celery). This is a known architectural risk. Translations are stored in `FormVersion.translations[lang_code]`.

---

## 10. Contributor Policy

### 10.1 Adding a New Feature

Follow this sequence:
1. Model in `models/YourModel.py`
2. Pydantic schema in `schemas/your_schema.py`
3. Service in `services/your_service.py` (extend `BaseService`)
4. Blueprint in `routes/v1/your_route.py`
5. Register blueprint in `routes/__init__.py`
6. Tests in `tests/test_your_feature.py`

### 10.2 Service Layer Rules

- Services must not import from `flask` or `flask_jwt_extended`
- Services must not return HTTP response objects
- Services take Pydantic schemas as input, return model instances or plain dicts
- All service methods must be testable in isolation from the Flask context

### 10.3 Route Handler Rules

- Route handlers must be thin: parse input → call service → return response
- Route handlers must not contain business logic
- All route handlers must use the correct decorator order:
  ```python
  @blueprint.route(...)
  @swag_from(...)
  @jwt_required() / @require_roles(...)
  @require_permission(...)
  def handler():
  ```
- All state-changing operations must log to `audit_logger`

### 10.4 Test Policy

- Tests must use real MongoDB and Redis via testcontainers
- No mocking of database queries
- `APP_ENV=testing` must be set (handled by `pytest.ini`)
- Test files must be in `tests/` following naming `test_<module>.py`

### 10.5 Migration Policy

Schema migrations live in `scripts/schema_migrations/`. Run via `manage.py`. Never perform destructive migrations on production without a rollback plan. Index creation runs via `make bootstrap`.
