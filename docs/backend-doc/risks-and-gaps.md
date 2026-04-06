# Known Risks, Limitations, and Gaps — RIDP Form Platform

## 1. Purpose

This document catalogs all identified architectural risks, security gaps, unimplemented stubs, and behavioral limitations in the RIDP Form Platform backend. It is written for security reviewers, senior engineers, and QA teams performing risk assessments.

Each item has: a risk ID, severity rating, description, affected area, evidence from the code, and recommended remediation.

**Last updated:** 2026-04-06 — reflects fixes applied after initial documentation (R-01 through R-09 below incorporate resolved items).

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

### R-01: Translation Jobs — Threading → Celery Migration **[RESOLVED]**

**Severity:** ~~HIGH~~ → **FIXED**

**Area:** `routes/v1/form/translation.py`

**Previous state:** Translation jobs ran in `threading.Thread`, with no retry capability, no survival across worker restarts, and no Celery visibility.

**Current state (fixed):** Jobs now dispatch to a Celery task:
```python
from tasks.form_tasks import async_process_translation_job
async_process_translation_job.delay(str(job.id))
```

Jobs benefit from Celery retry policy (3 retries, 300s backoff), worker resilience, and queue monitoring.

---

### R-02: Dashboard Widget Data Not Tenant-Scoped **[RESOLVED]**

**Severity:** ~~HIGH~~ → **FIXED**

**Area:** `routes/v1/dashboard_route.py` — `resolve_widget_data()`

**Previous state:** `match_query` for widget aggregation did not include `organization_id`, allowing potential cross-tenant data leakage.

**Current state (fixed):**
```python
match_query = {
    "form": widget.form_id,
    "is_deleted": False,
    "organization_id": org_id
}
```

---

### R-03: Analytics Endpoints Had No Tenant Scope **[RESOLVED]**

**Severity:** ~~HIGH~~ → **FIXED**

**Area:** `routes/v1/analytics_route.py`

**Previous state:** `Form.objects()` and `FormResponse.objects()` were called without `organization_id` filters, returning system-wide counts to any privileged user.

**Current state (fixed):** Queries now conditionally scope by `org_id` from JWT. `superadmin` role sees system-wide stats; all other roles see only their organization's data:
```python
jwt_data = get_jwt()
org_id = jwt_data.get("org_id")
role = jwt_data.get("role")

kwargs = {}
if role != "superadmin" and org_id:
    kwargs["organization_id"] = org_id

total_forms = Form.objects(**kwargs).count()
```

---

### R-04: Missing Imports in `form.py` **[RESOLVED]**

**Severity:** ~~MEDIUM~~ → **FIXED**

**Area:** `routes/v1/form/form.py`

**Previous state:** `Section` and `BaseSerializer` were used without import, causing `NameError` on `POST /forms/import` and `POST /forms/<id>/sections`.

**Current state (fixed):** Both are now explicitly imported at the top of `form.py`:
```python
from utils.response_helper import success_response, error_response, BaseSerializer
from models import Section
```

---

### R-05: Missing Logger Imports in `summarization.py` **[RESOLVED]**

**Severity:** ~~MEDIUM~~ → **FIXED**

**Area:** `routes/v1/form/summarization.py`

**Previous state:** `app_logger` and `error_logger` were used without import.

**Current state (fixed):**
```python
from utils.security_helpers import get_current_user
from logger.unified_logger import app_logger, error_logger
```

---

### R-06: `delete_all_responses` Was a Hard Delete **[RESOLVED]**

**Severity:** ~~HIGH~~ → **FIXED**

**Area:** `routes/v1/form/additional.py` — `delete_all_responses()`

**Previous state:** `FormResponse.objects(form=form.id).delete()` permanently removed all response documents with no confirmation and no undo.

**Current state (fixed):**
- Requires explicit confirmation in request body: `{"confirm": "DELETE_ALL"}`
- Uses soft-delete: `update(set__is_deleted=True, set__deleted_by=str(current_user.id))`
- Enforces org isolation: `Form.objects.get(id=form_id, organization_id=current_user.organization_id)`

```python
data = request.get_json(silent=True) or {}
if data.get("confirm") != "DELETE_ALL":
    return error_response(message="Confirmation required ...", status_code=400)

deleted_count = FormResponse.objects(form=form.id, is_deleted=False).update(
    set__is_deleted=True, set__deleted_by=str(current_user.id)
)
```

---

### R-07: `advanced_responses_bp` Lookups Not Tenant-Scoped **[RESOLVED]**

**Severity:** ~~MEDIUM~~ → **FIXED**

**Area:** `routes/v1/form/advanced_responses.py`

**Previous state:** All `Form.objects.get(id=form_id)` calls lacked `organization_id`, exposing form existence from other organizations.

**Current state (fixed):** All form lookups now include `organization_id=current_user.organization_id`:
```python
form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)
```
Applied to `fetch_external_form_data`, `fetch_same_form_data`, `fetch_specific_questions`, `fetch_response_meta`, `get_form_access_control`, and `update_access_policy`.

