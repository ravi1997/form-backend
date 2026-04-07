# Frontend-Backend Compatibility Issues

Based on analysis of `backend-doc/` documentation and frontend Flutter code.

| # | Issue | Frontend | Backend | Severity |
|---|------|---------|---------|----------|
| 1 | Tenant field name | `tenant_id` in User entity | `organization_id` in all MongoDB models | **High** |
| 2 | User login identifier | Sends `identifier` field | Accepts `email`, `username`, `employee_id`, or `identifier` with `password` | **Medium** |
| 3 | User status endpoint | Uses `/user/status` | Also available at `/user/profile` | Low |
| 4 | Register request body | Sends `userType`, `employeeId`, `mobile`, `roles` | Accepts `email`, `username`, `password`, `mobile`, `employee_id`, `roles`, `organization_id`. Does NOT have `userType` field | **High** |
| 5 | FormResponse model | Has `formId`, `answers` (data field), `status`, `aiResults` | Returns `form` (id), `data`, `submitted_by`, `organization_id`, `ip_address`, `user_agent` | **High** |
| 6 | Roles handling | `userType` (string) and `isAdminFlag` (bool) in User entity | Uses `roles` list + separate `is_admin` boolean field | **Medium** |
| 7 | User profile response | Expects `user` wrapper object | Returns nested `user` object under `data.user` | Medium |
| 8 | OTP login | Uses same `/auth/login` endpoint with mobile+otp | Uses same endpoint but different body schema | Low |
| 9 | Form versions | `/forms/{formId}/versions` | Backend supports this route | Low |
| 10 | Dashboard stats endpoint | Uses `/analytics/dashboard` | Backend uses `/analytics/dashboard` | Low |
| 11 | Admin list users | `/user/users` (paginated) | Backend supports pagination with `page` and `page_size` query params | Low |
| 12 | User activity endpoint | `/user/users/{userId}/activity` | Backend: `/user/security/lock-status/{userId}` returns lock info, not full activity | **Medium** |
| 13 | Change password endpoint | `/user/change-password` with `current_password` and `new_password` | Backend requires `current_password` and `new_password` | Low |
| 14 | Lock/unlock user | `/user/users/{userId}/lock`, `/user/users/{userId}/unlock` | Backend has these endpoints | Low |
| 15 | Form submission data | Sends `{ data: { field: value } }` | Backend expects `{ data: { variable_name: value } }` - uses variable names not field IDs | **Medium** |
| 16 | Form publish response | Expects `{ task_id: string }` in 202 response | Backend returns `{ task_id: string }` correctly | Low |
| 17 | Refresh token | Sends body with `refresh_token` | Backend accepts Bearer header or cookie, body optional | Low |
| 18 | Logout | Sends POST to `/auth/logout` | Backend expects JWT, clears cookies and adds JTI to blocklist | Low |
| 19 | Revoke all sessions | `/auth/revoke-all` | Backend supports this | Low |
| 20 | Request password reset | `/auth/request-password-reset` | Backend supports this | Low |
| 21 | Form template list | `/forms/templates` | Backend supports `is_template=true` filtering | Low |
| 22 | Section management | CRUD at `/forms/{formId}/sections` | Backend supports full section CRUD | Low |
| 23 | Form translations | `/forms/translations` endpoint | Backend supports get/save translations | Low |
| 24 | Translation jobs | `/forms/translations/jobs` | Backend supports async translation jobs | Low |
| 25 | AI generate form | `/ai/generate` | Backend has Ollama integration | Low |
| 26 | AI suggestions | `/ai/suggestions` | Backend supports field suggestions | Low |
| 27 | NLP/Semantic search | `/ai/forms/{formId}/nlp-search`, `/ai/forms/{formId}/semantic-search` | Backend has Elasticsearch + Ollama embeddings | Low |
| 28 | Form analytics | `/forms/{formId}/analytics` | Backend supports analytics | Low |
| 29 | Export responses | `/forms/{formId}/export/{format}` | Backend supports CSV/JSON export | Low |
| 30 | Bulk export | `/forms/export/bulk` | Backend uses Celery for async | Low |

---

## Detailed Issue Explanations

### Issue #1: Tenant ID Field Name Mismatch (HIGH PRIORITY)

**Location:**
- Frontend: `lib/features/auth/domain/entities/user.dart` line 20

