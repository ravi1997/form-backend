# RIDP Backend Agent Context

Python/Flask backend for the RIDP Form Platform. Use this file as the repo-level operating index.

## Canonical Paths
- Docs: `/home/ravi/workspace/form-builder/docs`
- Backend: `/home/ravi/workspace/docker/apps/form-backend`
- Frontend: `/home/ravi/workspace/frontend`

## How to Work in This Repo
- Use codebase-memory MCP first for code discovery: `search_graph`, `trace_path`, `get_code_snippet`, `query_graph`, `get_architecture`.

## Do This First
- Read `CONTEXT.md` for the canonical rules if the task is architectural or contract-related.
- Inspect the relevant route, service, or model file before editing.
- Check whether the change affects tenancy, auth, async work, or generated client contracts.
- Prefer graph discovery before grep unless you are searching literals or config text.

## Common Failure Modes
- Missing org scoping on Mongo queries.
- Route logic creeping into services.
- Contract changes without OpenAPI and generated client updates.
- Returning the wrong status code for async work or validation failures.
- Skipping audit/error logging on state changes or failures.

## Skill Router
- `ridp-backend-flask`: routes, services, models, auth, tenancy, Celery, OpenAPI, backend tests.
- `ridp-api-contract-sync`: API compatibility, OpenAPI, generated Dart client, auth headers, envelopes.
- `ridp-senior-planner`: architecture, migrations, refactors, risk analysis.
- `ridp-code-review`: reviews, bugs, security, tenancy, auth audits.
- `ridp-testing-strategy`: tests, flakiness, coverage, verification strategy.
- `ridp-quality-gates`: final lint/test/security and handoff readiness.

## Repo Priorities
- Routes stay thin. Services own business logic. Engines own core algorithms.
- Pydantic owns request/response boundaries.
- Mongo queries must stay org-scoped unless the collection is explicitly exempted in `CONTEXT.md`.
- Async work uses Celery and should return `202` with a `task_id`.
- State changes need audit logging. Failures should be logged with stack context.

## Safety and Data Rules
- Never import Flask request/JWT globals into services.
- Never run tenant-owned queries without the required org filter.
- Never expose secrets or raw credentials to plugin subprocesses.
- Preserve route/schema contract changes with OpenAPI updates and generated client updates when applicable.

## Useful Commands
```bash
git status --short
make lint
make test
make openapi
make generate-dart-client
docker compose run --rm backend pytest tests/test_file.py -v
```

## Verification Gates
- Run `make lint` when routes, services, models, or shared utilities change.
- Run `make openapi` when route or schema contracts change.
- Run `make generate-dart-client` when API response or request shapes change.
- Run targeted `pytest` for the touched backend area before handoff.

## Pre-Handoff Checklist
- `git status --short`
- `make lint`
- `make openapi` if contracts changed
- `make generate-dart-client` if payloads changed
- Targeted `pytest` for the touched area

## Handoff Checklist
- Report what you checked.
- Report what you skipped.
- Call out residual risk explicitly.
