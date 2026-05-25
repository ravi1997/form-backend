# Production Readiness Runbook

## Required Gates

- `make lint`
- `make test-cov`
- `make openapi`
- Playwright API smoke tests against staging.
- Restore drill from the latest backup into an isolated environment.
- Rollback drill for API, worker, and frontend images.

## Rollback

1. Stop rollout and disable release feature flags.
2. Roll back API, Celery worker, Celery beat, and event listener images as one
   release unit.
3. Keep database migrations forward-compatible; prefer forward-fix migrations
   unless a migration explicitly includes tested rollback metadata.
4. Verify `/form/health/`, `/form/api/v1/tasks/{id}`, auth login, project form
   list, and response submission.

## Operational Checks

- Mongo and Redis readiness healthy.
- Queue depth and task age below alert thresholds.
- Error rate below SLO threshold.
- Structured logs contain `request_id`.
- OpenAPI export matches deployed build.