**Problem:**
The frontend uses `tenant_id` in the User entity while the backend uses `organization_id` across all MongoDB models for multi-tenancy isolation.

**Backend Documentation (overview.md, section 6):**
> Every MongoEngine document model includes an `organization_id` field. Tenancy is enforced at three independent layers.

**Frontend Code:**
```dart
@Default('default_tenant') @JsonKey(name: 'tenant_id') String tenantId,
```

**Impact:**
- User sessions will have incorrect tenant context
- Data isolation may fail between organizations
- All queries will use wrong tenant identifier

**Backend Expects:**
```json
{ "organization_id": "org-uuid" }
```

---

### Issue #2: User Login Identifier Field (MEDIUM PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_service.dart` login method

**Problem:**
The frontend sends login requests with an `identifier` field. The backend accepts multiple identifier types.

**Frontend Sends:**
```json
{ "identifier": "user@example.com", "password": "secret123" }
```

**Backend Accepts (auth.md, lines 80-81):**
> Identifier can be: `email`, `username`, `employee_id`, or `identifier`. At least one must be present with `password`.

**Impact:**
- Currently compatible but could be more explicit
- Backend also supports separate `email` field

---

### Issue #3: User Status Endpoint Path (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` line 74

**Problem:**
Frontend uses `/user/status` but backend documentation shows both `/user/status` and `/user/profile` are available.

**Frontend Uses:**
```dart
static const String userStatus = '/user/status';
```

**Backend Documentation (user.md, line 35):**
> **Also available at:** `GET /form/api/v1/user/status`

**Impact:**
- Low - both endpoints work
- Minor inconsistency in documentation reference

---

### Issue #4: Register Request Body Mismatch (HIGH PRIORITY)

**Location:**
- Frontend: `lib/features/auth/domain/repositories/auth_repository.dart` line 12-19
- Frontend: `lib/core/network/api_endpoints.dart` line 39-49

**Problem:**
The register function sends fields that don't match the backend schema.

**Frontend Sends:**
```json
{
  "username": "john_doe",
  "email": "user@example.com",
  "password": "secret123",
  "userType": "user",
  "employeeId": "EMP001",
  "mobile": "9876543210"
}
```

**Backend Expects (auth.md, lines 31-39):**
```json
{
  "email": "user@example.com",
  "username": "john_doe",
  "password": "secret123",
  "mobile": "9876543210"
}
```

Schema: `UserCreateSchema` (Pydantic)

**Differences:**
1. Frontend sends `userType` - Backend does NOT have this field
2. Frontend sends `employeeId` - Backend expects `employee_id` (snake_case)
3. Backend expects optional `roles` array and `organization_id`
4. Frontend sends `roles` but not in the format backend expects

**Impact:**
- Registration may fail or create users with incorrect data
- Employee ID won't be saved correctly due to naming mismatch

---

### Issue #5: FormResponse Model Mismatch (HIGH PRIORITY)

**Location:**
- Frontend: `lib/features/responses/domain/entities/form_response.dart`

**Problem:**
The frontend FormResponse entity fields don't match what the backend returns.

**Frontend Defines:**
```dart
const factory FormResponse({
  @JsonKey(name: '_id') required String id,
  @JsonKey(name: 'form') required String formId,
  @JsonKey(name: 'submitted_at', ...) required DateTime? submittedAt,
  @JsonKey(name: 'data') required Map<String, dynamic> answers,
  @JsonKey(name: 'ai_results') @Default({}) Map<String, dynamic> aiResults,
  @Default('pending') String status,
})
```

**Backend Returns (forms-responses.md, lines 100-123):**
```json
{
  "id": "uuid",
  "form": "form-uuid",
  "organization_id": "org-uuid",
  "data": { "patient_name": "John", ... },
  "submitted_by": "user-uuid",
  "submitted_at": "2026-04-01T10:30:00Z",
  "status": "submitted",
  "ip_address": "10.0.0.1",
  "user_agent": "Mozilla/5.0..."
}
```

**Mapping Issues:**
1. Frontend expects `formId` - Backend returns `form`
2. Frontend expects `answers` - Backend returns `data`
3. Backend returns `submitted_by`, `organization_id`, `ip_address`, `user_agent` - Frontend doesn't have these fields
4. Frontend has `ai_results` - Backend doesn't return this in standard response

**Impact:**
- Response data will fail to parse correctly
- Missing fields like `submitted_by` for audit trails

