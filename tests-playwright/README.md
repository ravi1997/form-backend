# Playwright API Test Suite for Form Backend

This directory contains the Playwright-based end-to-end API test suite for the `form-backend` project. 
It focuses strictly on testing backend API routes, auth flows, tenant isolation, and business logic.

## Prerequisites

- Node.js (v18+)
- Form Backend must be running locally (e.g., `make up-dev` from `apps/form-backend`)
- Appropriate `.env` file configured (copy `.env.example` to `.env`)

## Installation

```bash
cd apps/form-backend/tests-playwright
npm install
```

## Running Tests

Ensure the API is accessible at the `API_BASE_URL` defined in your `.env` (default is `http://localhost:8051`).

**Run all tests:**
```bash
npm test
```

**Run specific test groups:**
```bash
npm run test:api       # Runs all API-level unit tests
npm run test:auth      # Runs only authentication tests
npm run test:flows     # Runs end-to-end multi-step flows
npm run test:tenancy   # Runs tenant isolation tests
npm run test:ai        # Runs AI-specific tests
```

**Run tests in UI mode (for debugging):**
```bash
npm run test:ui
```

## Test Structure

- `helpers/`: Reusable functions for authentication and data generation.
- `tests/api/`: Domain-specific API endpoint tests (auth, forms, users, etc.).
- `tests/flows/`: Complex, multi-step business flows.
- `tests/negative/`: Error handling and invalid payload tests.
- `tests/security/`: RBAC and authorization checks.
- `tests/tenancy/`: Strict data isolation tests between organizations/tenants.

## Notes on Test Data
Tests use the `data-factory.ts` helper to generate unique users, forms, and responses dynamically to prevent data collisions during parallel execution. Do not rely on hardcoded IDs.
