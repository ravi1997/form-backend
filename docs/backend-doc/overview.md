# Backend Engineering Handbook — RIDP Form Platform

## 1. Purpose

This document is the authoritative engineering reference for the RIDP Form Platform backend. It is written for engineers, QA, DevOps, and security reviewers who need a complete understanding of how the system works, how requests flow, how tenancy is enforced, and how all moving parts fit together — without needing to read source code line by line.

---

## 2. System Identity

| Property | Value |
|----------|-------|
| Platform name | RIDP Form Platform |
| Runtime | Python 3.x / Flask 3.1 |
| Primary transport | HTTP/1.1 (REST JSON API) |
| Base path | `/form` (all routes prefixed here) |
| API versioning | `/form/api/v1/` |
| Documentation UI | `/form/docs` (Swagger/Flasgger) |
| OpenAPI spec | `/form/apispec_1.json` |

---

## 3. High-Level Architecture

```
Client (Browser / Mobile / Frontend)
  │
  ▼
API Gateway / Reverse Proxy (Nginx / Traefik)
  │  strips /form prefix or forwards as-is
  ▼
Flask Application (Gunicorn / Flask Dev Server)
  │
  ├─ Middleware Stack (executed in order for every request):
  │     1. request_id.py     — attaches X-Request-ID to request + response
  │     2. security_waf.py   — OWASP pattern WAF, blocks malicious inputs
  │     3. tenant_db.py      — extracts organization_id from JWT, sets thread-local
  │
  ├─ Flask-JWT-Extended       — validates Bearer token or HttpOnly cookie
  ├─ Flask-Limiter            — tenant-aware Redis-backed rate limiting
  ├─ Flask-Talisman           — HSTS + security headers
  │
  ├─ Route Handlers (routes/v1/)
  │     └─ delegates to Service Layer (services/)
  │           └─ reads/writes MongoEngine models (models/)
  │                 └─ MongoDB Atlas / MongoDB
  │
  ├─ Long-running operations → Celery Worker
  │     ├─ Celery Broker: Redis DB (CELERY_BROKER_DB)
  │     └─ Tasks: publish_form, clone_form, bulk_export, notifications, etc.
  │
  └─ Redis (3 logical databases):
        ├─ DB cache  — general cache, NLP search cache (1hr TTL)
        ├─ DB session — JWT blocklist, OTP storage
        └─ DB queue  — Celery broker
```

---

## 4. Technology Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Web framework | Flask 3.1 | Application factory pattern (`create_app()`) |
| ODM / Database | MongoEngine + MongoDB | Multi-tenant with soft-delete |
| Auth tokens | Flask-JWT-Extended | Dual mode: header + HttpOnly cookie |
| Rate limiting | Flask-Limiter | Redis-backed, tenant-aware |
| Security headers | Flask-Talisman | HSTS enabled, CSP disabled (REST API) |
| API documentation | Flasgger (Swagger 2.0) | Live UI at `/form/docs` |
| Background tasks | Celery + Redis | Multiple named queues |
| Caching | Redis | 3 DB logical separation |
| Schema validation | Pydantic v2 | Input validation at route boundary |
| AI / LLM | Ollama (local) | Summarization, embeddings, translation |
| Search | Elasticsearch + Ollama embeddings | NLP/semantic search with keyword fallback |
| Observability | OpenTelemetry | Flask instrumented, Jaeger/OTLP exporter |
| Logging | Python logging + RotatingFileHandler | 5 named loggers, 10MB rotate, PII masking |
| Error tracking | Sentry (optional) | Configured via `SENTRY_DSN` env var |
| CORS | Flask-CORS | Credentials-enabled, per `ALLOWED_ORIGINS` |

---

## 5. Application Factory (`app.py`)

The application is assembled inside `create_app()`. The startup sequence is:

