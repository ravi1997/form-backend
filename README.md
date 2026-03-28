# Forms Backend

> High-performance, containerized backend for building, publishing, and analyzing forms and surveys. Built with Python 3.12, Flask 3.x, MongoDB, and Redis.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Flask 3.x](https://img.shields.io/badge/flask-3.x-orange.svg)](https://flask.palletsprojects.com/)

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Testing](#testing)
- [Deployment](#deployment)
- [Security](#security)
- [Monitoring & Observability](#monitoring--observability)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

---

## Overview

The Forms Backend is a production-ready REST API for the RIDP platform, providing:

- **Form Builder**: Create, edit, and version forms with conditional logic
- **Multi-tenant SaaS**: Organization-scoped resources with RBAC
- **Workflow Engine**: Multi-step approval workflows with state machines
- **AI/ML Integration**: Smart field inference and response analysis
- **Real-time Analytics**: Dashboarding, trending, and anomaly detection
- **Multi-channel Delivery**: SMS, email, and web form submissions

### Tech Stack

| Layer | Technology |
|-------|------------|
| Runtime | Python 3.12 |
| Framework | Flask 3.x, Flask-JWT-Extended |
| Database | MongoDB (with MongoEngine ORM) |
| Cache/Queue | Redis |
| Background Jobs | Celery with Redis broker |
| Observability | OpenTelemetry, Sentry, Structured Logging |
| Containerization | Docker, Docker Compose |

---

## Key Features

### Core Functionality

- **Dynamic Forms**: Schema-driven form builder with MongoDB-backed JSON schemas
- **Conditional Logic**: Show/hide fields, pages, and questions based on responses
- **Multi-language**: Built-in translation support with translation keys
- **Permissions**: Granular RBAC with user groups and resource access control
- **Versioning**: Full audit trail with immutable history

### Enterprise Features

- **Multi-tenancy**: Organization-scoped resources with tenant-aware rate limiting
- **Workflow Management**: Approve/reject/hold decisions with escalation rules
- **Audit Logging**: Immutable audit logs for compliance (SOX, HIPAA, etc.)
- **SMS Integration**: Twilio + plivo fallback for multi-vendor resilience
- **Dashboard Builder**: Drag-and-drop analytics dashboard configuration

### Developer Experience

- **Live Reload**: Dev mode with code hot-reload to container
- **Type Safety**: Pydantic schemas + type hints
- **Structured Logging**: JSON logs with correlation IDs and tracing spans
- **Test Coverage**: Unit, integration, and E2E tests with 80%+ coverage

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose Stack                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   MongoDB     │  │    Redis     │  │   Elasticsearch│         │
│  │    (DB)       │  │ (Cache/Broker)│  │  (Search Logs) │        │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                      form-backend                                 │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Flask App    │  │ Celery       │  │ Celery Beat  │          │
│  │  (5000)      │  │  Worker      │  │  Scheduler   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    Blueprints                            │    │
│  │  /forms, /responses, /workflows, /dashboards, /ai       │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                Middleware Layers                          │    │
│  │  Request ID, Tenant DB, WAF, JWT, CORS, Rate Limit       │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                   Observability Stack                             │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Sentry     │  │ OpenTelemetry │  │   ELK Stack  │          │
│  │ (Error Logs) │  │  (Tracing)   │  │  (Metrics)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Separation of Concerns**: Blueprints for feature areas, services for business logic
2. **Tenant-Aware**: Organization ID from JWT header scopes all resources
3. **Fail Fast**: Validation at boundaries, graceful degradation on failures
4. **Audit-Ready**: Immutable logs with correlation IDs and tracing spans

---

## Quick Start

### Prerequisites

- Docker 24.0+ and Docker Compose 2.24+
- Make (optional, for convenience commands)
- 2GB+ RAM available for containers

### Installation

1. **Clone and Configure**:

```bash
cp .env.example .env
# Edit .env with your secrets (JWT_SECRET_KEY, MONGO_URI, etc.)
```

2. **Start Services**:

```bash
# Production mode (recommended)
make up

# Development mode with auto-reload
make up-dev
```

3. **Check Status**:

```bash
make ps        # List running containers
make logs      # Follow application logs
make logs-worker  # Follow Celery worker logs
```

4. **Access the API**:

```bash
# Backend API (development)
curl http://localhost:5000/api/v1/forms/

# Production
curl http://localhost:${PORT:-8051}/api/v1/forms/
```

---

## Development Setup

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Application
APP_NAME=forms-backend
APP_ENV=development
DEBUG=true

# Authentication
JWT_SECRET_KEY=your-super-secret-key-here-min-32-chars
JWT_ALGORITHM=HS256

# MongoDB
MONGODB_URI=mongodb://mongo:27017/forms

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Optional: Sentry, Elastic, Celery
SENTRY_DSN=
ELASTICSEARCH_URL=
CELERY_BROKER_DB=1
```

### Development Commands

```bash
# Build images (cached)
make build

# Start production stack
make up

# Start dev stack (hot-reload enabled)
make up-dev

# Run all tests
make test

# Run tests with coverage
make test-cov

# Lint and type check
make lint

# Bootstrap MongoDB indexes
make bootstrap

# Open shell in backend container
make shell
```

### Hot Reload Workflow

When using `make up-dev`:

1. Edit code in `/home/ravi/workspace/docker/apps/form-backend`
2. Changes are bind-mounted to `/app/` in container
3. Flask auto-reloads on file modification
4. Logs streamed to `./logs/`

---

## Project Structure

```
form-backend/
├── app.py                      # Application factory
├── config/
│   ├── settings.py             # Environment-agnostic settings
│   ├── logging.py              # Logging configuration
│   └── tracing.py              # OpenTelemetry setup
├── extensions.py               # Flask extensions initialization
├── middleware/
│   ├── request_id.py          # Request ID middleware
│   ├── tenant_db.py           # Tenant-scoped DB sessions
│   ├── security_waf.py        # WAF rules
│   └── __init__.py
├── routes/
│   └── v1/
│       ├── auth_route.py      # Auth endpoints
│       ├── form.py            # Form CRUD
│       ├── responses.py       # Responses handling
│       ├── workflows.py       # Workflow engine
│       ├── dashboards.py      # Dashboard builder
│       └── ... (more)
├── services/                   # Business logic layer
│   ├── form_service.py        # Form creation/editing
│   ├── response_service.py    # Response processing
│   ├── workflow_service.py    # Workflow state machine
│   ├── ai_service.py          # AI inference
│   └── ... (more)
├── tasks/                      # Celery tasks
│   └── process_responses.py   # Async processing
├── scripts/                    # Utility scripts
│   └── bootstrap_resources.py # Initial DB setup
├── tests/                      # Test suite
├── Makefile                    # Build/test commands
└── docker-compose.yml          # Multi-container setup
```

---

## API Reference

### Authentication

All API endpoints require a JWT token in the `Authorization` header:

```http
Authorization: Bearer <JWT_TOKEN>
X-Organization-ID: <org_id>
```

### Rate Limiting

- Default: 2000 requests/hour per tenant
- Burst: 100 requests/minute
- Storage: Redis-backed with blocklist support

### Base Response Format

```json
{
  "success": true,
  "data": {},
  "meta": {
    "request_id": "abc123",
    "timestamp": "2024-01-01T00:00:00Z"
  }
}
```

### Error Handling

```json
{
  "success": false,
  "error": "Validation failed",
  "code": "VALIDATION_ERROR",
  "details": [
    {
      "field": "email",
      "message": "Invalid email format"
    }
  ]
}
```

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/forms/` | GET | List forms (paginated) |
| `/api/v1/forms/` | POST | Create new form |
| `/api/v1/forms/{id}/` | GET | Get form details |
| `/api/v1/forms/{id}/` | PUT | Update form |
| `/api/v1/forms/{id}/publish/` | POST | Publish form |
| `/api/v1/forms/{id}/draft/` | POST | Save as draft |
| `/api/v1/forms/{id}/archive/` | POST | Archive form |
| `/api/v1/auth/login/` | POST | User authentication |
| `/api/v1/auth/refresh/` | POST | Refresh JWT token |

See `/docs` for full Swagger documentation.

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_NAME` | Application name | `forms-backend` |
| `APP_ENV` | Environment | `development` |
| `DEBUG` | Debug mode | `false` |
| `JWT_SECRET_KEY` | JWT signing key | - |
| `MONGODB_URI` | MongoDB connection string | - |
| `REDIS_HOST` | Redis host | `localhost` |
| `REDIS_PORT` | Redis port | `6379` |
| `SENTRY_DSN` | Sentry DSN | - |
| `ELASTICSEARCH_URL` | Elastic URL | - |

### Flask Configuration

```python
from config.settings import settings

app.config.from_mapping(
    SECRET_KEY=settings.JWT_SECRET_KEY,
    DEBUG=settings.DEBUG,
    JWT_SECRET_KEY=settings.JWT_SECRET_KEY,
    JWT_TOKEN_LOCATION=["headers", "cookies"],
    JWT_COOKIE_SECURE=not settings.DEBUG,
    # ... more settings
)
```

---

## Testing

### Test Categories

```bash
# Run all tests
make test

# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# E2E tests with Playwright
pytest tests/e2e/

# With coverage report
make test-cov

# Coverage dashboard
coverage html
```

### Test Structure

```
tests/
├── unit/
│   ├── test_form_service.py
│   ├── test_response_service.py
│   └── ...
├── integration/
│   ├── test_api_forms.py
│   ├── test_api_auth.py
│   └── ...
├── e2e/
│   └── test_form_workflow.py
└── conftest.py
```

### Example Test

```python
def test_create_form():
    """Test creating a form via API."""
    client = app.test_client()
    response = client.post(
        "/api/v1/forms/",
        json={
            "name": "Test Form",
            "schema": {"fields": []}
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 201
    assert response.json["success"] is True
```

---

## Deployment

### Production Checklist

- [ ] Set `APP_ENV=production` and `DEBUG=false`
- [ ] Generate strong JWT keys (`secrets.token_urlsafe(64)`)
- [ ] Configure MongoDB authentication
- [ ] Set up Sentry DSN for error monitoring
- [ ] Configure Elasticsearch for log aggregation
- [ ] Enable HTTPS (set `FORCE_HTTPS=true`)
- [ ] Set up backup strategy for MongoDB

### Docker Deployment

```bash
# Build production images
make build

# Start production stack
make up

# View logs
make logs
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: forms-backend
spec:
  containers:
  - name: backend
    image: forms-backend:latest
    ports:
    - containerPort: 5000
```

---

## Security

### Implemented Controls

- **Authentication**: JWT with refresh token rotation
- **Authorization**: RBAC with permission scopes
- **Rate Limiting**: Tenant-aware limits via Redis
- **CORS**: Configurable origins with credentials control
- **WAF**: ModSecurity rules for attack mitigation
- **Data Encryption**: TLS in transit, at-rest encryption via MongoDB
- **Audit Logging**: Immutable logs for compliance

### Default Security Settings

```python
# app.py security headers
talisman.init_app(
    app,
    force_https=False,  # Enable in production
    strict_transport_security=True,
    content_security_policy=None,
)
```

---

## Monitoring & Observability

### Logging

Structured JSON logs with correlation IDs:

```json
{
  "request_id": "req-abc123",
  "logger": "forms-backend.routes.form",
  "level": "INFO",
  "message": "Form created successfully",
  "data": {"form_id": "form-xyz"}
}
```

### Tracing

OpenTelemetry integration with:

- **Service Name**: `forms-backend`
- **Exporter**: OTLP or JSON file
- **Spans**: MongoDB queries, HTTP requests, Celery tasks

### Metrics

- Request counts per endpoint (Prometheus-compatible)
- MongoDB query performance
- Redis latency
- Celery task execution time

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Container won't start | Check MongoDB/Redis connectivity |
| "MongoDB not found" error | Ensure MongoDB is running before startup |
| JWT errors | Verify `JWT_SECRET_KEY` is configured |
| Rate limit exceeded | Wait or increase limits in Redis |
| Celery queue empty | Run `make up` with worker |

### Debug Mode

```bash
# Enable debug logging
make up-dev

# Open shell in container
make shell

# Check MongoDB connection
mongoconnect() { mongosh mongodb://mongo:27017/admin -u admin -p <password> }
```

---

## Contributing

### Development Workflow

1. Fork and clone the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests locally (`make test`)
5. Ensure code style (`make lint`)
6. Commit your changes
7. Push to the branch and create a Pull Request

### Code Style

- Follow PEP 8
- Use type hints where appropriate
- Write meaningful commit messages
- Add tests for new features

### Pull Request Guidelines

- One feature per PR
- Include tests for new functionality
- Update documentation if needed
- Ensure all tests pass

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

## Support

- **Issues**: Create an issue on GitHub
- **Documentation**: See `/docs` for Swagger UI
- **Internal**: Contact the RIDP platform team
