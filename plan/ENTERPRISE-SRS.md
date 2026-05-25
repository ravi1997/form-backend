# RIDP Form Platform: Enterprise SRS and Production Execution Specification

Document version: 3.0  
Generated: 2026-05-25  
Source documents:
- Frontend: `plan/PRODUCTION-PLAN.md`
- Backend: `/home/ravi/workspace/docker/apps/form-backend/plan/PRODUCTION-PLAN.md`

## 1. Executive Summary

The RIDP Form Platform is a multi-tenant form-building, publishing, response-collection, analytics, workflow, and administration platform with a Flutter frontend and Flask/MongoDB backend. The current planning documents describe broad enterprise goals, but they are not implementation-ready: they lack canonical API contracts, shared schema ownership, rollout gates, failure behavior, queue semantics, tenant invariants, and operational acceptance criteria.

The system purpose is to let authenticated tenant users create projects and forms, configure schema-driven fields and logic, publish versions, collect responses, manage users and permissions, run analytics, execute workflows, export/import data, and administer platform configuration safely across tenants.

Existing architecture assumptions:
- Frontend: Flutter, Riverpod, Dio, generated DTOs, feature-folder structure, offline/sync primitives present but not fully specified.
- Backend: Flask blueprints under `/form/api/v1`, MongoEngine models, Pydantic schemas, Redis, Celery, JWT auth, Talisman, rate limiting, request IDs, WAF middleware, OpenTelemetry hooks.
- Tenancy: users carry `organization_id`; frontend sends `X-Organization-ID`; backend should enforce tenant scope server-side on every resource access.
- Forms: project-scoped form routes are canonical, but frontend still contains global `/forms/...` assumptions.

Main technical goals:
- Establish one canonical API/schema contract and generate clients from it.
- Make project-scoped tenancy, RBAC, audit logging, and validation non-bypassable.
- Define async task, file upload, response export/import, and publishing semantics.
- Add production observability, CI gates, contract testing, security controls, and rollback playbooks.
- Convert roadmap items into phase-gated implementation work with acceptance tests.

High-risk areas:
- Critical API route mismatch between frontend and backend form contracts.
- Response envelope ambiguity (`{success,data,message}` vs raw DTO handling).
- Auth/session behavior is inconsistent across bearer tokens and HttpOnly cookies.
- Async task polling is referenced but not fully specified.
- RBAC and tenant isolation are under-specified for project/form/response/admin surfaces.
- File upload, import/export, and public submission flows lack complete threat models.

Overall assessment score: 58/100. The codebase has many useful production primitives, but the plans are not production-ready execution specs until the blocking contract, security, and reliability gaps are resolved.

## 2. Frontend vs Backend Alignment Audit