1. `setup_logging()` — configure all 5 loggers with PII filter
2. `init_tracing()` — initialize OpenTelemetry with OTLP exporter
3. Create Flask app, load configuration from `settings` object
4. Initialize CORS (credentials + allowed origins)
5. Initialize JWT, Limiter, Talisman, Swagger
6. Register JWT event handlers (token expired, invalid, missing)
7. Register middleware: `request_id`, `security_waf`, `tenant_db`
8. Connect to MongoDB (ping to verify); exit on failure in non-dev
9. Configure 3 Redis clients (cache, session, queue); exit on failure in non-dev
10. Register all blueprints via `register_blueprints(app)`
11. Instrument Flask with OpenTelemetry `FlaskInstrumentor`
12. Register global error handlers

**Critical JWT cookie configuration:**

```python
JWT_TOKEN_LOCATION = ["headers", "cookies"]
JWT_ACCESS_COOKIE_PATH = "/form/api/"
JWT_REFRESH_COOKIE_PATH = "/form/api/v1/auth/refresh"
JWT_COOKIE_SECURE = not DEBUG   # HTTPS-only in production
JWT_COOKIE_HTTPONLY = True
JWT_COOKIE_SAMESITE = "Lax"
JWT_COOKIE_CSRF_PROTECT = True
JWT_ACCESS_CSRF_HEADER_NAME = "X-CSRF-TOKEN-ACCESS"
JWT_REFRESH_CSRF_HEADER_NAME = "X-CSRF-TOKEN-REFRESH"
```

Clients using cookies must send the appropriate CSRF header on state-changing requests.

---

## 6. Multi-Tenancy Model

Every MongoEngine document model includes an `organization_id` field. Tenancy is enforced at three independent layers:

### Layer 1: JWT Claim Injection

`middleware/tenant_db.py` runs before every request. It reads the JWT claims (`get_jwt()`), extracts `org_id`, and stores it in Flask's `g` object. The middleware also sets up the thread-local MongoDB alias for tenant-isolated queries.

### Layer 2: QuerySet-Level Filtering

The custom `TenantIsolatedSoftDeleteQuerySet` in `models/base.py` is the default manager for all models. It automatically appends:
- `organization_id = g.org_id` — tenant isolation
- `is_deleted = False` — soft-delete filtering

This means: unless a query explicitly bypasses this queryset (using `__raw__` or direct `.objects.get()`), tenant and soft-delete filtering are automatic.

### Layer 3: Service-Level Assertions

Service methods accept `organization_id` as a parameter and assert it in the query. Route handlers pass `current_user.organization_id` explicitly.

### Superadmin Bypass

Users with role `superadmin` bypass the `organization_id` filter. This is enforced in `require_roles()` and checked in service methods.

---

## 7. Authentication & Authorization Architecture

### JWT Token Lifecycle

```
User presents credentials (password or OTP)
  ↓
AuthService.generate_tokens(user_doc) → { access_token, refresh_token }
  ↓
Tokens set as HttpOnly cookies AND returned in response body
  ↓
Client sends:
  - Cookie: access_token (automatic) + X-CSRF-TOKEN-ACCESS header
  - OR: Authorization: Bearer <access_token> header
  ↓
flask_jwt_extended validates token on every @jwt_required() route
  ↓
On logout: auth_service.revoke_token_payload(get_jwt()) → adds JTI to Redis blocklist
```

### Role-Based Access Control (RBAC)

Four roles in ascending privilege order:

| Role | Access Level |
|------|-------------|
| `user` | Own profile, submit forms, view permitted forms |
| `manager` | Everything user can do + analytics, webhooks, SMS |
| `admin` | Everything manager can do + user CRUD, form admin, lock/unlock |
| `superadmin` | Everything admin can do + user delete, env config, cross-tenant |

The `@require_roles(*roles)` decorator is defined in `utils/security.py`. It wraps `@jwt_required()` and checks `current_user.roles` against the required roles.

### Fine-Grained Form Permissions

In addition to RBAC, each form has per-form ACL fields:

| Field | Meaning |
|-------|---------|
| `created_by` | Form creator — has all permissions |
| `editors` | List of user IDs with edit rights |
| `viewers` | List of user IDs with view rights |
| `submitters` | List of user IDs with submit rights |
| `access_policy` | Embedded `AccessPolicy` document with fine-grained flags |

The `has_form_permission(user, form, action)` helper (in `routes/v1/form/helper.py`) evaluates all of: user role, explicit lists, and `access_policy` fields.