---

### Issue #6: Roles Handling Mismatch (MEDIUM PRIORITY)

**Location:**
- Frontend: `lib/features/auth/domain/entities/user.dart` lines 35-39

**Problem:**
Frontend computes admin status differently than backend structure.

**Frontend Computation:**
```dart
bool get isAdmin =>
    roles.contains('admin') ||
    roles.contains('superadmin') ||
    isAdminFlag ||
    userType.toLowerCase() == 'admin';
```

**Backend Structure (overview.md, lines 369-370):**
```json
{
  "roles": ["user"],
  "is_admin": false
}
```

**Impact:**
- Inconsistent admin detection
- UI may show incorrect permissions
- `userType` is not a backend concept

---

### Issue #7: User Profile Response Wrapper (MEDIUM PRIORITY)

**Location:**
- Frontend: Auth service parsing user from response

**Problem:**
Backend wraps user in nested object, frontend may expect different structure.

**Backend Returns (user.md, lines 37-55):**
```json
{
  "success": true,
  "data": {
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "username": "john_doe",
      "roles": ["user"],
      "organization_id": "org-uuid",
      "is_active": true,
      "is_admin": false
    }
  }
}
```

**Frontend Expects:**
Direct user object or different nesting

**Impact:**
- User profile may fail to parse correctly

---

### Issue #8: OTP Login Schema (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_service.dart` line 52

**Problem:**
OTP login uses same endpoint as password login with different body schema.

**Frontend Sends (mobile + otp):**
```json
{ "mobile": "9876543210", "otp": "123456" }
```

**Backend Accepts (auth.md, lines 82-88):**
```json
{
  "mobile": "9876543210",
  "otp": "123456"
}
```

**Impact:**
- Compatible - works correctly

---

### Issue #9: Form Versions Endpoint (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` line 206

**Problem:**
None - endpoint is aligned.

**Frontend:**
```dart
static String getFormVersions(String formId) => '/forms/$formId/versions';
```

**Backend:**
Route exists for version management (forms.md)

**Impact:**
- None - working correctly

---

### Issue #10: Dashboard Stats Endpoint (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` line 600

**Problem:**
None - endpoint is aligned.

**Frontend:**
```dart
static const String getDashboardStats = '/analytics/dashboard';
```

**Backend (blueprints/dashboard.md):**
`GET /form/api/v1/analytics/dashboard`

**Impact:**
- None - working correctly

---

### Issue #11: Admin List Users Pagination (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` line 86

**Problem:**
None - backend supports pagination.

**Frontend:**
```dart
static const String adminListUsers = '/user/users';
// Usage: /user/users?page=1&page_size=20
```

**Backend (user.md, lines 104-107):**
Query parameters:
- `page` (int, default: 1)
- `page_size` (int, default: 20)

**Impact:**
- None - working correctly

---

### Issue #12: User Activity Endpoint Mismatch (MEDIUM PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` line 132-133

**Problem:**
Frontend expects full activity history, backend returns lock status only.

**Frontend Calls:**
```dart
static String adminGetUserActivity(String userId) =>
    '/user/users/$userId/activity';
// Calls: GET /form/api/v1/user/users/{userId}/activity
```

**Backend Has (user.md, lines 312-335):**
```dart
GET /form/api/v1/user/security/lock-status/<user_id>
```

Returns:
```json
{
  "success": true,
  "data": {
    "is_locked": true,
    "lock_until": "2026-04-02T15:00:00Z",
    "failed_login_attempts": 5
  }
}
```

**Impact:**
- Frontend expects activity events list, backend returns lock status
- Need new backend endpoint or frontend adjustment

---

### Issue #13: Change Password Endpoint (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` line 80

**Problem:**
None - endpoint is aligned.

**Frontend:**
```dart
static const String changePassword = '/user/change-password';
// Body: { "current_password": string, "new_password": string }
```

**Backend (user.md, lines 69-75):**
```json
{
  "current_password": "old_secret",
  "new_password": "new_secret123"
}
```

Rate limited: 3 per hour

**Impact:**
- None - working correctly

---

### Issue #14: Lock/Unlock User Endpoints (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` lines 122-126

**Problem:**
None - endpoints are aligned.

**Frontend:**
```dart
static String adminLockUser(String userId) => '/user/users/$userId/lock';
static String adminUnlockUser(String userId) => '/user/users/$userId/unlock';
```