| Area | Frontend Expectation | Backend Implementation | Status | Problem | Required Fix |
|---|---|---|---|---|---|
| Base URL | `API_BASE_URL` + relative endpoints | Blueprints under `/form/api/v1` plus health under `/form/health` | High | Plan does not define whether frontend base includes `/form/api/v1`; endpoint constants assume it does. | Define `API_BASE_URL=https://host/form/api/v1`; define separate `HEALTH_BASE_URL` or health endpoint `/system/health`. |
| Form list/create/get/update/delete | Global `/forms/`, `/forms/{id}` | Core CRUD registered at `/projects/{project_id}/forms` | Critical | Frontend cannot reliably list/create forms without project context. | Replace global CRUD calls with project-scoped endpoints; keep global aliases only if backend intentionally supports them and documents semantics. |
| Project forms | `/projects/{projectId}/forms` | Canonical backend route exists | Compatible | This should be the primary contract. | Make project context mandatory in frontend routers/controllers. |
| Builder metadata | `/forms/builder-metadata` | Registered under `/form/api/v1/forms/builder-metadata` via separate blueprint and project route also has `builder-metadata` | Medium | Duplicate route ownership creates drift risk. | Single owner: `GET /forms/builder-metadata`, versioned schema, cached with ETag. |
| OTP request | `/auth/otp/request` | `/auth/request-otp` | Critical | Login via OTP fails unless an undocumented alias exists. | Standardize to `/auth/otp/request` or update frontend to `/auth/request-otp`; deprecate alias with tests. |
| OTP verify | `/auth/otp/verify` | Login accepts `mobile` + `otp` at `/auth/login` | Critical | Frontend calls route not shown in backend. | Add `/auth/otp/verify` wrapper or change frontend to call `/auth/login`. |
| Register response | Expects tokens + user per comments | Backend returns only `{user}` in response envelope | High | New user registration cannot auto-login as documented. | Choose one behavior: either registration returns tokens or frontend routes to login; update OpenAPI and tests. |
| Refresh request | Sends refresh token as Bearer header | Backend uses `@jwt_required(refresh=True)` likely header/cookie | Medium | Comments say body; implementation uses header. | Canonicalize: `POST /auth/refresh` with refresh bearer token or secure cookie; never both ambiguously. |
| Response envelope | Some services cast direct `response.data` to DTO/map; some comments expect raw | Backend wraps success as `{success,message,data}` | Critical | DTO parsing breaks unless interceptor unwraps consistently. | Define client interceptor envelope policy; all typed services receive `data`; contract tests must verify. |
| Pagination | `page`, `page_size`; frontend reads `items` | Backend returns paginated `data` with `items` | Medium | Metadata fields are not specified. | Canonical pagination: `{items,page,page_size,total,total_pages,has_next,has_prev}`. |
| Error handling | Dio exceptions, app exceptions, navigation on 401 | Backend returns `{success:false,error,details?}` | Medium | No canonical `code`, `request_id`, field errors, retryability. | Define error envelope with `code`, `message`, `details`, `field_errors`, `request_id`, `retry_after`. |
| Auth storage | Frontend stores bearer tokens | Backend also sets HttpOnly cookies | High | Dual token channels create CSRF/session ambiguity. | For Flutter web/mobile use bearer tokens only or cookie-only for web; document CSRF behavior per platform. |
| CORS | Cross-origin frontend | Backend `supports_credentials=False`, allows auth headers | Medium | Cookie auth cannot work cross-origin; bearer can. | If bearer-only, do not set cookies for API clients; if cookie auth, set credentials and CSRF headers. |
| Tenant header | Sends `X-Organization-ID` from token service | Backend derives org from user and middleware route context | High | Header can be spoofed if trusted. | Treat header as selection hint only; authorize against token claims/server-side membership. |
| RBAC | Permission UI planned | Backend has `require_permission` and access control service | High | Plan lacks permission matrix by route/action. | Create route-level permission matrix and automated tests for every protected endpoint. |
| Form status enum | `draft/published/archived` | Same literals in schema | Compatible | Needs generated enum to avoid drift. | Generate Dart enum from OpenAPI. |
| UI type enum | Frontend dynamic strings | Backend literal set includes `flex`, `grid-cols-2`, etc. | Medium | Builder may emit unsupported values. | Frontend must consume `builder-metadata` enum and validate before save. |
| Access policy naming | Frontend `accessPolicy` | Backend schema `access_policy` | High | DTO currently maps only camelCase, causing missed data. | Support `@JsonKey(name:'access_policy')`; contract test. |
| Dates | Frontend parses ISO | Backend emits `datetime.isoformat()` | Medium | Timezone can be omitted if naive datetimes exist. | Require UTC RFC3339 with `Z`; reject naive datetimes. |
| Publish/clone | Frontend expects async `{task_id}` | Backend async Celery tasks referenced | High | Task status semantics and 202 envelope not specified. | Return `202` with `{task_id,status_url}`; define task states and polling backoff. |
| File upload | Frontend has `/forms/upload`, `/forms/signatures` | Backend files routes are project/form-scoped modules | High | Endpoint ownership and multipart contract are unclear. | Canonicalize file upload under `/projects/{project_id}/forms/{form_id}/files`; include metadata DTO. |
| Realtime/events | Plans mention real-time analytics and streams | Backend has stream/event services but no frontend contract | High | UI may assume realtime where backend provides polling. | Define SSE/WebSocket/polling per feature; version event payloads. |
| Cache assumptions | Frontend plans Riverpod caching/TTL | Backend analytics cache exists | Medium | No cache invalidation contract. | Define cache keys, ETags, invalidation events, stale TTLs. |
| Feature flags | Plans require flags | No canonical flag API in frontend endpoints | Medium | Rollout cannot be controlled safely. | Add `/system/feature-flags` read endpoint and server-side enforcement for gated behavior. |

## 3. Missing Features Discovery