Supported action strings: `view`, `edit`, `submit`, `view_responses`, `edit_responses`, `delete_responses`, `edit_design`, `manage_access`, `view_audit`, `delete_form`.

The `@require_permission("resource", "action")` decorator in `utils/security_helpers.py` is used at the route level for resource-level checks.

---

## 8. Middleware Stack

### `middleware/request_id.py`

Generates a UUID for every request if `X-Request-ID` header is not present. Stores in `g.request_id`. Appended to every response as `X-Request-ID`. All logs include this ID for correlation.

### `middleware/security_waf.py`

A custom Web Application Firewall. Inspects URL, query parameters, and request body for OWASP Top-10 patterns including:
- SQL injection patterns
- XSS payloads
- Path traversal (`../`)
- Command injection (`; ls`, `| cat`, etc.)
- Template injection patterns

Blocks matching requests with `400 Bad Request` before they reach route handlers.

### `middleware/tenant_db.py`

Extracts `org_id` from JWT claims. Sets `g.organization_id`. Configures the MongoEngine connection alias for the current request thread to enforce tenant isolation at the database driver level.

---

## 9. Service Layer

All business logic lives in `services/`. Route handlers are thin — they parse input, call a service method, and return the result.

`services/base.py` provides `BaseService` with:
- `create(schema)` — validates and inserts
- `get_by_id(id, **filters)` — fetch with filters
- `update(id, schema, **filters)` — fetch + update
- `delete(id, **filters)` — soft-delete
- `list_paginated(page, page_size, **filters)` — paginated list

Services take Pydantic v2 schemas as input. They return MongoEngine model instances or dicts. They never return HTTP responses.

Key services:

| Service | Responsibility |
|---------|---------------|
| `AuthService` | Token generation, blocklist management, session revocation |
| `UserService` | User CRUD, authentication, OTP lifecycle |
| `FormService` | Form CRUD, template management |
| `SectionService` | Form section CRUD and reordering |
| `FormResponseService` | Response submission, listing |
| `DashboardService` | Dashboard CRUD, widget data resolution |
| `WebhookService` | Webhook delivery, status, retry |
| `SummarizationService` | LLM-backed form response summarization |
| `AIService` | Translation via Ollama |
| `OllamaService` | Ollama API client (health, embeddings, generate) |
| `RedisService` | Multi-client Redis accessor |

---

## 10. Async Task Architecture (Celery)

Long-running operations are offloaded to Celery workers. Tasks live in `tasks/`.

### Queues

| Queue name | Purpose |
|-----------|---------|
| `celery` (default) | Form publish, form clone, bulk export |
| `sms` | SMS delivery tasks |
| `mail` | Email notification tasks |
| `ehospital` | eHospital integration tasks |
| `request` | Outbound HTTP request tasks |
| `employee` | Employee data sync tasks |

### Retry Policy

- Max retries: 3
- Backoff: 300 seconds
- Soft time limit: 300 seconds
- Hard time limit: 3600 seconds

### Key async tasks

| Task | Trigger | Queue |
|------|---------|-------|
| `async_publish_form` | `POST /forms/<id>/publish` → 202 | celery |
| `async_clone_form` | `POST /forms/<id>/clone` → 202 | celery |
| `async_bulk_export` | `POST /forms/export/bulk` → 202 | celery |

Callers receive `{ task_id }` in the 202 response. Currently, no dedicated task-status poll endpoint exists in the public API.

**Important architectural note:** Translation jobs (TranslationJob) use Python `threading.Thread`, NOT Celery. This means translation jobs do NOT survive worker restarts and have no retry capability. See risks documentation.

---

## 11. Logging Architecture

Five named loggers. Import from `logger.unified_logger`:

```python
from logger.unified_logger import app_logger, error_logger, audit_logger
from logger import get_logger, performance_logger

logger = get_logger(__name__)   # module-level general logger
```

