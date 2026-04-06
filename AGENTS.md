# RIDP Form Platform — Agent Reference

> This file is the primary context document for AI coding agents (Claude Code, Gemini, Kilo Code, Cursor, Copilot, etc.) working in this repository. Read it before touching any file.

---

## 1. What This Project Is

**RIDP Form Platform** — a multi-tenant form-building and data-collection backend.

| Property | Value |
|----------|-------|
| Language / Framework | Python 3.x / Flask 3.1 |
| Database | MongoDB via MongoEngine ODM |
| Cache / Queue | Redis (3 logical DBs) |
| Task queue | Celery (multiple named queues) |
| Auth | Flask-JWT-Extended — Bearer header + HttpOnly cookie |
| Validation | Pydantic v2 |
| AI / LLM | Ollama (local) — `llama3.2` + `nomic-embed-text` |
| All routes prefix | `/form` → `/form/api/v1/` |
| Swagger UI | `GET /form/docs` |
| Run stack | Docker Compose (`make up-dev` for dev, `make up` for prod) |

---

## 2. Critical Rules — Read Before Writing Any Code

### 2.1 Multi-Tenancy Is Mandatory

Every query that touches a user-owned resource **must** include `organization_id`. There are no exceptions except for `superadmin` role.

```python
# CORRECT
form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)

# WRONG — never do this for tenant data
form = Form.objects.get(id=form_id)
```

`organization_id` flows from JWT → `middleware/tenant_db.py` → `g.organization_id`. The `TenantIsolatedSoftDeleteQuerySet` in `models/base.py` auto-appends it to standard queries, but `get()`, `__raw__`, and aggregate pipelines bypass it — always add it explicitly there.

### 2.2 Soft Delete Only

Never call `.delete()` on a document. Use `is_deleted = True` instead. The only exception is `TranslationJob` hard-delete, which is documented and intentional.

```python
# CORRECT
obj.update(set__is_deleted=True)

# WRONG
obj.delete()
```

### 2.3 Services Have No Flask Imports

Service files (`services/`) must not import from `flask`, `flask_jwt_extended`, or `request`. They receive plain Python objects / Pydantic schemas. They return MongoEngine instances or dicts.

### 2.4 Route Handlers Are Thin

Route handlers parse input → call service → return response. No business logic in routes.

### 2.5 Use the Correct Logger

```python
from logger.unified_logger import app_logger, error_logger, audit_logger

app_logger.info(...)           # entering/exiting functions, state changes
error_logger.error(..., exc_info=True)  # exceptions — always include exc_info
audit_logger.info(...)         # EVERY state change: create/update/delete/login/logout
```

All state-changing operations require an `audit_logger` line. This is a compliance requirement.

### 2.6 All Input Goes Through Pydantic

```python
# CORRECT
schema = MyCreateSchema(**request.get_json())
result = my_service.create(schema)

# WRONG — never pass raw dicts to services
result = my_service.create(request.get_json())
```

### 2.7 Standard Response Format

Always use helpers from `utils/response_helper.py`:

```python
from utils.response_helper import success_response, error_response

return success_response(data={...}, message="...", status_code=200)
return error_response(message="Not found", status_code=404)
```