| Feature | Why Needed | Risk If Missing | Suggested Architecture | Priority |
|---|---|---|---|---|
| Canonical OpenAPI contract | Autonomous agents and teams need one source of truth. | Client/server drift causes production outages. | Generate OpenAPI from Flask/Pydantic; validate in CI; generate Dart DTO/client. | Critical |
| Contract tests | Protects frontend/backend compatibility. | Silent route/schema breaks. | Schemathesis/Dredd plus Flutter DTO fixture tests. | Critical |
| Idempotency keys | Required for retries on create/publish/export/upload. | Duplicate forms, responses, exports, payments-like side effects. | `Idempotency-Key` table/collection scoped by tenant/user/route/body hash. | Critical |
| Route permission matrix | Required for RBAC completeness. | Privilege escalation and inconsistent UI guards. | Machine-readable `permissions.yaml` generating backend decorators and frontend guards. | Critical |
| Audit log viewer | Enterprises need activity history. | Security investigations impossible. | Append-only `AuditLog` with admin UI filters and export. | High |
| Draft autosave contract | Builder workflows need resilience. | Lost work and conflicting saves. | Debounced `PUT /draft` with ETag/revision and conflict response. | High |
| Concurrent editing control | Multiple editors will collide. | Last-write-wins data loss. | Optimistic concurrency via `version/revision`, lock hints, presence events later. | High |
| Notification center | Users need task/workflow/export status. | Async tasks feel broken. | Notifications table + WebSocket/SSE/poll fallback. | High |
| Full text search/filtering | Forms/responses/admin lists need scale. | Slow list scans and poor UX. | Mongo indexes + search service; normalized query params. | High |
| Export/import validation | Enterprise data operations need safe portability. | Corrupt imports and CSV injection. | Async import jobs, dry-run validation, schema versioning, CSV escaping. | High |
| API versioning policy | Prevents breaking deployed clients. | Mobile/web clients break on deploy. | `/api/v1`, deprecation headers, compatibility tests. | High |
| Health/readiness/liveness | Required for orchestration. | Bad pods receive traffic. | `/health/live`, `/health/ready`, dependency checks. | High |
| Structured logging | Required for production support. | Incident triage slow. | JSON logs with request_id, tenant_id, user_id hash, route, latency. | High |
| Distributed tracing | Required for async and multi-service debugging. | Latency root causes invisible. | OpenTelemetry spans across Flask, Celery, Redis, Mongo. | High |
| Backup/restore drills | Multi-tenant data must be recoverable. | Data loss becomes existential. | PITR backups, restore test environment, quarterly drills. | Critical |
| Rate limit strategy | Protects auth, public forms, exports. | DDoS and credential stuffing. | Per-IP, per-user, per-tenant quotas with `Retry-After`. | Critical |
| File malware scanning | Uploads are dangerous. | Malware, stored XSS, data exfiltration. | Quarantine bucket, MIME sniffing, AV scan, signed download URLs. | Critical |
| Webhook delivery system | Integrations need reliability. | Lost external events. | Outbox, retries, DLQ, signatures, replay UI. | High |
| Accessibility test pipeline | WCAG cannot be manual-only. | Regressions and legal risk. | Flutter semantics tests, axe web tests, keyboard E2E. | High |
| Performance budgets | Prevents bundle/API regression. | Slow app at scale. | CI budget checks, p95 dashboards, load tests. | Medium |
| Localization governance | Multi-language requires workflow. | Partial translations and RTL breakage. | ICU messages, translation coverage CI, RTL visual tests. | Medium |
| Admin impersonation with audit | Support teams need controlled troubleshooting. | Unsafe credential sharing. | Time-bound impersonation, explicit consent/approval, audit trail. | Medium |
| Secrets management | Production secrets cannot live in env files. | Secret leaks. | Vault/cloud secret manager, rotation playbook, scan gates. | Critical |
| Migration strategy | Schema changes need repeatability. | Broken deployments and partial data changes. | Versioned migrations, dry-run, rollback notes. | Critical |
| Preview deployments | Faster frontend/backend validation. | Late integration failures. | Per-PR environment with seeded tenant data. | Medium |

## 4. Architecture Review

Current issues:
- The documents conflate product roadmap, remediation tasks, and implementation requirements. They do not define ownership boundaries between frontend API clients, backend route contracts, domain services, tasks, and infrastructure.
- Backend route modularity exists, but route prefixes are inconsistent with frontend endpoint constants. Project-scoped form ownership is the most important domain boundary and must be enforced everywhere.
- Response envelope and error envelope are not treated as first-class contracts.
- Async workflows are named but not specified: no task lifecycle, cancellation, retry, DLQ, result retention, progress payload, or frontend polling behavior.
- RBAC exists as scattered decorators/services rather than a contract that can generate UI guards and backend enforcement tests.
- Multi-tenancy relies on convention; every query must include tenant predicates and every route must have tenant isolation tests.

