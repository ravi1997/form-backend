# Known Risks, Limitations, and Gaps — RIDP Form Platform

## 1. Purpose

This document catalogs all identified architectural risks, security gaps, unimplemented stubs, and behavioral limitations in the RIDP Form Platform backend. It is written for security reviewers, senior engineers, and QA teams performing risk assessments.

Each item has: a risk ID, severity rating, description, affected area, evidence from the code, and recommended remediation.

---

## 2. Severity Ratings

| Level | Meaning |
|-------|---------|
| CRITICAL | Data breach, data loss, or complete auth bypass possible |
| HIGH | Significant security or reliability impact |
| MEDIUM | Noticeable functional limitation or partial security gap |
| LOW | Minor issue, edge case, or quality concern |

---

## 3. Risk Register

---

### R-01: Translation Jobs Use Python Threads, Not Celery

**Severity:** HIGH

**Area:** `routes/v1/form/translation.py` — `handle_jobs()` POST handler

**Description:**
Translation jobs are processed using `threading.Thread` directly within the Flask request handler, using the Flask application object passed by reference (`current_app._get_current_object()`). This means:
- Translation jobs do not survive Gunicorn worker restarts or process recycling
- If the worker process crashes mid-job, the job is stuck in `inProgress` state permanently with no recovery mechanism
- No retry capability exists for failed language translations — failure is logged but execution continues
- Thread count is unbounded — many concurrent translation requests could spawn many threads and exhaust worker resources
- Translation jobs have no queue, no backpressure, and no visibility into system load

**Code evidence:**
```python
thread = threading.Thread(
    target=process_translation_job,
    args=(job.id, current_app._get_current_object()),
)
thread.start()
```

**Impact:** Translation jobs may silently fail in production under load or after restarts. Users will see jobs stuck in `inProgress` or `failed` state with no auto-recovery.

**Recommended fix:** Migrate `process_translation_job` to a Celery task in the `celery` queue with standard retry policy (3 retries, 300s backoff). The `TranslationJob.status` update pattern already exists and maps cleanly to Celery task lifecycle.

---

### R-02: Blueprint URL Prefix Conflicts (Anomaly and NLP Search)

**Severity:** MEDIUM

**Area:** `routes/v1/form/anomaly.py`, `routes/v1/form/nlp_search.py`

**Description:**
The `anomaly_bp` and `nlp_search_bp` blueprints define a `url_prefix` in their `Blueprint()` constructor. These prefixes may conflict with the prefix assigned during blueprint registration in `routes/__init__.py`. In Flask, when a blueprint is registered with a `url_prefix` AND the blueprint itself has a `url_prefix`, the registration-time prefix is used and the constructor-time prefix is ignored. This discrepancy means the actual route paths may differ from what the code appears to declare.

**Code evidence:**
```python
# In nlp_search.py:
nlp_search_bp = Blueprint("nlp_search", __name__, url_prefix="/ai/search")

# In routes/__init__.py:
app.register_blueprint(nlp_search_bp, url_prefix=f"{base_prefix}/api/v1/ai/search")
```

**Impact:** Routes may be registered at unexpected paths. Frontend and QA must verify actual route paths by inspecting the running app's route map (`flask routes` or Swagger UI) rather than reading the code.

**Recommended fix:** Remove `url_prefix` from `Blueprint()` constructors for these blueprints. Set the prefix exclusively in `register_blueprints()`.

---

### R-03: Dashboard Widget Data Not Tenant-Scoped

**Severity:** HIGH

**Area:** `routes/v1/dashboard_route.py` — `resolve_widget_data()`

**Description:**
When resolving widget data, the `match_query` for `FormResponse` aggregation does NOT include `organization_id`. The query filters on `form` and `is_deleted` only:

```python
match_query = {
    "form": widget.form_id,
    "is_deleted": False
}
```

The `org_id` is passed to the function but not used in the MongoDB query. This means a widget configured with a `form_id` that belongs to another organization would return that organization's response data.

**Impact:** Potential cross-tenant data leakage in dashboard widgets. An attacker who can create or modify a dashboard widget and set an arbitrary `form_id` could view response counts or data from any organization's form.

**Recommended fix:** Add `"organization_id": org_id` to the `match_query` dict in `resolve_widget_data()`.

---

### R-04: Analytics Endpoints Have No Tenant Scope

**Severity:** HIGH

**Area:** `routes/v1/analytics_route.py` — `get_dashboard_stats()`, `get_summary()`

**Description:**
Both `GET /analytics/dashboard` and `GET /analytics/summary` query `Form.objects()` and `FormResponse.objects()` without any `organization_id` filter:

```python
total_forms = Form.objects().count()
total_responses = FormResponse.objects(is_deleted=False).count()
```

This returns system-wide totals (all organizations combined) to any user with the `admin`, `superadmin`, or `manager` role.

**Impact:** Admins of Organization A see total form/response counts from all organizations in the system. This is an information disclosure vulnerability.

**Note:** This may be intentional for a global admin view, but it is not documented as such and violates the stated multi-tenant isolation policy.

**Recommended fix:** Filter by `organization_id = get_jwt().get("org_id")` unless the user is a superadmin requesting system-wide stats. Document the exception explicitly.

---

### R-05: `import_form` References `Section` Without Import

**Severity:** MEDIUM

**Area:** `routes/v1/form/form.py` — `import_form()`

**Description:**
The `import_form` route references the `Section` model class in the `import_sections()` nested function without an explicit import:

```python
s = Section(
    title=s_data.get("title"),
    ...
)
```

`Section` is not imported at the top of `form.py`. This will raise a `NameError` at runtime when `import_form` is called with a payload containing sections.

**Impact:** The `POST /forms/import` endpoint will error with 500 (NameError) for any import payload that includes sections. The endpoint may appear to work for payloads without sections (which create a form with no sections).

**Recommended fix:** Add `from models.Section import Section` or `from models import Section` at the top of `form.py`, or inside the `import_form` function.

---

### R-06: `create_form_section` References `BaseSerializer` Without Import

**Severity:** MEDIUM

**Area:** `routes/v1/form/form.py` — `create_form_section()`

**Description:**
`create_form_section()` calls `BaseSerializer.clean_dict(...)` but `BaseSerializer` is not imported at the module level in `form.py`. This will raise a `NameError` when a section creation is attempted.

**Impact:** `POST /forms/<form_id>/sections` returns 500 (NameError) at runtime.

**Recommended fix:** Add `from utils.response_helper import BaseSerializer` (or wherever `BaseSerializer` is defined) to `form.py`.

---

### R-07: `summarization.py` References `app_logger` and `error_logger` Without Import

**Severity:** MEDIUM

**Area:** `routes/v1/form/summarization.py`

**Description:**
`summarization.py` uses `app_logger` and `error_logger` directly but does not import them. The file imports are at the bottom of the module-level scope — this works in Python only if the names are available from the blueprint's `__init__` module scope or a star import. If they are not available, routes will raise `NameError`.

**Recommended fix:** Explicitly import at the top of `summarization.py`:
```python
from logger.unified_logger import app_logger, error_logger
```

---

### R-08: `view_route.py` Has No Organization Scope

**Severity:** MEDIUM

**Area:** `routes/v1/view_route.py`

**Description:**
The HTML render routes (login page and form viewer) query `Form.objects.get(id=form_id)` without any `organization_id` filter and without authentication. Any form ID in the system can be accessed via the view routes.

**Impact:** An anonymous user who knows or guesses a form UUID can render it in the browser. This may expose form structure (labels, question text) from any organization.

**Note:** HTML rendering is generally used for embedded/public forms. If this is intentional, the access policy should be explicitly documented and the rendered output should not include response data.

**Recommended fix:** If public rendering is intentional, restrict to `is_public = True` forms. Otherwise add authentication.

---

### R-09: `advanced_responses_bp` fetch/external Does Not Scope to Organization

**Severity:** MEDIUM

**Area:** `routes/v1/form/advanced_responses.py` — `fetch_external_form_data()`

**Description:**
The `/forms/fetch/external` route looks up the target form using `Form.objects.get(id=form_id)` without `organization_id` filtering:

```python
form = Form.objects.get(id=form_id)
```

This means a user from Organization A could query forms belonging to Organization B, subject only to the `has_form_permission` check. Since the form belongs to Organization B, the permission check would likely fail — but the form document is fetched before the check, which means existence is revealed.

**Recommended fix:** Pass `organization_id=current_user.organization_id` to all Form lookups in `advanced_responses.py`.

---

### R-10: Translation Job Cancel Does Not Stop Running Thread

**Severity:** MEDIUM

**Area:** `routes/v1/form/translation.py` — `cancel_job()` and `process_translation_job()`

**Description:**
Cancelling a job sets `job.status = "cancelled"` in MongoDB. The background thread checks this periodically (`job.reload().status == "cancelled"` between languages). However:
- There is no immediate termination mechanism
- The thread may continue processing for the current language before noticing the cancellation
- Python threads cannot be forcibly terminated

**Impact:** After cancellation, the job may continue processing 1 more language before stopping. Partially completed translations may be saved to the form.

