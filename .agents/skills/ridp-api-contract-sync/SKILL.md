---
name: ridp-api-contract-sync
description: Use when RIDP backend routes/schemas/OpenAPI, generated Dart API clients, API compatibility, auth headers, response envelopes, or cross-repo frontend/backend behavior are involved.
---

# RIDP API Contract Sync

Backend owns the contract; frontend consumes it. Never hand-edit generated Dart API code.

## Contract Invariants
- API prefix: `/form/api/v1/`.
- Response envelope changes require explicit frontend/test updates.
- Bearer auth uses `Authorization: Bearer <token>`.
- Cookie auth requires `X-CSRF-TOKEN-ACCESS` on POST/PUT/PATCH/DELETE.
- Async operations return `202` with `{ "task_id": "..." }`.
- Public submit is unauthenticated but validates public, published, and not expired/scheduled.
- Clear-all responses requires `{ "confirm": "DELETE_ALL" }`.
- Role order and ACL action names must match both repos.

## Change Protocol
1. Change backend route/schema/service behavior.
2. Update Swagger/OpenAPI annotations.
3. Run `make openapi && make generate-dart-client` from backend.
4. Inspect generated client diff for intended churn only.
5. Update frontend wrappers/state/UI tests.
6. Verify backend tests plus frontend analyze/contract tests.