Future risks:
- Adding enterprise features before contract stabilization will multiply incompatible endpoints.
- Form schemas will drift between Pydantic/MongoEngine/Dart unless generated.
- Analytics/export/import workloads will compete with request traffic without queue isolation.
- Public forms and file uploads are likely abuse vectors without quotas and scanning.

Recommended architecture improvements:
- Adopt modular monolith boundaries: Auth, Identity, Tenant/Project, Form Builder, Responses, Workflow, Analytics, Files, Admin, Integrations.
- Keep Flask monolith initially, but enforce service-layer boundaries and publish internal events through an outbox.
- Add OpenAPI-first or schema-generated workflow. Backend owns schemas; frontend consumes generated DTOs and writes mappers only for UI state.
- Use optimistic concurrency for form drafts and response edits.
- Use Redis/Celery queues separated by workload class: `critical`, `default`, `exports`, `ai`, `webhooks`.
- Add durable outbox for audit/webhook/notification events before considering microservices.

Refactoring recommendations:
- Replace global form endpoints in frontend with project-scoped repository methods.
- Introduce `ApiEnvelope<T>` and `ApiError` models in Flutter.
- Generate Dart models for Form, Section, Question, Response, User, Project, Task, FileAsset, AuditEvent.
- Move frontend route guards to a central permission service backed by server-returned capabilities.
- Add backend decorators that require tenant, permission, and idempotency for mutation routes.

## 5. Data Contract & Schema Validation

Canonical shared schema requirements:
- All API responses use `ApiEnvelope<T>`: `{success:boolean,message:string,data?:T,error?:ApiError,request_id:string}`.
- Paginated lists use `Page<T>`: `{items:T[],page:int,page_size:int,total:int,total_pages:int,has_next:boolean,has_prev:boolean}`.
- Errors use stable codes: `AUTH_INVALID_CREDENTIALS`, `AUTH_EXPIRED`, `VALIDATION_FAILED`, `TENANT_FORBIDDEN`, `RESOURCE_NOT_FOUND`, `CONFLICT`, `RATE_LIMITED`, `TASK_FAILED`.
- Dates use UTC RFC3339 strings with timezone. Backend must serialize aware datetimes only.
- IDs are strings. UUID validation applies to project/form/response/task IDs.
- Field naming is snake_case over the wire. Frontend may expose camelCase internally through generated mappings.
- Nullable fields must be explicitly nullable in OpenAPI; omitted and `null` must have defined behavior.
- Decimal/precision fields, if introduced, must be strings or integer minor units, never binary floats.

Canonical API examples:
- `POST /auth/login` body: `{identifier:string,password:string}` or `{mobile:string,otp:string}`. Response data: `{access_token,refresh_token,expires_in,user}`.
- `POST /auth/refresh` requires refresh bearer token or cookie, not request body. Response data: `{access_token,refresh_token,expires_in}` if rotation is enabled.
- `GET /projects/{project_id}/forms?page=1&page_size=50&status=draft&search=q`.
- `PUT /projects/{project_id}/forms/{form_id}/draft` requires `If-Match` or body `revision`. Conflict returns `409 CONFLICT` with latest revision metadata.
- `POST /projects/{project_id}/forms/{form_id}/publish` returns `202` data `{task_id,status_url}`.
- `GET /tasks/{task_id}` returns `{id,type,status,progress,result,error,created_at,updated_at,expires_at}`.

OpenAPI/type generation workflow:
1. Backend Pydantic schemas are the source of truth.
2. CI exports `openapi.json` on every PR.
3. CI diffs OpenAPI and classifies breaking changes.
4. Dart models/client are generated from OpenAPI.
5. Frontend commits generated models only when API changes are approved.
6. Contract tests replay representative fixtures through generated models.

Recommended tools:
- Backend: Pydantic v2 schemas, Flasgger only as presentation if accurate, Schemathesis for API fuzzing.
- Frontend: OpenAPI Generator or `swagger_dart_code_generator`; keep Freezed for UI view models where needed.
- Shared validation: backend validates all writes; frontend mirrors constraints for UX but never becomes authority.

## 6. Security Review

