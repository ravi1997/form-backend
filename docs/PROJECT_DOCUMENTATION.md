# Forms Backend Project Documentation

## 1. Project Overview

**Forms Backend** is a high-performance, containerized backend for building, publishing, and analyzing forms and surveys. Built to support complex form logic, the application uses MongoDB for flexible schemas, Redis for caching and session management, Elasticsearch for search functionality, and Celery for asynchronous background tasks.

### Core Functionality & Key Features

* **Form Builder**: Flexible MongoDB schemas supporting robust conditional logic and validations.
* **Role-Based Access Control (RBAC)**: Granular permissions (Maker-Checker, view, edit) mapped to user groups.
* **Workflow & Analytics**: Configurable multi-step approval workflows and analytics dashboards built on Elasticsearch.
* **Robust Infrastructure**: Fully containerized using Docker, with Celery-based background task execution.
* **Authentication & Security**: Secure JWT-based authentication featuring strict rate-limiting and Redis-backed token blocklisting.
* **Observability**: Integrated with Sentry for error tracking and a unified logging system for centralized audit and debug trails.

### High-Level Architecture

* **Web Framework**: Flask (Python)
* **Primary Database**: MongoDB (MongoEngine for ORM-like access)
* **Caching & Task Queue Broker**: Redis
* **Search & Analytics Index**: Elasticsearch
* **Background Workers**: Celery
* **Monitoring & Error Tracking**: Sentry

---

## 2. Installation Guide

This section covers setting up the project locally for development and running it via Docker.

### Prerequisites

* Docker (v20.10+) and Docker Compose (v2.0+)
* Make (GNU Make)
* Git

### Step-by-Step Installation

1. **Clone the Repository**:

    ```bash
    git clone <repository_url>
    cd forms-backend
    ```

2. **Environment Setup**:
    Copy the sample environment variable file and modify it to suit your needs:

    ```bash
    cp .env.example .env
    ```

    *Ensure you set secure values for `JWT_SECRET_KEY` and database credentials in the `.env` file.*

3. **Start Services**:
    Using the provided `Makefile`, you can quickly spin up all required containers:

    ```bash
    make up-dev  # Starts the project in development mode with auto-reloading
    ```

    To start the project in production mode (without auto-reload):

    ```bash
    make up
    ```

4. **Check Service Status**:
    Validate that all services (Flask backend, MongoDB, Redis, Elasticsearch, Celery) are running:

    ```bash
    make logs
    ```

### Troubleshooting Common Installation Issues

* **Port Conflicts**: Ensure that ports 5000 (Flask), 27017 (MongoDB), 6379 (Redis), 9200 (Elasticsearch), and 9000 (Sentry) are not in use by other local services.
* **Docker Daemon Not Running**: If `make up-dev` fails, ensure the Docker background daemon is running.
* **Elasticsearch Startup Error**: Elasticsearch may require an increase in `vm.max_map_count`. Run `sysctl -w vm.max_map_count=262144` (on Linux) if it keeps crashing.

---

## 3. Configuration

The application is heavily configured via environment variables.

### Key Environment Files

* `.env`: Main configuration file for secrets, credentials, and environment overrides. Validated on startup by `pydantic-settings`.

### Core Settings

* `APP_ENV`: Specifies the environment (`development`, `staging`, `production`).
* `JWT_SECRET_KEY`: Very important. A strong randomized string used to sign user tokens.
* `MONGODB_URI`: Connection string for the database (e.g., `mongodb://db:27017/forms_db`).
* `REDIS_HOST` / `REDIS_PORT`: Used to communicate with the Redis caching, session, and broker layer.
* `ELASTICSEARCH_URL`: Used for connection to the local/remote search cluster.
* `SENTRY_SECRET_KEY`: Used to initialize tracing and bug captures.

### Third-Party Services Integration

* **Sentry SDK**: Configure your internal or cloud-based Sentry instance via `.env` parameter `SENTRY_DSN`.

---

## 4. Usage Guide

### Using the APIs (End-User flow)

As a backend service, interaction primarily occurs via RESTful endpoints.

1. **Authentication**: Start by calling the login endpoint (e.g., `/api/auth/login`) with your credentials. On success, you will receive an `access_token` and `refresh_token`.
2. **Authorization Header**: In subsequent API calls, include the `access_token` in the HTTP Authorization header: `Authorization: Bearer <your_access_token>`.
3. **Form Creation**: Issue a POST request to the `/api/forms` endpoint to create a form schema mapping conditional logic, validation points, and structural layouts.
4. **Submission Processing**: Users end interacting with forms trigger POSTs to the form submission endpoints mapping to background Celery validation routines.

### Dashboard & External Interaction

Generally, an accompanying Frontend (React/Vue/Dart) consumes these APIs. Ensure the matching UI client is configured to base route against `http://localhost:5000/api/v1`.

---

## 5. API Documentation

We offer robust JSON-based endpoints. Most endpoints require standard Bearer Token Auth.