| Logger name | Use case | When to use |
|-------------|----------|-------------|
| `app_logger` | General application operations | Entering/exiting functions, state changes |
| `error_logger` | Exceptions | Always with `exc_info=True` for stack traces |
| `audit_logger` | Compliance events | State changes: login, logout, create, update, delete |
| `performance_logger` | Timing diagnostics | Slow query detection, expensive operations |
| `structured` | Machine-readable structured logs | Integration with log aggregators |

Log files rotate at 10MB with 10 backups. A PII filter in `config/logging.py` automatically masks:
- Passwords
- JWT tokens
- Phone numbers
- Email addresses (configurable)

All logs include `X-Request-ID` for cross-request correlation.

---

## 12. Data Model Overview

### Form Document

Key fields:
- `id` (UUID) — primary key
- `organization_id` — tenant identifier
- `title`, `slug` — slugs are globally unique
- `status` — `draft` | `published` | `archived`
- `is_template` — forms used as templates
- `is_public` — enables anonymous public submission
- `is_deleted` — soft-delete flag
- `sections` — list of embedded Section references
- `active_version_id` — points to the current FormVersion
- `supported_languages`, `default_language`, `translations` — i18n support
- `expires_at`, `publish_at` — lifecycle scheduling
- `created_by`, `editors`, `viewers`, `submitters` — ACL fields
- `access_policy` — embedded AccessPolicy document

### FormVersion Document

Immutable snapshot of a form at publish time. Key fields:
- `form` — reference to parent Form
- `version_string` — semantic version (e.g., `1.2.0`)
- `resolved_snapshot` — complete denormalized form structure (sections + questions + options)
- `translations` — per-language translation map

The `resolved_snapshot` is what gets used for CSV/JSON exports. It is frozen at publish time and never mutated.

### FormResponse Document

- `form` — reference to Form
- `organization_id` — tenant isolation
- `data` — dict of `{ variable_name: value }` or `{ section_id: { question_id: value } }`
- `submitted_by` — user ID or `"anonymous"`
- `status` — `submitted` | `draft`
- `ip_address`, `user_agent` — submission metadata

### User Document

- `id`, `username`, `email`, `mobile`, `employee_id` — identifiers (any can be used for login)
- `organization_id` — tenant membership
- `roles` — list: `["user"]`, `["admin"]`, etc.
- `is_admin`, `is_active`, `is_deleted` — status flags
- `failed_login_attempts`, `lock_until` — account security
- Password stored as bcrypt hash (via `set_password()` / `check_password()` methods)

---

## 13. Error Handling

### Global Error Handlers

Registered in `utils/error_handlers.py` and applied in `create_app()`:

| Exception | HTTP Status | Behavior |
|-----------|------------|---------|
| `ValidationError` | 400 | Returns `{"success": false, "message": "..."}` |
| `UnauthorizedError` | 401 | Returns 401 with message |
| `ForbiddenError` | 403 | Returns 403 with message |
| `NotFoundError` | 404 | Returns 404 with message |
| `Exception` (unhandled) | 500 | Returns generic 500, logs with `error_logger` |

### Standard Response Shape

All routes use `success_response()` and `error_response()` from `utils/response_helper.py`:

```json
// Success
{
  "success": true,
  "data": { ... },
  "message": "Optional message"
}

// Error
{
  "success": false,
  "message": "Human-readable error",
  "error": "Optional technical detail"
}
```

---

## 14. Rate Limiting

Flask-Limiter with Redis storage. Limits are applied per route:

| Route group | Default limit |
|-------------|--------------|
| `POST /auth/register` | 5 per minute |
| `POST /auth/login` | 5 per minute |
| `POST /auth/request-otp` | 3 per minute |
| `POST /user/change-password` | 3 per hour |
| `POST /sms/single` | 10 per minute |
| `POST /sms/otp` | 5 per minute |

The limiter is tenant-aware: rate limit keys include the organization context so one tenant cannot exhaust limits for another.

On limit exceeded, Flask-Limiter returns `429 Too Many Requests`.

---

## 15. Development & Operations

### Starting the application

```bash
make up-dev        # Live reload (Flask dev server + bind-mount)
make up            # Production (gunicorn)
make restart       # Restart backend + celery + celery-beat (use after code changes)
make build         # Rebuild Docker image
make bootstrap     # Create MongoDB indexes (run once on new environment)
```