| Vulnerability | Severity | Location | Exploit Scenario | Recommended Fix |
|---|---|---|---|---|
| Route/tenant mismatch | Critical | Frontend `/forms`, backend project routes | User accesses forms without project scope if alias added poorly. | Enforce project-scoped routes and tenant predicates on every query. |
| Spoofable tenant header | Critical | `X-Organization-ID` | Malicious client sends another tenant ID. | Derive allowed tenants from JWT/user record; header only selects among authorized tenants. |
| Dual token channels | High | Auth service/cookies/bearer | CSRF or stale-cookie confusion on web. | Choose bearer-only or cookie-only per client; document CSRF. |
| Missing idempotency | High | Create/publish/export/upload | Retry creates duplicate resources. | Require idempotency keys for unsafe retryable mutations. |
| Incomplete file upload controls | Critical | Upload/signature endpoints | Malware upload or stored XSS. | MIME sniffing, extension allowlist, AV scan, size quotas, signed URLs. |
| Weak error envelope | Medium | Global error handling | Leaks internals or hides field failures. | Stable errors, sanitized messages, request IDs. |
| RBAC drift | Critical | Decorators/UI guards | UI hides action but backend allows it. | Machine-readable permission matrix with backend tests. |
| Public form abuse | High | Public submit routes | Spam, quota exhaustion, data injection. | CAPTCHA/risk checks, per-form quotas, rate limits, validation. |
| Logging PII | High | Audit/app logs | Sensitive responses appear in logs. | Structured redaction policy and tests. |
| CSV injection | Medium | Exports | Spreadsheet formula execution. | Escape formula-leading cells and document export safety. |
| Missing secret rotation | High | DevOps | Leaked JWT/DB secret persists. | Secret manager, rotation runbooks, scan gates. |
| CORS ambiguity | Medium | Flask CORS | Overly broad origins in production. | Exact origin allowlist per environment. |

## 7. Reliability & Scalability Review

Bottlenecks:
- Mongo list/filter endpoints will degrade without compound indexes on `organization_id`, `project`, `status`, `is_deleted`, `created_at`.
- Response exports and AI jobs can starve normal request processing if they share queue resources.
- Large forms/responses can create high memory pressure if serialized whole for every request.
- Polling all async tasks aggressively can overload API without backoff.
- File uploads through app servers will limit horizontal scaling unless direct-to-object storage is used.

Scaling recommendations:
- Make app servers stateless; store sessions/token blocklist in Redis.
- Use object storage for files with pre-signed upload/download URLs.
- Add queue partitioning and autoscaling based on queue depth/age.
- Add response pagination, streaming exports, and async bulk jobs.
- Add per-tenant rate quotas and budget enforcement for AI/export/public submissions.
- Add read models/materialized analytics where dashboards exceed p95 targets.

Reliability improvements:
- Define timeouts for every external dependency.
- Add retry with exponential backoff only for idempotent operations.
- Add DLQ and replay UI for webhooks/tasks.
- Add circuit breakers around AI/SMS/webhook providers.
- Add backup/restore drills with measured RPO/RTO.

Disaster recovery requirements:
- RPO: <= 15 minutes for production data.
- RTO: <= 4 hours for core form submission and auth.
- Daily encrypted backups; weekly restore verification; quarterly full incident simulation.

## 8. Developer Experience Review

Required standards:
- One canonical contract repository artifact: `openapi.json` plus generated clients.
- `make dev`, `make test`, `make lint`, `make openapi`, `make migrate`, `make seed`.
- Pre-commit hooks for formatting, linting, secrets, generated-file drift.
- ADRs for auth mode, tenancy model, async jobs, file storage, schema generation.
- Seed data for local tenant/project/forms/responses.
- Preview environment per PR with frontend and backend wired together.

Testing and mocking:
- Frontend should mock at repository boundary for component tests and use generated API fixtures for contract tests.
- Backend should use testcontainers or isolated Mongo/Redis databases for integration tests.
- E2E tests should use stable seeded tenants and assert RBAC/tenant isolation.

## 9. Testing Strategy

Frontend:
- Unit tests: Dart logic, mappers, validators, permission service. Target 85% on core/domain.
- Component tests: form builder widgets, response list/detail, admin controls, error/loading states.
- E2E tests: login, project/form CRUD, draft autosave, publish polling, public submission, export, RBAC denial.
- Accessibility: Flutter semantics tests, keyboard traversal tests, axe/Lighthouse for web build.
- Visual regression: golden tests for builder, dashboard, admin panels, mobile/tablet/desktop.
- Contract tests: generated DTO fixture decode/encode for every backend schema.

Backend:
- Unit tests: services, validators, permission decisions, serializers.
- Integration tests: routes with Mongo/Redis, tenant isolation, auth, file metadata, tasks.
- API tests: OpenAPI validation, status codes, response envelopes, pagination.
- Load tests: auth, form list, response submission, export queue, public submission.
- Security tests: RBAC matrix, rate limits, injection, upload validation, CORS, headers.
- Queue tests: task lifecycle, retries, cancellation, DLQ, idempotency.