* *Note: Specific parameter documentation is normally accessible through Swagger UI (if configured via `swasg-ui` extensions in Flask). Below is the high-level outline.*

### Common Endpoints

* `POST /auth/login` - Authenticate an existing user.
  * **Payload**: `{"email": "user@example.com", "password": "password"}`
  * **Response**: `{"access_token": "...", "refresh_token": "..."}`
* `GET /health` - Service health-check (public endpoint).
  * **Response**: `{"status": "healthy", "env": "production"}`

### Responses & Error Handling

All APIs default to JSON outputs. Failed requests return descriptive messages along with HTTP Error Codes. Example:

```json
{
  "error": "Resource not found"
}
```

---

## 6. Code Documentation

The project follows a standard 3-tier structure architecture to keep the codebase clean:

* **Models (`/models`)**: MongoEngine schemas detailing database documents, custom behavior hooks, and validation restrictions.
* **Services (`/services`)**: Core business rules and logic abstractions (e.g., `user_service.py`, `redis_service.py`). Includes the background implementation context.
* **Routes (`/routes`)**: Flask Blueprints containing API endpoints. Controllers only validate incoming payloads via Pydantic/Marshmallow and pass data to the underlying services.
* **Tasks (`/tasks`)**: Celery tasks designated for heavy asynchronous work, such as processing analytics aggregates and handling webhooks.
* **App Factory (`app.py`)**: Responsible for initial container injections, wiring logging setups, attaching error handlers, extensions (like JWT), and connecting to datastores.

---

## 7. Testing Documentation

We utilize `pytest` to implement our unit and integration tests. Test mock frameworks are heavily utilized to decouple component testing.

### Running Tests

To run tests in an isolated Docker container, use the provided `make` command:

```bash
make test
```

This triggers the `pytest` test suite with `pytest-cov`, providing standard output containing code coverage metrics.

### Adding Coverage

New functionality must be accompanied by relevant unit test scripts located in the `/tests/` directory ensuring high code coverage over primary logical paths.

---

## 8. Deployment Guide

### Target Infrastructure

Forms Backend is designed to be cloud-agnostic using Docker containers. Popular targets include:

1. **AWS ECS / EKS**: Use the generated images inside an orchestrator.
2. **Docker Swarm / VM Docker Compose**: Useful for smaller, on-premise deployments.

### Production Recommendations

* **Security Context**: Make sure all environment variables are properly populated and isolated through a secrets manager rather than explicit files.
* **Reverse Proxy**: Do not expose Flask's underlying WSGI Gunicorn server directly. Front it with a reverse proxy like Nginx or AWS API Gateway to handle TLS termination.
* **Database Authentication**: Validate `MONGODB_URI` points securely authenticated instances, ensuring Role-Based Access controls within Mongo.

---

## 9. Contribution Guidelines

We encourage external contribution following these basic steps:

1. **Fork & Clone**: Fork the repository on the main version control provider and clone your copy.
2. **Local Setup**: Ensure Docker and Make are functioning locally. Run `make up-dev`.
3. **Branching Standard**: Branch from `main` using standard naming conventions (e.g., `feature/awesome-addition` or `fix/broken-logic`).
4. **Writing Tests**: Add and test your modifications using `make test`.
5. **Code Style**: Observe Python's PEP 8 guidelines. A `.flake8` file is included in the project for automatic linting references.
6. **Pull Request**: Submit a Pull Request outlining modifications with a clear summary attached.

---

## 10. Licensing and Legal Information

This project is licensed under the standard MIT License, giving users and developers permissive access to modify, copy, and distribute without warranty.

*A formal LICENSE file should be located at the top-level directory outlining complete legal statements.*

---

## 11. Troubleshooting & FAQ

**Q: I get a `Connection Refused` error when attempting to hit `http://localhost:5000/health`.**
A: Ensure the Flask container is healthy. Run `make logs` to determine if a database connection error blocked startup.

**Q: Background tasks via Celery aren't processing.**
A: Ensure the `forms_worker` container is active in your `docker-compose.yml` block and functioning without runtime exceptions.

**Q: How do I access standard logs while running remotely?**
A: Logs are configured to output both securely to the console and onto persistent files within the `./logs` mounted directory.

---

## 12. Changelog / Release Notes

*(This section will be manually maintained per tag rollout)*

**v1.0.0**

* Initial Public Backend Release.
* Integrating JWT security and RBAC.
* Providing Celery infrastructure.

---

## 13. Future Work & Roadmap

* **Expanded Analytical Insight**: Better AI-driven processing through extended models via celery queues utilizing Elasticsearch aggregates.
* **Webhooks Refinement**: Native capabilities sending form submissions immediately securely against third-party consumers.
* **GraphQL Layer**: Addition of an advanced query endpoint to minimize HTTP REST over-fetching problems.

---

## 14. Contact Information

For inquiries, support, or security-related concerns:

* **Community Forums**: Visit the open issue tracker in the relevant Git Repository.
* **Documentation Site**: Visit our external domain / Wiki for broader configuration tutorials.