### Running tests

```bash
make test          # Run full pytest suite inside container
make test-cov      # With coverage report
make lint          # flake8 + black + mypy

# Run a specific test file:
docker compose run --rm backend pytest tests/test_auth_service.py -v

# Run a specific test:
docker compose run --rm backend pytest tests/test_auth_service.py::TestClass::test_method -v
```

Tests use `testcontainers` to spin real MongoDB and Redis — no mocks. `APP_ENV=testing` is set automatically via `pytest.ini`. Coverage targets: `services/` and `routes/`.

### Environment variables

| Variable | Notes |
|----------|-------|
| `APP_ENV` | `development` / `testing` / `production` |
| `MONGODB_URI` | Full MongoDB connection string |
| `REDIS_HOST` / `REDIS_PORT` | Redis host and port |
| `REDIS_DB` | Base DB index (session = DB+1, queue = CELERY_BROKER_DB) |
| `JWT_SECRET_KEY` | Must be changed in production |
| `ALLOWED_ORIGINS` | CORS allowed origins list |
| `ELASTICSEARCH_URL` | For search and analytics |
| `AI_PROVIDER` | `local` / `ollama` / `openai` |
| `OLAP_ENGINE` | `duckdb` (default) or `clickhouse` |
| `SENTRY_DSN` | Optional error tracking |

---

## 16. Blueprint Registration Summary

All blueprints are registered in `routes/__init__.py` under the `/form` base prefix:

| Blueprint | URL Prefix | Module |
|-----------|-----------|--------|
| `health_bp` | `/form/health` | `routes/health` |
| `form_bp` | `/form/api/v1/forms` | `routes/v1/form/` |
| `translation_bp` | `/form/api/v1/forms/translations` | `routes/v1/form/translation.py` |
| `library_bp` | `/form/api/v1/custom-fields` | `routes/v1/form/library.py` |
| `library_bp` (alias) | `/form/api/v1/templates` | same, registered as `form_templates` |
| `permissions_bp` | `/form/api/v1/forms` | `routes/v1/form/permissions.py` |
| `view_bp` | `/form/api/v1/view` | `routes/v1/view_route.py` |
| `auth_bp` | `/form/api/v1/auth` | `routes/v1/auth_route.py` |
| `ai_bp` | `/form/api/v1/ai` | `routes/v1/form/ai.py` |
| `nlp_search_bp` | `/form/api/v1/ai/search` | `routes/v1/form/nlp_search.py` |
| `dashboard_bp` | `/form/api/v1/dashboards` | `routes/v1/dashboard_route.py` |
| `dashboard_settings_bp` | `/form/api/v1/dashboard-settings` | `routes/v1/dashboard_settings_route.py` |
| `analytics_bp` | `/form/api/v1/analytics` | `routes/v1/analytics_route.py` |
| `workflow_bp` | `/form/api/v1/workflows` | `routes/v1/workflow_route.py` |
| `webhooks_bp` | `/form/api/v1/webhooks` | `routes/v1/webhooks.py` |
| `sms_bp` | `/form/api/v1/sms` | `routes/v1/sms_route.py` |
| `external_api_bp` | `/form/api/v1/external` | `routes/v1/external_api_route.py` |
| `advanced_responses_bp` | `/form/api/v1/forms` | `routes/v1/form/advanced_responses.py` |
| `system_settings_bp` | `/form/api/v1/admin/system-settings` | `routes/v1/admin/system_settings_route.py` |
| `env_config_bp` | `/form/api/v1/admin/env-config` | `routes/v1/admin/env_config_route.py` |
| `system_bp` | `/form/api/v1/system` | `routes/v1/admin/system_route.py` |
| `user_bp` | `/form/api/v1/user` | `routes/v1/user_route.py` |
| `user_bp` (alias) | `/form/api/v1/users` | same, registered as `user_bp_plural` |

Note: `advanced_responses_bp` is registered at `/form/api/v1/forms`, which overlaps with `form_bp`. Both are active. Some routes in `advanced_responses_bp` include the `form_id` in the path (e.g., `/<form_id>/fetch/same`), making them distinguishable.
