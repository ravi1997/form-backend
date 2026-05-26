---
name: ridp-testing-strategy
description: Use when adding/fixing RIDP tests, debugging flaky tests, validating API compatibility, or improving coverage for auth, tenancy, UI, accessibility, async, or contracts.
---

# RIDP Testing Strategy

Test production promises, not implementation trivia. Start narrow, then broaden only when shared contracts changed.

## Backend Coverage Priorities
- Tenant isolation across normal queries, `get()`, raw queries, and aggregations.
- Auth modes, roles, form ACLs, CSRF, and public-submit boundaries.
- Soft delete and confirmation-gated destructive operations.
- Response envelopes, status codes, OpenAPI schemas, and generated-client compatibility.
- Celery dispatch, task ids, retries/idempotency, and no thread-based async regressions.

## Frontend Coverage Priorities
- Generated DTO mapping and domain wrapper behavior.
- Route guards and role/ACL-driven UI capabilities.
- Form rendering: `uiType`, `section.layout`, Smart Grid spans, responsive constraints.
- Accessibility semantics, keyboard/focus behavior, validation/error states.
- Async UX for `202 task_id`, stubs, loading, retry, and failure states.

## Execution Standard
Reproduce first when fixing. Add a regression test near the behavior. Run targeted tests during iteration and full quality gates when auth, contracts, layout engine, generated clients, or shared services changed.