CI gates:
- Backend coverage >= 85% for services/routes touched.
- Frontend coverage >= 80% for changed feature modules.
- OpenAPI diff must be reviewed for breaking changes.
- Contract test suite must pass before merge.
- Security scans: Bandit/Safety/pip-audit, dependency audit, secret scan.
- Performance smoke: p95 API latency and Flutter bundle budget checks.

## 10. Enterprise SRS

### System Overview
RIDP shall provide a tenant-isolated form platform for project-based form creation, publishing, response collection, analytics, workflow automation, import/export, user administration, themes, and system configuration.

### Functional Requirements
- Users can authenticate by password and optionally OTP.
- Admins can manage users, roles, departments, lock status, sessions, system settings, themes, and audit history.
- Users with project permissions can create, edit, autosave, publish, archive, restore, clone, import, and export forms.
- Forms support sections, nested sections, questions, validation, conditional logic, triggers, translations, themes, access policies, and version history.
- Respondents can submit public or authenticated responses subject to form status, expiry, permissions, quotas, and validation.
- Users can view, filter, search, export, and audit responses subject to permission.
- Async jobs expose task status and notifications.
- Analytics dashboards provide cached and fresh metrics with explicit freshness timestamps.
- Integrations include webhooks, SMS/OTP, AI generation/summarization/search, each behind feature flags and quotas.

### Non-Functional Requirements
- Availability: 99.9% monthly for core auth/form/response APIs.
- API p95 latency: <= 300 ms for common reads excluding async jobs.
- Public response submission p95: <= 500 ms excluding file upload.
- Accessibility: WCAG 2.1 AA for supported web surfaces.
- Security: OWASP ASVS-aligned controls for auth, tenancy, input validation, logging, upload, and secrets.
- Data durability: RPO <= 15 min, RTO <= 4 hr.

### Architecture
- Modular Flask backend with service-layer business logic, MongoDB persistence, Redis cache/session/task broker, Celery workers, OpenTelemetry, structured logging.
- Flutter frontend with Riverpod state, generated API client/DTOs, feature modules, centralized auth/session/permission/error handling.
- Object storage for uploads; CDN/signed URLs for downloads.
- Queue workloads separated by function and priority.

### Domain Models
Core models: Tenant/Organization, User, Role, Permission, Project, Form, FormVersion, Section, Question, Option, Response, FileAsset, Workflow, WorkflowInstance, Task, Notification, AuditLog, Theme, SystemSettings, WebhookEndpoint, WebhookDelivery.

### API Contracts
- All APIs are under `/form/api/v1` except health endpoints.
- Project-scoped forms are canonical: `/projects/{project_id}/forms`.
- All mutation requests validate idempotency where retryable.
- All responses use canonical envelope and errors.
- OpenAPI is mandatory and generated in CI.

### State Management
- Frontend repositories own server state access.
- Riverpod providers expose normalized view state with loading/error/empty/stale states.
- Form builder state maintains local draft, server revision, dirty fields, validation errors, and conflict status.

### Security Requirements
- Bearer token mode for API clients unless cookie mode is explicitly enabled for web.
- Refresh token rotation and token blocklist.
- RBAC enforced server-side and mirrored client-side.
- Tenant isolation enforced by server-side membership and query predicates.
- Upload scanning, rate limits, secure headers, CSP, redacted logs, audit logs.

### Scalability Requirements
- Horizontal stateless API scaling.
- Mongo indexes and pagination for all collection reads.
- Async exports/imports/AI/webhooks.
- Redis cache with explicit invalidation rules.
- Direct-to-object-storage upload for large files.

### Reliability Requirements
- Dependency timeouts, retries, circuit breakers, DLQs.
- Task status and notifications.
- Backup/restore playbooks and drills.
- Graceful degradation for AI/SMS/webhook provider outages.

### Deployment Architecture
- Environments: local, CI, preview, staging, production.
- Containers for frontend web, backend API, workers, scheduler.
- Managed Mongo/Redis/object storage in production.
- Blue/green or rolling deployments with migrations gated before traffic.

### Monitoring & Observability
- Metrics: request rate/error/latency, queue depth/age, DB latency, cache hit rate, upload failures, auth failures, tenant quota use.
- Logs: JSON structured with request_id/correlation_id.
- Traces: API to DB/Redis/Celery/provider spans.
- Alerts: p95 latency, error rate, auth failure spike, queue age, DLQ growth, backup failure.