Never return raw `jsonify()` in new code (legacy code uses it — don't copy that pattern).

---

## 3. Directory Structure

```
app.py                  # Flask app factory — create_app()
extensions.py           # JWT, CORS, Limiter, Talisman, Swagger init
config/                 # Pydantic settings, Celery config, logging, Redis, Sentry
models/                 # MongoEngine document models (PascalCase filenames)
  base.py               # TenantIsolatedSoftDeleteQuerySet — MUST use as base
schemas/                # Pydantic v2 input/output schemas
routes/
  __init__.py           # register_blueprints() — register ALL blueprints here
  v1/                   # All API blueprints
    auth_route.py
    user_route.py
    dashboard_route.py
    dashboard_settings_route.py  # Per-user settings, widget positions, layout config
    analytics_route.py
    webhooks.py
    sms_route.py
    view_route.py
    workflow_route.py   # Approval workflows (POST/GET/PUT/DELETE /workflows/)
    external_api_route.py  # External API stubs: UHID, employee, mail, SMS
    form/               # Form-related blueprints (all share form_bp or sub-blueprints)
      __init__.py       # form_bp definition
      form.py           # Core CRUD, publish, clone, sections, translations
      responses.py      # Submit + list responses
      export.py         # CSV/JSON streaming, bulk async export
      additional.py     # slug, share, archive, restore, toggle-public, etc.
      advanced_responses.py  # Cross-form queries, access-control, access-policy
      summarization.py  # LLM summarization
      translation.py    # AI translation jobs (Celery-backed)
      anomaly.py        # Anomaly detection
      nlp_search.py     # Semantic/NLP search
      ai.py             # AI health check
      library.py        # Custom field templates
      expire.py         # Form expiry management
      misc.py           # Public submit, history, next-action
      files.py          # File upload (POST /upload, POST /signatures) + serving (GET /<id>/files/...)
      hooks.py          # Event hook triggers (question/section/form/project) + external hook registration
      permissions.py    # Low-level ACL lists: editors/viewers/submitters on Form (permissions_bp)
      validation.py     # validate_form_submission helper + POST /conditions/evaluate
      analytics.py      # Per-form analytics: summary, timeline, distribution, full
      helper.py         # has_form_permission(), apply_translations(), get_current_user()
    admin/              # System administration (all require admin or superadmin)
      system_settings_route.py  # GET/PUT /admin/system-settings/
      env_config_route.py       # GET/PUT /admin/env-config/ (superadmin only, reads .env)
      system_route.py           # GET /system/event-health, GET /system/analytics-trends/<org_id>
services/               # All business logic
  base.py               # BaseService with CRUD + list_paginated
tasks/                  # Celery async tasks
  form_tasks.py         # async_publish_form, async_clone_form, async_bulk_export, async_process_translation_job
middleware/
  request_id.py         # X-Request-ID per request
  security_waf.py       # OWASP WAF — runs before all routes
  tenant_db.py          # Extracts org_id from JWT → g.organization_id
utils/
  response_helper.py    # success_response, error_response, FormSerializer, BaseSerializer
  security.py           # require_roles() decorator
  security_helpers.py   # get_current_user(), require_permission() decorator
tests/                  # pytest + testcontainers (real MongoDB + Redis, no mocks)
```

---

## 4. How to Add a New Feature

Follow this sequence every time:

1. **Model** — `models/YourModel.py`
   - Extend `TenantIsolatedSoftDeleteQuerySet` as the default queryset
   - Add `organization_id = StringField(required=True)`
   - Add `is_deleted = BooleanField(default=False)`

2. **Schema** — `schemas/your_schema.py`
   - Use Pydantic v2 `BaseModel`
   - Separate `CreateSchema` / `UpdateSchema` / `OutSchema`

3. **Service** — `services/your_service.py`
   - Extend `BaseService`
   - No Flask imports
   - Accept Pydantic schemas, return model instances or dicts

4. **Blueprint** — `routes/v1/your_route.py`
   - Use `@swag_from({...})` for Swagger
   - Use `@jwt_required()` or `@require_roles(...)`
   - Keep handlers thin: parse → service call → return response
   - Audit log every write operation

5. **Register** — `routes/__init__.py`
   - Add `from routes.v1.your_route import your_bp`
   - Add `app.register_blueprint(your_bp, url_prefix=f"{base_prefix}/api/v1/your-resource")`

6. **Tests** — `tests/test_your_feature.py`
   - Use real MongoDB + Redis via testcontainers (no mocks)

---

## 5. Authentication

### Decorator Usage

```python
from flask_jwt_extended import jwt_required
from utils.security import require_roles
from utils.security_helpers import require_permission, get_current_user

@bp.route("/resource", methods=["POST"])
@swag_from({...})
@jwt_required()                          # any authenticated user
def my_route():
    current_user = get_current_user()    # get User model instance
    ...

@bp.route("/admin-resource", methods=["POST"])
@require_roles("admin", "superadmin")   # wraps @jwt_required() internally
def admin_route():
    ...

@bp.route("/forms/<form_id>", methods=["GET"])
@jwt_required()
@require_permission("form", "view")     # resource-level permission
def get_form(form_id):
    ...
```

### Form-Level Permission Check (inline)

```python
from routes.v1.form.helper import has_form_permission

form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)
if not has_form_permission(current_user, form, "edit"):
    return error_response(message="Unauthorized", status_code=403)
```

Permission action strings: `view`, `edit`, `submit`, `view_responses`, `edit_responses`, `delete_responses`, `edit_design`, `manage_access`, `view_audit`, `delete_form`

### Role Hierarchy

```
superadmin > admin > manager > user
```

---

## 6. Celery Tasks

For any operation taking > 1 second or involving external APIs:

```python
# In tasks/form_tasks.py
@celery.task(bind=True, max_retries=3, default_retry_delay=300,
             soft_time_limit=300, time_limit=3600)
def my_async_task(self, param1, param2):
    try:
        # do work
    except Exception as exc:
        raise self.retry(exc=exc)

# In route handler — return 202
task = my_async_task.delay(param1, param2)
return success_response(data={"task_id": task.id}, status_code=202)
```

Available queues: `celery` (default), `sms`, `mail`, `ehospital`, `request`, `employee`

To route to a specific queue: `my_task.apply_async(args=[...], queue="sms")`

**Never use `threading.Thread` for background work.** Use Celery.

---

## 7. MongoDB / MongoEngine Patterns

### Standard Document with Tenancy

```python
from mongoengine import Document, StringField, BooleanField
from models.base import TenantIsolatedSoftDeleteQuerySet

class MyModel(Document):
    meta = {
        "collection": "my_collection",
        "queryset_class": TenantIsolatedSoftDeleteQuerySet,
    }
    organization_id = StringField(required=True)
    name = StringField(required=True)
    is_deleted = BooleanField(default=False)
```

### Query Patterns

```python
# Standard query — tenant + soft-delete filtered automatically
items = MyModel.objects(name="foo")           # org scoped via queryset class

# get() bypasses queryset class — always add org filter manually
item = MyModel.objects.get(id=item_id, organization_id=org_id)

# Raw query — always add org filter manually
items = MyModel.objects(__raw__={"name": "foo", "organization_id": org_id})

# Aggregation — always add organization_id to $match
pipeline = [{"$match": {"organization_id": org_id, "is_deleted": False}}, ...]
```

---

## 8. Complete Route Map (Quick Lookup)

All routes start with `/form/api/v1/`. No authentication = public.

| Prefix | Blueprint | Auth |
|--------|-----------|------|
| `/auth/register` | auth | none |
| `/auth/login` | auth | none |
| `/auth/request-otp` | auth | none |
| `/auth/refresh` | auth | JWT refresh |
| `/auth/logout` | auth | JWT |
| `/auth/revoke-all` | auth | JWT |
| `/user/profile` | user | JWT |
| `/user/change-password` | user | JWT |
| `/user/users` | user | admin |
| `/user/users/<id>` | user | admin |
| `/user/users/<id>/roles` | user | admin |
| `/user/users/<id>/lock` | user | admin |
| `/user/users/<id>/unlock` | user | admin |
| `/user/security/lock-status/<id>` | user | admin |
| `/forms/` POST/GET | form | JWT |
| `/forms/<id>` GET/PUT/DELETE | form | JWT + form perm |
| `/forms/<id>/publish` | form | JWT + form:edit |
| `/forms/<id>/clone` | form | JWT + form:view |
| `/forms/templates` | form | JWT |
| `/forms/import` | form | JWT |
| `/forms/<id>/sections` CRUD | form | JWT |
| `/forms/<id>/sections/reorder` | form | JWT |
| `/forms/<id>/responses` POST | form | JWT + form:submit |
| `/forms/<id>/responses` GET | form | JWT + form:view_responses |
| `/forms/<id>/responses` DELETE | form | admin (soft delete + confirm) |
| `/forms/<id>/export/csv` | form | JWT + form:view_responses |
| `/forms/<id>/export/json` | form | JWT + form:view_responses |
| `/forms/export/bulk` | form | JWT |
| `/forms/export/bulk/<job_id>` | form | JWT |
| `/forms/slug-available` | form | JWT |
| `/forms/<id>/share` | form | admin |
| `/forms/<id>/archive` | form | admin |
| `/forms/<id>/restore` | form | admin |
| `/forms/<id>/toggle-public` | form | admin |
| `/forms/<id>/responses/count` | form | JWT |
| `/forms/<id>/responses/last` | form | JWT |
| `/forms/<id>/check-duplicate` | form | JWT |
| `/forms/<id>/expire` | form | admin |
| `/forms/expired` | form | admin |
| `/forms/<id>/summarize` | form | JWT |
| `/forms/<id>/summarize-stream` (SSE) | form | JWT |
| `/forms/<id>/public-submit` | form | **none** |
| `/forms/<id>/history` | form | JWT |
| `/forms/<id>/next-action` | form | JWT |
| `/forms/<id>/access-control` | form | JWT |
| `/forms/<id>/access-policy` POST/PUT | form | JWT + manage_access |
| `/forms/<id>/permissions` GET/POST | form/permissions | JWT + form:edit |
| `/forms/<id>/analytics` | form/analytics | JWT + form:view |
| `/forms/<id>/analytics/summary` | form/analytics | JWT + form:view |
| `/forms/<id>/analytics/timeline` | form/analytics | JWT + form:view |
| `/forms/<id>/analytics/distribution` | form/analytics | JWT + form:view |
| `/forms/<id>/files/<qid>/<filename>` | form/files | JWT optional (public if is_public) |
| `/forms/upload` | form/files | JWT |
| `/forms/signatures` | form/files | JWT |
| `/forms/<id>/questions/<qid>/hooks/trigger` | form/hooks | JWT |
| `/forms/<id>/sections/<sid>/hooks/trigger` | form/hooks | JWT |
| `/forms/<id>/hooks/trigger` | form/hooks | JWT |
| `/forms/projects/<pid>/hooks/trigger` | form/hooks | JWT |
| `/forms/external-hooks/register` | form/hooks | JWT |
| `/forms/external-hooks/<id>/approve` | form/hooks | JWT + approve_hooks perm |
| `/forms/conditions/evaluate` | form/validation | JWT |
| `/forms/translations` GET/POST | translation | JWT |
| `/forms/translations/languages` | translation | JWT |
| `/forms/translations/preview` | translation | JWT |
| `/forms/translations/jobs` GET/POST | translation | JWT |
| `/forms/translations/jobs/<id>` | translation | JWT |
| `/forms/translations/jobs/<id>/cancel` | translation | JWT |
| `/forms/translations/jobs/<id>/content` | translation | JWT |
| `/custom-fields/` CRUD | library | JWT |
| `/templates/` CRUD (alias) | library | JWT |
| `/ai/health` | ai | **none** |
| `/ai/search/semantic-search` | nlp_search | JWT |
| `/ai/search/search-history` | nlp_search | JWT |
| `/dashboards/` POST | dashboard | JWT + dashboard:create |
| `/dashboards/<slug>` GET | dashboard | JWT + dashboard:view |
| `/dashboards/<id>` PUT | dashboard | JWT + dashboard:edit |
| `/dashboard-settings/settings` GET/PUT | dashboard_settings | JWT |
| `/dashboard-settings/reset` | dashboard_settings | JWT |
| `/dashboard-settings/widgets` GET | dashboard_settings | JWT |
| `/dashboard-settings/widgets/<id>` PUT/DELETE | dashboard_settings | JWT |
| `/dashboard-settings/widgets/positions` | dashboard_settings | JWT |
| `/dashboard-settings/layout` | dashboard_settings | JWT |
| `/analytics/dashboard` | analytics | manager |
| `/analytics/summary` | analytics | admin |
| `/analytics/trends` | analytics | JWT (stub) |
| `/workflows/` POST/GET | workflow | JWT |
| `/workflows/<id>` GET/PUT/DELETE | workflow | JWT |
| `/workflows/pending` | workflow | JWT (stub) |
| `/webhooks/deliver` | webhooks | manager |
| `/webhooks/<id>/status` | webhooks | JWT |
| `/sms/single` | sms | manager, 10/min |
| `/sms/otp` | sms | admin, 5/min |
| `/sms/health` | sms | JWT |
| `/external/uhid/<uhid>` | external_api | JWT (stub) |
| `/external/employee/<id>` | external_api | JWT (stub) |
| `/external/mail` | external_api | JWT (stub) |
| `/external/sms` | external_api | JWT (stub) |
| `/admin/system-settings/` GET/PUT | system_settings | admin |
| `/admin/env-config/` GET/PUT | env_config | **superadmin only** |
| `/system/event-health` | system | superadmin |
| `/system/analytics-trends/<org_id>` | system | admin |
| `/api/v1/view/<form_id>` | view | **none** (public forms only) |
| `/health` | health | **none** |

Aliases: all `/user/*` routes also work at `/users/*`.

---

## 9. Key Behavioral Rules Agents Must Know

### Async Operations Return 202
`publish`, `clone`, `bulk_export`, `translation_jobs` → respond immediately with `{"task_id": "..."}` and 202. No polling endpoint exists yet.

### Translation Jobs Are Celery Tasks
`POST /forms/translations/jobs` dispatches `async_process_translation_job.delay(job_id)`. Do not revert this to threading.

### `delete_all_responses` Is Soft Delete + Requires Confirmation
Request body must include `{"confirm": "DELETE_ALL"}`. The operation sets `is_deleted=True`, does not hard-delete.

### Form Lifecycle States
`draft` → (publish) → `published` → (archive) → `archived` → (restore) → `draft`
Deletion sets `is_deleted=True` — it is NOT a state change.

### Superadmin Bypasses Org Scope
Analytics routes and other admin routes show system-wide data to `superadmin`. All others are scoped to their `organization_id`. Check `jwt_data.get("role") == "superadmin"` before deciding to scope queries.

### JWT Dual-Mode Auth
Tokens are accepted via `Authorization: Bearer <token>` header OR via `access_token` HttpOnly cookie. Cookie mode requires `X-CSRF-TOKEN-ACCESS` header on state-changing requests.

### Public Forms
`POST /forms/<id>/public-submit` — no auth, no org scope. Form must have `is_public=True` and `status="published"` and not be expired/scheduled.

---

## 10. Running and Testing

```bash
make up-dev        # Start with live reload
make restart       # Restart backend + celery after code changes (dev)
make test          # Run pytest inside container
make test-cov      # With coverage
make lint          # flake8 + black + mypy
make shell         # bash in backend container
make logs          # Follow backend logs

# Single test file
docker compose run --rm backend pytest tests/test_auth_service.py -v

# Single test method
docker compose run --rm backend pytest tests/test_auth_service.py::TestClass::test_method -v
```

Tests use real MongoDB + Redis via `testcontainers`. No mocking of database. `APP_ENV=testing` is set automatically by `pytest.ini`. Coverage targets: `services/` and `routes/`.

---

## 11. Environment Variables

| Variable | Required | Notes |
|----------|----------|-------|
| `APP_ENV` | yes | `development` / `testing` / `production` |
| `MONGODB_URI` | yes | Full MongoDB connection string |
| `REDIS_HOST` / `REDIS_PORT` | yes | Redis host and port |
| `JWT_SECRET_KEY` | yes | Must be changed in production |
| `ALLOWED_ORIGINS` | yes | CORS allowed origins list |
| `ELASTICSEARCH_URL` | no | For search |
| `AI_PROVIDER` | no | `local` / `ollama` / `openai` (default: `ollama`) |
| `SENTRY_DSN` | no | Error tracking |

Copy `.env.example` to `.env` before first run.

---

## 12. Swagger / API Documentation

Every new route **must** have a `@swag_from({...})` decorator:

```python
from flasgger import swag_from

@bp.route("/resource", methods=["POST"])
@swag_from({
    "tags": ["YourTag"],
    "parameters": [
        {"name": "body", "in": "body", "schema": {"$ref": "#/definitions/YourSchema"}}
    ],
    "responses": {
        "201": {"description": "Resource created"},
        "400": {"description": "Validation error"},
        "401": {"description": "Unauthorized"}
    }
})
@jwt_required()
def create_resource():
    ...
```

---

## 13. Known Stubs / Not Implemented

These endpoints return empty/placeholder responses — do not treat them as bugs, and do not build features that depend on them without implementing them first:

| Endpoint | Stub behavior |
|----------|--------------|
| `GET /analytics/trends` | Returns `{"trends": []}` always |
| `GET /forms/micro-info` | Returns `{"data": {}}` always |
| Anomaly stats and feedback routes | All stubs |
| `GET /workflows/pending` | Returns `{"items": [], "total": 0}` always |
| `GET /external/uhid/<uhid>` | Returns empty `data: {}` placeholder |
| `GET /external/employee/<id>` | Returns empty `data: {}` placeholder |
| `POST /external/mail` | Returns `"Mail sent successfully"` without sending |
| `POST /external/sms` | Returns `"SMS sent successfully"` without sending |
| `GET /forms/<id>/analytics` field `completionRate` | Hardcoded to `0.85` — not calculated |

---

### 14. Known Remaining Issues

| ID | Issue | File |
|----|-------|------|
| R-09 | No Celery task status poll endpoint | Architecture gap |
| R-13 | `anomaly_bp` / `nlp_search_bp` / `dashboard_settings_bp` have redundant `url_prefix` in constructor | `anomaly.py`, `nlp_search.py`, `dashboard_settings_route.py` |
| B-07 | Redundant `url_prefix` in `dashboard_settings_bp` constructor | `routes/v1/dashboard_settings_route.py:9` |

See `docs/backend-doc/ISSUES_SUMMARY.md` for full detail and remediation plan.


---

## 15. Full Documentation Index

| Document | What it covers |
|----------|---------------|
| `docs/backend-doc/overview.md` | Architecture, tech stack, middleware, service layer, Celery, logging, data models |
| `docs/backend-doc/policies.md` | API design rules, auth/authz policy, security policy, contributor rules |
| `docs/backend-doc/integration-guide.md` | Every API endpoint with request/response examples |
| `docs/backend-doc/risks-and-gaps.md` | Security risks, known gaps, remediation status |
| `docs/backend-doc/ISSUES_SUMMARY.md` | Full audit of doc gaps, code bugs, and remediation plan |
| `docs/backend-doc/blueprints/*.md` | Per-blueprint deep reference (note: workflow, dashboard-settings, external-api, admin routes not yet written) |
| `docs/backend-doc/appendices/route-inventory.md` | Route table (incomplete — missing ~35 routes added after last doc run) |
| `docs/backend-doc/appendices/auth-permission-matrix.md` | Role hierarchy, form ACL, decorators |
| `docs/backend-doc/appendices/lifecycle-matrices.md` | State machines for forms, responses, tokens, jobs |
| `docs/backend-doc/appendices/glossary.md` | Definitions for all domain terms |
| `docs/backend-doc/appendices/legacy-route-mapping.md` | Alias routes, prefix conflicts |
| `docs/backend-doc/appendices/onboarding-order.md` | Reading order by role |
