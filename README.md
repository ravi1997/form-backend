# Forms Backend

A high-performance, containerized backend for building, publishing, and analyzing forms and surveys. Built with Python, Flask, MongoDB, and Redis.

## Features

- **Form Builder**: Flexible MongoDB schemas supporting robust conditional logic and validations.
- **Role-Based Access Control**: Granular permissions (Maker-Checker, view, edit) and user groups.
- **Workflow & Analytics**: Configurable multi-step approval workflows and analytics dashboards.
- **Robust Infrastructure**: Containerized with Docker, background tasks via Celery, unified logging, and Sentry integration.
- **Authentication**: Secure JWT-based auth with strict rate-limiting and redis-backed blocklisting.

## Prerequisites

- Docker and Docker Compose
- Make

## Quick Start

1. **Clone & Configure**:

   ```bash
   cp .env.example .env
   # Update JWT_SECRET_KEY and other credentials in .env
   ```

2. **Start Services**:

   ```bash
   make up-dev
   ```

3. **Check Status**:

   ```bash
   make logs
   ```

## Development Commands

The provided `Makefile` makes development easy:

- `make build` : Build docker images
- `make up` : Start production mode
- `make up-dev` : Start in development mode with auto-reload
- `make test` : Run tests inside the container
- `make shell` : Drop into bash inside the backend container

## Testing

To run the automated test suite:

```bash
make test
```

## Security

- Default Sentry config does **not** send PII data.
- MongoDB requires authentication in production.
- Use strong, generated keys for your `.env` file.