### Testing Strategy
Use the testing strategy in section 9 as a release gate. No production rollout without green unit, integration, contract, security, E2E smoke, and migration tests.

### Migration Plan
- Freeze existing public contracts.
- Export current OpenAPI and route inventory.
- Normalize endpoints and add compatibility aliases only with deprecation dates.
- Add data migrations for schema fields and indexes.
- Run dual-read or dual-write only where necessary; remove compatibility after telemetry confirms no use.

### Rollout Strategy
- Phase flags for new auth/session, form route normalization, task polling, file upload, and admin control panel.
- Staging soak with synthetic tenant load.
- Canary production tenant rollout.
- Monitor dashboards for 24-72 hours before broad enablement.

### Risk Register
Top risks: contract drift, tenant leakage, auth ambiguity, upload abuse, export/AI queue starvation, missing backup restore, RBAC gaps, schema migration failure, accessibility regression, insufficient observability.

### Acceptance Criteria
- Frontend and backend pass compatibility matrix with no Critical/High open issues.
- OpenAPI generation and client generation are automated.
- Project-scoped form workflows pass E2E.
- RBAC/tenant isolation tests cover every protected endpoint.
- Async job and file upload flows pass failure-path tests.
- Production readiness checklist is fully green.

### Milestones
1. Contract freeze and OpenAPI generation.
2. Route/auth/envelope alignment.
3. Tenant/RBAC hardening.
4. Async task/file/import/export hardening.
5. Frontend UX/accessibility/state completion.
6. Observability/CI/CD/DR completion.
7. Staging load/security certification.
8. Canary rollout.

### Dependencies
MongoDB, Redis, Celery broker/result backend, object storage, SMS provider, AI provider, Sentry/OTel backend, CI runner, secrets manager.

### Open Questions
- Will web clients use bearer tokens or secure cookies as the primary auth mode?
- Should global `/forms` endpoints be removed or retained as read-only tenant-wide endpoints?
- What are enterprise tenant quotas for forms, responses, files, exports, AI, and SMS?
- Which compliance regimes are contractual: GDPR, HIPAA, SOC 2, ISO 27001?
- What is the source of truth for roles and departments?
- What file types and maximum upload sizes are allowed per tenant tier?

### Technical Debt
- Duplicate/ambiguous route prefixes.
- Manual DTO mapping instead of generated contracts.
- Response envelope assumptions hidden in interceptors/services.
- Incomplete async task semantics.
- Incomplete route permission inventory.
- Plans overstate readiness without executable acceptance criteria.

### Future Enhancements
Real-time collaborative editing, offline-first sync, advanced template marketplace, AI-assisted form generation, multi-cloud deployment, GraphQL read API, advanced data warehouse exports.

## 11. Final Implementation Roadmap

| Phase | Goal | Deliverables | Dependencies | Risks | Migrations | Testing | Rollback | Acceptance Criteria |
|---|---|---|---|---|---|---|---|---|
| 0 | Contract baseline | Route inventory, OpenAPI export, compatibility test harness | Current backend/frontend | Hidden clients depend on old routes | None | Contract smoke | Keep old routes | All current routes documented |
| 1 | API alignment | Project-scoped frontend repositories, envelope/error models, OTP route fix | Phase 0 | Breaking frontend flows | Optional route aliases | E2E auth/form CRUD | Feature flag old client | No Critical matrix issues |
| 2 | Tenant/RBAC hardening | Permission matrix, tenant query tests, audit events | Phase 1 | False denies | Indexes on tenant fields | Security/RBAC suite | Revert decorators by flag | Every protected route tested |
| 3 | Async/task foundation | Task schema, polling/backoff, queue partitioning, DLQ | Phase 1 | Queue misconfig | Task result indexes | Queue integration/load | Disable async features | Publish/export jobs observable |
| 4 | Files/import/export | Object storage, upload scan, async import/export | Phase 3 | Data corruption | File metadata collection | Upload/security/export tests | Disable upload/import | Safe file and export flows |
| 5 | Frontend production UX | Error boundaries, skeletons, guards, autosave, accessibility | Phase 1-4 | UI regressions | None | Widget/E2E/a11y/visual | Feature flags | WCAG AA core flows |
| 6 | Observability/DevOps | CI/CD, dashboards, alerts, backups, runbooks | All prior | Alert noise | Backup config | Smoke/load/restore drill | Previous deployment | Staging production-like |
| 7 | Enterprise admin | Control panel, settings, themes, audit viewer | Phase 2/6 | Misconfig by admins | Settings schema | Admin E2E/RBAC | Disable settings writes | Admin features permissioned |
| 8 | Staging/canary | Launch readiness | Load/security certification, canary rollout | All prior | Final indexes | Full regression | Blue/green rollback | Production checklist green |

