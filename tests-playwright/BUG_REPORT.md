# Playwright QA Bug Report

## Execution Summary
- Scope: `apps/form-backend` only
- Test harness: Playwright API suite in `tests-playwright`
- Final stable command: `npx playwright test --reporter=list --workers=1`
- Final result: `34 passed`

## Initial Failure Landscape
- Startup/config failures
  - Mongo auth mismatch against authenticated `shared-mongo`
  - Logging formatter crashes when `request_id` was missing
- Auth/runtime failures
  - Login cookie helpers were called on tuple responses
  - QuerySet implementation referenced a nonexistent `_model` attribute
- Form/runtime failures
  - Missing imports and invalid create/update assumptions in form routes
  - `PaginatedResult` lacked `to_dict()`
  - Permission helper used `user.role` instead of `user.roles`
- Async/background failures
  - Celery worker did not register or consume form/AI tasks
  - Celery tasks executed without Flask/Mongo bootstrap
- Response flow failures
  - Response route assumed `Form.project` existed
  - Published form version references were inconsistent across request/write paths
- Admin/error handling failures
  - Invalid JSON to login crashed with `500`
  - Admin system-settings endpoint could `500` on duplicate/default singleton creation

## Confirmed Product Bugs Fixed
1. Auth setup and login flow
   - Fixed tuple/cookie misuse in `auth_route`
   - Added graceful invalid-JSON handling in login
2. MongoEngine queryset bug
   - Replaced `_model` usage with `_document`
3. Logging robustness
   - Ensured file handlers receive `request_id`
4. Form CRUD/runtime fixes
   - Added missing imports/defaults
   - Defaulted tenant context and slug generation safely
   - Enabled partial update validation
5. Pagination serialization
   - Added `PaginatedResult.to_dict()`
6. Permission evaluation
   - Switched to `user.roles`
7. Event/task platform fixes
   - Added JSON-safe event serialization
   - Registered Celery form/AI tasks and default queue
   - Added Flask app context for Celery tasks
8. Response submission hardening
   - Removed invalid `project` assumption
   - Corrected form version lookup path
   - Avoided fragile `active_version` dereference patterns
9. Admin singleton settings stability
   - Made default settings creation/retrieval atomic and resilient

## Test Suite Issues Corrected
1. Refresh test used an access token against a refresh-only endpoint
2. Logout test over-specified cookie invalidation format
3. Response and flow tests used skeletal empty forms but asserted guaranteed submission success
4. Generated auth traffic reused shared rate-limit keys
5. Health test assumed a specific payload shape (`services` vs `dependencies`)
6. Invalid token test assumed `401` only; backend returns framework-standard `422` for malformed JWTs
7. RBAC test assumed regular users cannot create forms, which is not the current backend contract

## Infrastructure/Config Issues Encountered
- Shared Mongo requires auth, while local example config pointed to an unauthenticated URI
- Restart-driven test runs could race backend readiness without a health wait

## Recommended Fix Order
1. Environment/bootstrap blockers
2. Auth/runtime crashes
3. Async worker/task registration
4. Submission/versioning path
5. Admin/error-handling defects
6. Contract-test corrections
