# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python/Flask backend for a multi-tenant form-building platform (RIDP). Stack: Flask 3.1, MongoDB (MongoEngine), Redis, Celery, Elasticsearch. All services run via Docker Compose.

## Commands

```bash
make up-dev        # Start with live reload (Flask dev server + bind-mount to /app)
make up            # Start in production mode (gunicorn)
make down          # Stop all services
make restart       # Restart backend + celery + celery-beat only (use after code changes in dev)
make build         # Rebuild Docker image (no cache)
make bootstrap     # Create MongoDB indexes (run once on new environment)

make test          # Run pytest inside container
make test-cov      # Run tests with coverage report
make lint          # flake8 + black (check) + mypy via separate linter image

make shell         # bash in backend container
make shell-worker  # bash in celery worker container
make logs          # Follow backend logs
make logs-worker   # Follow celery worker logs
```

**Run a single test file or test:**
```bash
docker compose run --rm backend pytest tests/test_auth_service.py -v
docker compose run --rm backend pytest tests/test_auth_service.py::TestClass::test_method -v
```

Note: Celery workers do not hot-reload. Run `make restart` after changing task code.

## Architecture

### Request Flow

```
HTTP Request
  → Flask middleware (request_id.py, tenant_db.py)
  → JWT auth (Flask-JWT-Extended)
  → Rate limiter (tenant-aware, Redis-backed)
  → Route handler (routes/v1/)
  → Service layer (services/)
  → MongoEngine models (models/)
  → Long-running ops → Celery task (.delay() / .apply_async())
```

### Multi-Tenancy

Every model has an `organization_id`. The custom `TenantIsolatedSoftDeleteQuerySet` (in `models/base.py`) automatically scopes all queries to the current tenant, set by `middleware/tenant_db.py` from the JWT claims. Superadmin role bypasses this.

Soft-delete is also enforced at the queryset level — deleted documents are excluded by default.

### Service Layer Pattern

All business logic lives in `services/`. `services/base.py` provides a `BaseService` with common paginated CRUD. Services take Pydantic schemas as input and return model instances or dicts. Services should not contain route-specific logic.

### Async Tasks (Celery)

Tasks live in `tasks/`. Multiple queues: `celery` (default), `sms`, `mail`, `ehospital`, `request`, `employee`. Task retry policy: max 3 retries, 300s backoff. Soft timeout: 300s, hard timeout: 3600s.

### Authentication

JWT access + refresh token pattern. Tokens are blocklisted in Redis on logout. OTPs are also stored in Redis. Bcrypt for password hashing.

### Logging

Five named loggers — use the right one for the context:

```python
from logger import get_logger, audit_logger, error_logger, performance_logger

logger = get_logger(__name__)     # General application operations
audit_logger.info(...)            # State changes, compliance events
error_logger.error(..., exc_info=True)  # Exceptions
performance_logger.info(...)      # Timing diagnostics
```

Log files rotate at 10MB (10 backups). PII and secrets are automatically masked by a filter in `config/logging.py`.

### Key Directories

| Path | Purpose |
|------|---------|
| `app.py` | Flask app factory |
| `extensions.py` | JWT, CORS, Limiter, Talisman, Swagger init |
| `config/` | Settings (Pydantic), Celery, logging, Redis, Sentry, tracing |
| `models/` | MongoEngine documents (PascalCase filenames) |
| `schemas/` | Pydantic v2 validation schemas |
| `routes/v1/` | Flask blueprints; registered in `routes/__init__.py` |
| `services/` | Business logic |
| `tasks/` | Celery async tasks |
| `middleware/` | `request_id.py`, `tenant_db.py` |
| `workers/` | `event_listener.py` — real-time event processor |
| `scripts/` | `bootstrap_resources.py` (indexes), `manage.py` (CLI), `schema_migrations/` |
| `tests/` | pytest unit tests; `conftest.py` uses testcontainers for real MongoDB + Redis |
| `tests-playwright/` | E2E tests (Node.js/Playwright) |

### Adding a New Feature

1. Model in `models/YourModel.py`
2. Pydantic schema in `schemas/your_schema.py`
3. Service in `services/your_service.py` (extend `BaseService`)
4. Blueprint in `routes/v1/your_route.py`
5. Register blueprint in `routes/__init__.py`
6. Tests in `tests/test_your_feature.py`

### Environment

Copy `.env.example` to `.env`. Key variables:

| Variable | Notes |
|----------|-------|
| `APP_ENV` | `development` / `testing` / `production` |
| `MONGODB_URI` | Full connection string |
| `REDIS_HOST` / `REDIS_PORT` | Cache, sessions, Celery broker |
| `JWT_SECRET_KEY` | Must be changed in production |
| `ELASTICSEARCH_URL` | For search and analytics |
| `AI_PROVIDER` | `local` / `ollama` / `openai` |
| `OLAP_ENGINE` | `duckdb` (default) or `clickhouse` |

### Testing Notes

- Tests use `testcontainers` to spin up real MongoDB and Redis (no mocks for these).
- `APP_ENV=testing` is set automatically via `pytest.ini`.
- Coverage is configured for `services/` and `routes/` modules.
