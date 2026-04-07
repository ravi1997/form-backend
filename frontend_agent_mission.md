# Frontend Resolution Mission Briefing

## Context
You are a Flutter/Dart expert tasked with resolving **30 compatibility issues** between the RIDP Form Platform frontend and its Python/Flask/MongoDB backend. The backend enforces strict multi-tenancy and data isolation rules.

## Core Backend Rules (Source of Truth)
From `/form-backend/AGENTS.md`:
- **Multi-Tenancy**: All queries MUST use `organization_id`. The frontend refers to this incorrectly as `tenant_id` in many places.
- **Delete Policy**: Soft-delete ONLY (`is_deleted = true`).
- **Input Validation**: Backend uses Pydantic V2. Requests MUST match the defined schemas exactly.
- **Response Format**: All responses are wrapped: `{"success": true, "data": {...}, "message": "..."}`.
- **API Prefix**: All routes are prefixed with `/form/api/v1/`.

## High Priority Issues (Critical Fixes)

### 1. Tenant Field Mismatch
- **Location**: `lib/features/auth/domain/entities/user.dart` (~line 20)
- **Problem**: Frontend uses `tenant_id`.
- **Fix**: Rename `@JsonKey(name: 'tenant_id')` to `organization_id`. Update the `User` entity and all derived models.

### 2. Registration Schema Mismatch
- **Location**: `lib/features/auth/domain/repositories/auth_repository.dart`
- **Problem**: Frontend sends `userType` and `employeeId`.
- **Fix**: 
    - Remove `userType` (not a backend field).
    - Rename `employeeId` to `employee_id`.
    - Ensure `organization_id` is sent if required.

### 3. FormResponse Model Mismatch
- **Location**: `lib/features/responses/domain/entities/form_response.dart`
- **Problem**: 
    - Frontend expects `formId` -> Backend returns `form`.
    - Frontend expects `answers` -> Backend returns `data`.
- **Fix**: Update `@JsonKey` mappings to match:
    - `@JsonKey(name: 'form') required String formId`
    - `@JsonKey(name: 'data') required Map<String, dynamic> answers`
    - Verify `submitted_by` and `organization_id` are captured.

## Medium Priority Issues (Functional Fixes)

### 4. Admin Role Detection
- **Location**: `lib/features/auth/domain/entities/user.dart` (~lines 35-39)
- **Problem**: Frontend checks `roles.contains('admin')` or `userType == 'admin'`.
- **Fix**: Use the backend's explicit `is_admin` (bool) field and `roles` (list of strings). Remove logic relying on `userType`.

### 5. Form Submission Data Keys
- **Problem**: Frontend sends field IDs (e.g., `field_123`) in the `data` map.
- **Fix**: Backend expects **Question Variable Names** (e.g., `patient_name`, `age`). Ensure the submission logic maps question IDs to their variable names before POSTing.

### 6. User Activity Endpoint
- **Location**: `lib/core/network/api_endpoints.dart` (~line 132)
- **Problem**: Frontend calls `/user/users/$userId/activity`.
- **Fix**: Backend returns lock info via `GET /user/security/lock-status/<userId>`. Adjust expectations to handle `is_locked`, `lock_until`, and `failed_login_attempts`.

## Low Priority & Endpoint Alignments
- Verify that standard CRUD paths for **Sections**, **Translations**, **AI Suggestions**, and **Bulk Exports** are correctly prefixed with `/form/api/v1/`.
- Ensure **Refresh Token** logic uses the `Authorization: Bearer <refresh_token>` header instead of just the request body for consistency.

## Goal
Update all Dart entities, JSON serialization logic, and API service methods so that every frontend request perfectly matches the backend Pydantic schemas and every response correctly parses the `data` wrapper.

Refer to `docs/backend-doc/` for any additional schema details.
