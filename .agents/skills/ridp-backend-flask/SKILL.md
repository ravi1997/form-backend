---
name: ridp-backend-flask
description: Use when changing RIDP Flask routes, schemas, services, models, authz, tenancy, Celery tasks, OpenAPI docs, integrations, or backend tests.
---

# RIDP Backend Flask

Build like a production backend maintainer: tenant-safe, contract-stable, observable, and testable.

## Prompt Discipline
- Keep prompts minimal: one bounded backend task, exact files/symbols, constraints, and expected output.
- Prefer graph-backed discovery and symbol reads before broad repository search.
- Split route, service, model, contract, and verification work when that keeps each prompt smaller.
- Return concise summaries: changed files, commands run, and residual risk.

## Execution Rules
- Tenant-owned models need `organization_id`, `is_deleted`, and tenant-aware queryset behavior.
- `get()`, `__raw__`, and aggregations must explicitly scope `organization_id` unless superadmin behavior is intentional.
- Soft delete with `is_deleted=True`; avoid hard delete except documented exceptions.
- Routes parse/authorize/validate/call/return; business logic belongs in services.
- Services receive plain values/Pydantic schemas and do not import Flask/request/JWT globals.
- All service input goes through Pydantic v2.
- New route responses use `success_response` / `error_response`.
- State changes require `audit_logger`; exceptions use `error_logger.error(..., exc_info=True)`.
- Long-running or external work uses Celery, returns `202` with `task_id`, and avoids threads.
- Route/schema changes update `@swag_from` and generated frontend client.

## Verification
Run targeted pytest first; broaden to `make lint`, `make test`, and contract generation when shared behavior or API surface changed. Do not pay for broad checks unless the change can actually affect them.