**Backend (user.md, lines 268-309):**
- `POST /form/api/v1/user/users/<user_id>/lock`
- `POST /form/api/v1/user/users/<user_id>/unlock`

**Impact:**
- None - working correctly

---

### Issue #15: Form Submission Data Structure (MEDIUM PRIORITY)

**Location:**
- Frontend: Response submission in repository

**Problem:**
Frontend may send field IDs as keys, backend expects variable names.

**Frontend Sends:**
```json
{
  "data": {
    "field_123": "John Doe",
    "field_456": "25"
  }
}
```

**Backend Expects (forms-responses.md, lines 31-43):**
> The `data` field is a free-form dict mapping **question variable names** to their values.

```json
{
  "data": {
    "patient_name": "John Doe",
    "age": 35
  }
}
```

**Impact:**
- Responses may not map correctly to questions
- Need to use variableName (not field ID) when submitting

---

### Issue #16: Form Publish Response (LOW PRIORITY)

**Location:**
- Frontend: `lib/features/form_builder/data/repositories/form_builder_repository_impl.dart` line 144

**Problem:**
None - 202 response with task_id is handled correctly.

**Backend Returns (forms.md, lines 207-214):**
```json
{
  "success": true,
  "data": { "task_id": "celery-task-uuid" },
  "message": "Form publishing initiated in background"
}
```

**Impact:**
- None - working correctly

---

### Issue #17: Refresh Token Request (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` line 54

**Problem:**
Frontend sends refresh_token in body, backend also accepts Bearer header.

**Frontend Sends:**
```json
{ "refresh_token": "eyJ..." }
```

**Backend Accepts (auth.md, lines 161-163):**
> Token via `Authorization: Bearer <refresh_token>` header or refresh cookie.

**Impact:**
- Works but could use Bearer header for better security

---

### Issue #18: Logout Endpoint (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` line 59

**Problem:**
None - endpoint is aligned.

**Frontend:**
```dart
static const String logout = '/auth/logout';
```

**Backend (auth.md, lines 191-214):**
- Revokes JWT by adding JTI to Redis blocklist
- Clears HttpOnly cookies
- Requires valid access token

**Impact:**
- None - working correctly

---

### Issue #19: Revoke All Sessions (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` line 36

**Problem:**
None - endpoint is aligned.

**Frontend:**
```dart
static const String revokeAll = '/auth/revoke-all';
```

**Backend (auth.md, lines 218-241):**
> Revoke all active JWT sessions for the authenticated user.

**Impact:**
- None - working correctly

---

### Issue #20: Request Password Reset (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` line 64

**Problem:**
None - endpoint is aligned.

**Frontend:**
```dart
static const String requestPasswordReset = '/auth/request-password-reset';
```

**Backend:**
Password reset flow exists

**Impact:**
- None - working correctly

---

### Issue #21: Form Template List (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` line 240

**Problem:**
None - endpoint is aligned.

**Frontend:**
```dart
static const String listFormTemplates = '/forms/templates';
```

**Backend (forms.md, lines 248-263):**
- Lists forms where `is_template = True`
- Filters by user's forms

**Impact:**
- None - working correctly

---

### Issue #22: Section Management (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` lines 249-256

**Problem:**
None - endpoints are aligned.

**Frontend:**
```dart
static String listSections(String formId) => '/forms/$formId/sections';
static String createSection(String formId) => '/forms/$formId/sections';
static String updateSection(String formId, String sectionId) => '/forms/$formId/sections/$sectionId';
static String deleteSection(String formId, String sectionId) => '/forms/$formId/sections/$sectionId';
static String reorderSections(String formId) => '/forms/$formId/sections/reorder';
```

**Backend (forms.md, lines 314-362):**
- Full CRUD for sections
- Reorder endpoint

**Impact:**
- None - working correctly

---

### Issue #23: Form Translations (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` lines 460-471

**Problem:**
None - endpoints are aligned.

**Frontend:**
```dart
static String getFormTranslations({String? formId, String? language})
static const String saveFormTranslations = '/forms/translations';
```

**Backend (forms.md, lines 365-391):**
- GET/PUT translations per language
- Stores in `form.translations[lang_code]`

**Impact:**
- None - working correctly

---

### Issue #24: Translation Jobs (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` lines 477-501