Critical path: OpenAPI/contract baseline -> route/auth/envelope alignment -> tenant/RBAC hardening -> async/file workflows -> observability/CI -> staging/canary.

Parallelizable workstreams:
- Frontend accessibility/design system can proceed after shared component contracts are stable.
- DevOps CI/observability can proceed alongside API alignment.
- Backend RBAC matrix and frontend permission guards can proceed once route inventory is complete.
- File upload architecture can proceed in parallel with import/export UI after metadata contract is defined.

Backend/frontend sequencing:
- Backend publishes OpenAPI and compatibility aliases first.
- Frontend migrates repositories to generated/project-scoped clients.
- Backend removes deprecated aliases only after telemetry and deprecation window.

Infrastructure sequencing:
- CI and secret scanning first.
- Redis/Mongo/object storage staging parity second.
- Observability dashboards before canary.
- Backup/restore validation before production write traffic.

## 12. Final Deliverables

| Deliverable | Required Artifact |
|---|---|
| Unified enterprise SRS | This document |
| Backend/frontend alignment matrix | Section 2 |
| Missing features report | Section 3 |
| Risk register | Sections 10 and 12 |
| API consistency report | Sections 2 and 5 |
| Security review | Section 6 |
| Scalability review | Section 7 |
| Testing strategy | Section 9 |
| Implementation roadmap | Section 11 |
| Open questions list | Section 10 |
| Technical debt register | Section 10 |
| Production readiness checklist | Below |

Production readiness checklist:
- [ ] No Critical/High compatibility gaps remain.
- [ ] OpenAPI export is accurate and generated in CI.
- [ ] Dart API client/DTO generation is automated.
- [ ] Auth mode is documented and tested.
- [ ] Tenant isolation tests cover every route.
- [ ] RBAC matrix covers every route/action.
- [ ] Async task contract is implemented and observable.
- [ ] File uploads use scanning and object storage.
- [ ] Rate limits protect auth/public/upload/export routes.
- [ ] Structured logs/traces/metrics are available in staging.
- [ ] Backups and restores have been tested.
- [ ] CI runs unit, integration, contract, security, E2E smoke tests.
- [ ] Accessibility tests pass for core flows.
- [ ] Rollback plan has been exercised in staging.

## Top 20 Critical Issues Blocking Production Readiness

1. Frontend global `/forms` contract conflicts with backend project-scoped form routes.
2. OTP routes are incompatible (`/auth/otp/request|verify` vs `/auth/request-otp` and `/auth/login`).
3. Response envelope handling is not a documented cross-platform contract.
4. Registration response expectations differ from backend behavior.
5. Auth channel ambiguity between bearer tokens and HttpOnly cookies.
6. Tenant selection header can become a bypass if trusted.
7. No machine-readable route permission matrix.
8. No generated OpenAPI-to-Dart type workflow.
9. No idempotency for retryable create/publish/export/upload operations.
10. Async task lifecycle and polling contract are incomplete.
11. File upload security architecture is incomplete.
12. Public form abuse controls are not specified.
13. Form draft conflict resolution is undefined.
14. Pagination metadata and filtering semantics are incomplete.
15. Error codes, field errors, request IDs, and retry semantics are incomplete.
16. Queue partitioning, DLQ, and replay behavior are not specified.
17. Backup/restore validation is not a release gate.
18. Observability requirements are not tied to acceptance tests.
19. CI/CD gates are described but not made mandatory with exact jobs.
20. Plans mark status as ready while core contracts remain unresolved.

## Most Likely Future Failure Points

- A frontend release calls unimplemented or differently scoped backend routes.
- A tenant isolation bug leaks forms/responses across organizations.
- Token refresh/session expiry behaves differently on web and mobile.
- Large exports or AI jobs saturate Celery workers and delay publish/webhook tasks.
- File upload abuse causes malware storage, high costs, or app memory pressure.
- Form autosave overwrites another editor's changes.
- OpenAPI docs drift from Flask implementation and generated clients become unreliable.
- Analytics dashboards become stale or slow without freshness and cache invalidation rules.
- Rollback fails because migrations lack reversible or forward-compatible design.
- Production incident triage is delayed because logs lack request_id, tenant context, or task correlation.