---

### R-11: Async Task Status Poll Not Available in Public API

**Severity:** LOW

**Area:** Architecture gap

**Description:**
Three operations return 202 with a `task_id` (publish, clone, bulk export). There is no documented endpoint for polling Celery task status. Clients receive a task ID but have no way to determine completion or failure short of checking the form/job status indirectly.

**Impact:** Frontend cannot implement reliable progress tracking for async operations.

**Recommended fix:** Implement `GET /forms/tasks/<task_id>` using Celery's `AsyncResult` API, or use WebSocket/SSE for push notifications.

---

### R-12: `delete_all_responses` Is a Hard (Permanent) Delete

**Severity:** HIGH (operational risk)

**Area:** `routes/v1/form/additional.py` — `delete_all_responses()`

**Description:**
`DELETE /forms/<form_id>/responses` calls `FormResponse.objects(form=form.id).delete()` which permanently removes documents from MongoDB. This bypasses the soft-delete pattern used everywhere else. There is no confirmation prompt, no dry-run, and no undo capability.

**Impact:** An admin with valid credentials can permanently destroy all response data for any form in their organization in a single request.

**Recommended fix:** Require explicit confirmation token in request body. Add a soft-delete/archive option. Implement a time-delayed hard delete with a grace period.

---

### R-13: `analytics_bp` Trends Endpoint Is a Stub

**Severity:** LOW

**Area:** `routes/v1/analytics_route.py` — `get_trends()`

**Description:**
`GET /analytics/trends` always returns `{ "trends": [] }` regardless of parameters or data. It is marked with `@jwt_required()` but performs no queries.

**Impact:** Any frontend feature relying on trends data receives an empty array.

---

### R-14: `advanced_responses_bp` `micro_info` Is a Placeholder

**Severity:** LOW

**Area:** `routes/v1/form/advanced_responses.py` — `micro_info()`

**Description:**
`GET /forms/micro-info` returns `{"message": "Micro information retrieved", "data": {}}` unconditionally. It is marked as "Placeholder" in the docstring.

---

### R-15: anomaly_stats and anomaly_feedback Are Stubs

**Severity:** LOW

**Area:** `routes/v1/form/anomaly.py`

**Description:**
Based on the file listing and the summary from the previous analysis, anomaly statistics and feedback endpoints are stub implementations that return empty or placeholder data.

---

## 4. Security Summary

| Category | Status |
|----------|--------|
| Authentication (JWT) | Implemented, dual-mode (header + cookie) |
| CSRF protection | Implemented for cookie mode |
| Password hashing | Implemented (bcrypt) |
| Input validation | Implemented (Pydantic + WAF) |
| Rate limiting | Implemented (Redis-backed) |
| Multi-tenancy | Largely implemented; gaps in analytics (R-04) and dashboard widgets (R-03) |
| Audit logging | Implemented for all state-changing operations |
| Token revocation | Implemented (Redis blocklist) |
| Account lockout | Implemented (failed login counter + lock_until) |
| HTTPS enforcement | Implemented via Talisman (production) |
| PII masking in logs | Implemented via logging filter |

---

## 5. Reliability Summary

| Category | Status |
|----------|--------|
| Celery async tasks | Implemented; retries configured |
| Translation jobs | High risk — uses threads, no retry (R-01) |
| Database failure | Application exits in non-dev if MongoDB unavailable |
| Redis failure | Application exits in non-dev if Redis unavailable |
| Async task visibility | No public status poll endpoint (R-11) |
| Soft delete | Implemented everywhere except `delete_all_responses` (R-12) |
| Form versioning | Implemented; snapshots are immutable |

---

## 6. Recommended Remediation Priority

| Priority | Risk | Action |
|----------|------|--------|
| P0 | R-03 (dashboard data leakage) | Add `organization_id` to widget match query |
| P0 | R-04 (analytics unscoped) | Scope analytics queries to org_id |
| P1 | R-01 (threading) | Migrate translation jobs to Celery |
| P1 | R-12 (hard delete) | Add confirmation requirement + soft option |
| P2 | R-05 (NameError in import) | Add missing `Section` import |
| P2 | R-06 (NameError in sections) | Add missing `BaseSerializer` import |
| P2 | R-07 (NameError in summarization) | Add missing logger imports |
| P2 | R-08 (view route unscoped) | Scope to `is_public` forms or add auth |
| P3 | R-02 (prefix conflict) | Remove constructor url_prefix |
| P3 | R-11 (no task status poll) | Implement task status endpoint |
| P4 | R-13, R-14, R-15 (stubs) | Implement or remove stubs |
