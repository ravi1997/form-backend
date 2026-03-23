# Form Backend Playwright API Tests

This directory contains a comprehensive Playwright-based API test suite for the `form-backend` project.

## Project Structure

```text
tests-playwright/
├── helpers/               # Reusable test helpers (auth, data-factory)
├── tests/                 # Test suites
│   ├── api/               # API endpoint tests (auth, forms, responses, etc.)
│   ├── flows/             # End-to-end business flows
│   ├── negative/          # Error handling and validation tests
│   ├── security/          # RBAC and security tests
│   └── tenancy/           # Tenant isolation tests
├── playwright.config.ts   # Playwright configuration
└── package.json           # Test dependencies and scripts
```

## Setup

1.  **Install dependencies**:
    ```bash
    cd apps/form-backend/tests-playwright
    npm install
    ```

2.  **Configure environment**:
    Create a `.env` file based on `.env.example`:
    ```bash
    cp .env.example .env
    ```
    Ensure `API_BASE_URL` points to your running `form-backend` instance (default: `http://localhost:8051`).

## Running Tests

From the `tests-playwright` directory:

-   **Run all tests**: `npm test`
-   **Run specific group**:
    -   Auth: `npm run test:auth`
    -   API: `npm run test:api`
    -   Flows: `npm run test:flows`
    -   Tenancy: `npm run test:tenancy`
    -   AI: `npm run test:ai`

From the project root:
-   `npm run test:form-backend`

## Key Testing Areas

-   **Authentication**: Registration, Login, Refresh Token, Logout.
-   **RBAC**: Role-based access control (Admin, Creator, User, Approver).
-   **Tenancy**: Strict isolation between different organizations.
-   **Forms & Responses**: CRUD, Publishing, Versioning, Submissions, Validation.
-   **Workflows**: Workflow creation and triggering.
-   **AI & Analytics**: Health, Summarization, Dashboard stats.
-   **Negative Testing**: Error codes, malformed payloads, unauthorized access.