**Problem:**
None - endpoints are aligned.

**Frontend:**
```dart
static const String startTranslationJob = '/forms/translations/jobs';
static String getTranslationJob(String jobId) => '/forms/translations/jobs/$jobId';
```

**Backend (blueprints/forms-translation.md):**
- Async translation using Python `threading.Thread`
- Job status tracking

**Impact:**
- None - working correctly

---

### Issue #25: AI Generate Form (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` line 527

**Problem:**
None - endpoint is aligned.

**Frontend:**
```dart
static const String generateFormAI = '/ai/generate';
```

**Backend (blueprints/ai.md):**
- Uses Ollama (local LLM)
- Generates form structure from prompt

**Impact:**
- None - working correctly

---

### Issue #26: AI Field Suggestions (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` line 531

**Problem:**
None - endpoint is aligned.

**Frontend:**
```dart
static const String getFieldSuggestions = '/ai/suggestions';
```

**Backend:**
AI-powered field suggestions

**Impact:**
- None - working correctly

---

### Issue #27: NLP/Semantic Search (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` lines 542-550

**Problem:**
None - endpoints are aligned.

**Frontend:**
```dart
static String nlpSearch(String formId) => '/ai/forms/$formId/nlp-search';
static String semanticSearch(String formId) => '/ai/forms/$formId/semantic-search';
```

**Backend (blueprints/ai.md):**
- Uses Elasticsearch + Ollama embeddings
- NLP semantic search with keyword fallback

**Impact:**
- None - working correctly

---

### Issue #28: Form Analytics (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` line 603

**Problem:**
None - endpoint is aligned.

**Frontend:**
```dart
static String getAnalytics(String formId) => '/forms/$formId/analytics';
```

**Backend (blueprints/analytics.md):**
- Form response analytics
- Requires admin/superadmin/manager role

**Impact:**
- None - working correctly

---

### Issue #29: Export Responses (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` lines 395-396

**Problem:**
None - endpoint is aligned.

**Frontend:**
```dart
static String exportResponses(String formId, {String format = 'csv'}) =>
    '/forms/$formId/export/$format';
```

**Backend (blueprints/forms-export.md):**
- CSV and JSON export
- Uses `resolved_snapshot` from FormVersion

**Impact:**
- None - working correctly

---

### Issue #30: Bulk Export (LOW PRIORITY)

**Location:**
- Frontend: `lib/core/network/api_endpoints.dart` lines 402-411

**Problem:**
None - async pattern is handled correctly.

**Frontend:**
```dart
static const String bulkExport = '/forms/export/bulk';
static String bulkExportStatus(String jobId) => '/forms/export/bulk/$jobId';
```

**Backend (forms.md, lines 285-291):**
- Returns 202 with `{ task_id }`
- Uses Celery worker
- No dedicated task-status poll endpoint (noted as gap)

**Impact:**
- None - working correctly

---

## Recommendations

### High Priority Fixes (Must Fix)

1. **Fix tenant_id → organization_id** (Issue #1)
   - Update `User` entity: change `tenantId` to `organizationId` with `@JsonKey(name: 'organization_id')`
   - Or add JSON mapping layer

2. **Fix register payload** (Issue #4)
   - Map `userType` to `roles` array (e.g., `userType: "admin"` → `roles: ["admin"]`)
   - Convert `employeeId` to `employee_id`
   - Add default `roles: ["user"]`
   - Backend provides `organization_id`, frontend shouldn't send it

3. **Fix FormResponse parsing** (Issue #5)
   - Add `@JsonKey(name: 'form')` to `formId` field
   - Add `@JsonKey(name: 'data')` to `answers` field  
   - Add missing fields: `submittedBy`, `organizationId`, `ipAddress`, `userAgent`

### Medium Priority Fixes (Should Fix)

4. **Fix role handling** (Issue #6)
   - Align `isAdmin` computation with backend's `is_admin` field
   - Remove `userType` dependency from admin check

5. **Add X-Organization-ID header** (from overview.md section 6)
   - Backend requires `X-Organization-ID` header for tenant isolation
   - Add to all API client requests after login

6. **Fix user activity endpoint** (Issue #12)
   - Either create backend endpoint for activity or adjust frontend to use lock-status

### Low Priority (Nice to Have)

7. **Use Bearer header for refresh token** (Issue #17)
8. **Use variable names for form submission** (Issue #15)