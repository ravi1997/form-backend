# Onboarding Reading Order

Recommended reading sequence for engineers, QA, frontend developers, and DevOps joining the project.

---

## For All Engineers (Start Here)

1. **`docs/backend/overview.md`** — System identity, architecture, technology stack, request flow, multi-tenancy model, service layer, Celery, logging. Read in full.

2. **`docs/backend/policies.md`** — API design rules, authentication policy, authorization policy, validation policy, security policy, contributor rules. Read in full.

3. **`docs/backend/appendices/glossary.md`** — Key terms. Skim to learn the vocabulary. Return here when you encounter unfamiliar terms.

---

## For Backend Engineers

4. **`docs/backend/appendices/auth-permission-matrix.md`** — Understand the full permission model before adding any route.

5. **`docs/backend/appendices/lifecycle-matrices.md`** — Understand state machines for forms, responses, tokens, users, jobs before touching any flow.

6. **`docs/backend/blueprints/auth.md`** — Read auth blueprint thoroughly (most other things depend on JWT understanding).

7. **`docs/backend/blueprints/user.md`** — User management.

8. **`docs/backend/blueprints/forms.md`** — Core form CRUD.

9. Browse remaining blueprint docs as you need them.

10. **`docs/backend/risks-and-gaps.md`** — Critical reading before any code changes. Know what is broken or risky.

---

## For Frontend / API Integration Engineers

4. **`docs/backend/integration-guide.md`** — Read in full. This is your primary reference.

5. **`docs/backend/appendices/auth-permission-matrix.md`** — Sections 5 (auth methods) and 6 (public endpoints).

6. **`docs/backend/appendices/route-inventory.md`** — Quick route lookup.

7. **`docs/backend/appendices/legacy-route-mapping.md`** — Important for knowing canonical vs alias URLs.

8. **`docs/backend/risks-and-gaps.md`** — Section 3 (Risk Register) for any risks affecting your integration.

---

## For QA / Automation Engineers

4. **`docs/backend/integration-guide.md`** — Full API reference with request/response shapes.

5. **`docs/backend/appendices/route-inventory.md`** — Complete route listing with auth requirements.

6. **`docs/backend/appendices/lifecycle-matrices.md`** — State machines for testing state transitions.

7. **`docs/backend/risks-and-gaps.md`** — Known gaps that need test coverage or manual testing.

8. **`docs/backend/appendices/auth-permission-matrix.md`** — Test authorization: verify each role cannot access routes above its level.

---

## For DevOps / Security Engineers

4. **`docs/backend/policies.md`** — Sections 7 (Security Policy) and 8 (Observability Policy).

5. **`docs/backend/risks-and-gaps.md`** — Full risk register. Section 4 (Security Summary) and Section 6 (Remediation Priority).

6. **`docs/backend/overview.md`** — Section 15 (Development & Operations) for make targets and environment variables.

---

## Key Files to Know in the Codebase

| Purpose | File |
|---------|------|
| App factory | `app.py` |
| Blueprint registration | `routes/__init__.py` |
| Multi-tenancy enforcement | `models/base.py`, `middleware/tenant_db.py` |
| JWT auth + cookie config | `app.py` (JWT config section), `extensions.py` |
| Role-based access control | `utils/security.py` |
| Fine-grained form permissions | `routes/v1/form/helper.py` |
| Global error handlers | `utils/error_handlers.py` |
| Response format helpers | `utils/response_helper.py` |
| WAF middleware | `middleware/security_waf.py` |
| Async tasks | `tasks/form_tasks.py` |
| Logging configuration | `config/logging.py`, `logger/unified_logger.py` |
| Settings / env vars | `config/settings.py` |
| Test configuration | `tests/conftest.py`, `pytest.ini` |

---

## Common First Tasks and Where to Look

| Task | Start here |
|------|-----------|
| Add a new API endpoint | `routes/v1/your_route.py` → register in `routes/__init__.py` |
| Add business logic | `services/your_service.py` → extend `BaseService` |
| Add a new model | `models/YourModel.py` → use `TenantIsolatedSoftDeleteQuerySet` |
| Debug an auth issue | Check `utils/jwt_handlers.py`, `extensions.py`, `utils/security.py` |
| Debug a tenant isolation issue | Check `middleware/tenant_db.py`, `models/base.py` |
| Add a Celery task | `tasks/` → follow existing task pattern with retry policy |
| Run a specific test | `docker compose run --rm backend pytest tests/test_your.py -v` |
| Inspect registered routes | `flask routes` inside the container, or check Swagger at `/form/docs` |
