# RIDP Backend Agent Context

Python/Flask backend for the RIDP Form Platform. Keep this file as the durable index; load task detail from `.agents/skills/<name>/SKILL.md` only when relevant.

## Durable Subagent Orchestration
All major coding, planning, reviews, and test runs are delegated to specialized, narrow-context subagents to keep parent model token usage extremely low and optimize context cost. For architecture and operations, see [.agents/skills/ORCHESTRATOR.md](file:///home/ravi/workspace/docker/apps/form-backend/.agents/skills/ORCHESTRATOR.md).

## Skill Router
- `ridp-backend-flask`: routes, schemas, services, models, authz, tenancy, Celery, OpenAPI, backend tests.
- `ridp-api-contract-sync`: backend/frontend API compatibility, OpenAPI, generated Dart client, auth headers, response envelopes.
- `ridp-senior-planner`: architecture, multi-step plans, migrations, refactors, risk analysis.
- `ridp-code-review`: reviews, bug hunts, security/tenancy/auth audits.
- `ridp-testing-strategy`: new/failing/flaky tests and coverage strategy.
- `ridp-quality-gates`: final verification, lint/test/security/tooling readiness.

Project MCP defaults are in `.mcp.json`. Use the smallest relevant tool set. Validate agent tooling with `.agents/check-agent-tools.sh`.

## Hard Invariants
- API prefix: `/mahasangraha/api/v1/`; Swagger UI: `/mahasangraha/docs`; frontend source: `/home/ravi/workspace/frontend`.
- Tenant-owned queries must include `organization_id`; `superadmin` is the only cross-org exception.
- `get()`, `__raw__`, and aggregations bypass automatic tenant filtering; scope them explicitly.
- Soft delete with `is_deleted=True`; hard delete only for documented exceptions.
- Services do not import Flask/request/JWT globals; routes stay thin.
- All service input goes through Pydantic v2; new responses use `success_response` / `error_response`.
- State changes need `audit_logger`; exceptions need `error_logger.error(..., exc_info=True)`.
- Route/schema changes need `@swag_from`, OpenAPI regeneration, and generated frontend client update.
- Async work uses Celery and returns `202` with `{ "task_id": "..." }`; do not use threads.
- Auth supports Bearer and HttpOnly cookie modes; cookie writes require `X-CSRF-TOKEN-ACCESS`.

## Commands
```bash
make up-dev
make restart
make lint
make test
make openapi
make generate-dart-client
docker compose run --rm backend pytest tests/test_file.py -v
```

Before handoff, report checks run, skipped checks, and residual risk.