---

### R-08: `view_route.py` Rendered Any Form Without Authentication **[PARTIALLY RESOLVED]**

**Severity:** MEDIUM → **PARTIALLY FIXED**

**Area:** `routes/v1/view_route.py` — `view_form()`

**Previous state:** Any form UUID could be rendered in a browser by anyone with no authentication and no org scope.

**Current state (partially fixed):** A `is_public` check was added:
```python
form = Form.objects.get(id=form_id)
if not getattr(form, 'is_public', False):
    return "Form is private or requires authentication", 403
```

**Remaining gap:** The `is_public` check prevents rendering private forms, which is a significant improvement. However:
- No `organization_id` filter is applied — cross-tenant form existence is still revealed via 404 vs 403 distinction
- No `is_deleted` filter — soft-deleted forms still render if `is_public = True`
- Error responses are plain text (inconsistent with JSON API)

---

### R-09: Async Task Status Poll Not Available in Public API

**Severity:** LOW

**Area:** Architecture gap

**Description:**
Three operations return 202 with a `task_id` (publish, clone, bulk export). There is no endpoint for polling Celery task status. Clients receive a task ID but have no mechanism to determine completion or failure other than checking form/job state indirectly.

**Impact:** Frontend cannot implement reliable progress tracking for async operations.

**Recommended fix:** Implement `GET /forms/tasks/<task_id>` using Celery's `AsyncResult` API, or use WebSocket/SSE for push notifications.

---

### R-10: `analytics_bp` Trends Endpoint Is a Stub

**Severity:** LOW

**Area:** `routes/v1/analytics_route.py` — `get_trends()`

**Description:**
`GET /analytics/trends` always returns `{ "trends": [] }` regardless of parameters or data.

**Impact:** Any frontend feature relying on trends data receives an empty array.

---

### R-11: `advanced_responses_bp` `micro_info` Is a Placeholder

**Severity:** LOW

**Area:** `routes/v1/form/advanced_responses.py` — `micro_info()`

**Description:**
`GET /forms/micro-info` always returns `{"message": "Micro information retrieved", "data": {}}`. Marked as "Placeholder" in docstring.

---

### R-12: anomaly_stats and anomaly_feedback Are Stubs

**Severity:** LOW

**Area:** `routes/v1/form/anomaly.py`

**Description:**
Anomaly statistics and feedback endpoints are stub implementations returning empty or placeholder data.

---

### R-13: Blueprint URL Prefix Conflicts (`anomaly_bp`, `nlp_search_bp`)

**Severity:** MEDIUM

**Area:** Blueprint constructors in `anomaly.py`, `nlp_search.py`

**Description:**
These blueprints define `url_prefix` in their `Blueprint()` constructor AND are registered with a different prefix in `routes/__init__.py`. Flask uses the registration-time prefix and ignores the constructor prefix. This discrepancy makes the code misleading and could cause confusion during maintenance.

**Impact:** Routes work correctly (registration prefix wins), but a developer reading the Blueprint constructor would see the wrong URL prefix.

**Recommended fix:** Remove `url_prefix` from `Blueprint()` constructors and set it exclusively at registration time.

---

## 4. Security Summary

| Category | Status |
|----------|--------|
| Authentication (JWT) | Implemented, dual-mode (header + cookie) |
| CSRF protection | Implemented for cookie mode |
| Password hashing | Implemented (bcrypt) |
| Input validation | Implemented (Pydantic + WAF) |
| Rate limiting | Implemented (Redis-backed) |
| Multi-tenancy | Implemented; previously identified gaps in analytics and dashboard widgets are now fixed |
| Audit logging | Implemented for all state-changing operations |
| Token revocation | Implemented (Redis blocklist) |
| Account lockout | Implemented (failed login counter + lock_until) |
| HTTPS enforcement | Implemented via Talisman (production) |
| PII masking in logs | Implemented via logging filter |
| View route isolation | Partially fixed — `is_public` check added; cross-tenant existence still inferable |

---

## 5. Reliability Summary

| Category | Status |
|----------|--------|
| Celery async tasks | Implemented; retries configured |
| Translation jobs | Fixed — now dispatched via Celery (was threads) |
| Database failure | Application exits in non-dev if MongoDB unavailable |
| Redis failure | Application exits in non-dev if Redis unavailable |
| Async task visibility | No public status poll endpoint (R-09) |
| Soft delete | Implemented everywhere including `delete_all_responses` (now soft + confirmation required) |
| Form versioning | Implemented; snapshots are immutable |

---

## 6. Recommended Remediation Priority

| Priority | Risk | Action |
|----------|------|--------|
| P1 | R-08 (view route partial fix) | Add `is_deleted` filter; normalize error responses |
| P2 | R-13 (prefix conflict) | Remove constructor `url_prefix` from anomaly and nlp_search blueprints |
| P2 | R-09 (no task status poll) | Implement task status endpoint |
| P3 | R-10, R-11, R-12 (stubs) | Implement or remove stubs |
