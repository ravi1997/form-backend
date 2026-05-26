---
name: ridp-code-review
description: Use for RIDP code reviews, diff audits, PR checks, security-sensitive changes, auth/tenancy changes, generated-client changes, or bug-finding requests.
---

# RIDP Code Review

Review as a production maintainer. Findings first, severity ordered, with file/line references.

## Hunt Order
1. Tenant/data leaks: missing `organization_id`, raw query/aggregation gaps, wrong superadmin scope.
2. Auth/authz: role hierarchy, form ACL actions, route guards, CSRF for cookie mode, public endpoint boundaries.
3. Contract drift: OpenAPI mismatch, response envelope changes, generated Dart client assumptions.
4. Data loss: hard deletes, unsafe bulk actions, migrations without rollback/containment.
5. Async/idempotency: Celery dispatch, retries, duplicate side effects, missing `202 task_id`.
6. Frontend breakage: Smart Grid/layout coupling, null-safety holes, accessibility regressions, stale DTO mapping.
7. Test weakness: missing regression coverage for the actual failure mode.

## Review Discipline
- Verify with code, tests, or targeted search; do not speculate as a finding.
- Ignore style preferences unless they create correctness, maintainability, or user-impact risk.
- If no issues are found, say so and name the remaining test/coverage risk.
