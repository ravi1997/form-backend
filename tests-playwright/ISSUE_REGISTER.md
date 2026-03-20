# Fallback Issue Register

GitHub issue creation was not completed from this environment, so these are copy-paste-ready issue bodies for confirmed engineering defects.

## 1. Fix Celery worker task registration and Flask app bootstrap

Title: `fix(celery): register form tasks and initialize Flask/Mongo context for background jobs`

Severity: High

Affected area:
- `config/celery.py`
- `tasks/form_tasks.py`

Failing test references:
- `tests/api/responses/responses.spec.ts`
- `tests/flows/form-submission-flow.spec.ts`

Problem:
- Form publish jobs were accepted but never executed correctly because the worker did not register form tasks and later lacked Flask/Mongo initialization when tasks did execute.

Expected:
- Publish/background jobs run successfully with the same app/database bootstrap as API requests.

Actual:
- Workers either never saw the task or failed with `You have not defined a default connection`.

Acceptance criteria:
- Form publish tasks are registered in Celery
- Worker consumes the default queue
- Worker task execution has Flask app context and Mongo connectivity
- Publish-dependent flows pass end to end

## 2. Fix response submission path assumptions and version lookup robustness

Title: `fix(responses): harden submission flow for published form version lookup`

Severity: High

Affected area:
- `routes/v1/form/responses.py`
- `services/response_service.py`
- `models/Response.py`
- `models/Form.py`

Failing test references:
- `tests/api/responses/responses.spec.ts`
- `tests/flows/form-submission-flow.spec.ts`

Problem:
- Response submission assumed a `project` field on `Form` and relied on fragile `active_version` dereferencing/lookup behavior.

Expected:
- Published forms resolve their active snapshot consistently and accept or reject submissions deterministically.

Actual:
- Submission failed with `Form.project` attribute errors and inconsistent form-version resolution.

Acceptance criteria:
- Submission route no longer assumes `Form.project`
- Active version lookup is stable for published forms
- Valid response flow no longer crashes on version dereference issues

## 3. Fix admin system-settings singleton race/lookup behavior

Title: `fix(admin): make system settings singleton retrieval idempotent`

Severity: Medium

Affected area:
- `models/SystemSettings.py`
- `routes/v1/admin/system_settings_route.py`

Failing test references:
- `tests/security/rbac.spec.ts`

Problem:
- Admin reads could fail with duplicate-key or empty-document lookup behavior while creating/fetching the default settings row.

Expected:
- Admin GET for system settings returns a stable singleton document.

Actual:
- Endpoint could return `500` due duplicate-key creation attempts or failed hydration.

Acceptance criteria:
- Default settings creation is atomic
- Existing singleton is returned safely
- Admin endpoint no longer returns `500` for normal reads

## 4. Fix auth login invalid-JSON handling

Title: `fix(auth): return 400 for invalid JSON payloads instead of 500`

Severity: Medium

Affected area:
- `routes/v1/auth_route.py`

Failing test references:
- `tests/negative/error-handling.spec.ts`

Problem:
- Invalid JSON request bodies could become raw strings and trigger attribute errors.

Expected:
- Invalid JSON is rejected with a client error response.

Actual:
- Login could return `500` with `'str' object has no attribute 'get'`.

Acceptance criteria:
- Invalid JSON to login returns `400`
- No server exception is logged for malformed JSON bodies
