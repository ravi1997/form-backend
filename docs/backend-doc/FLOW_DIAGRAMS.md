# API Flow Diagrams — RIDP Form Platform

This document provides detailed flow diagrams for common API usage scenarios, showing which endpoints to call in sequence.

---

## Table of Contents

1. [Authentication Flow](#1-authentication-flow)
2. [User Registration and Onboarding](#2-user-registration-and-onboarding)
3. [Form Creation and Publishing](#3-form-creation-and-publishing)
4. [Form Submission Flow](#4-form-submission-flow)
5. [Form Response Management](#5-form-response-management)
6. [Dashboard Widget Setup](#6-dashboard-widget-setup)
7. [Export Data Flow](#7-export-data-flow)
8. [Form Translation Flow](#8-form-translation-flow)
9. [Anomaly Detection Flow](#9-anomaly-detection-flow)
10. [Bulk Export Flow](#10-bulk-export-flow)
11. [Form Clone Flow](#11-form-clone-flow)
12. [Form Access Control Flow](#12-form-access-control-flow)

---

## 1. Authentication Flow

### 1.1 Password-Based Login

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant Redis as Redis (Session DB)
    participant DB as MongoDB

    Client->>API: POST /form/api/v1/auth/login<br/>{email, password}
    activate #API
    API->>DB: Find user by email/username
    DB-->>API: User document
    API->>API: Verify password hash
    alt Password Valid
        API->>API: Generate JWT access & refresh tokens
        API->>Redis: Store refresh token JTI in blocklist (for logout)
        API-->>Client: 200 OK<br/>{access_token, refresh_token, user}
        Note over Client: Server sets HttpOnly cookies:<br/>access_token, refresh_token
    else Password Invalid
        API-->>Client: 401 Unauthorized
        Note over API: Log failed attempt
        DB->>DB: Increment failed_login_attempts
    end
    deactivate #API
```

### 1.2 OTP-Based Login

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant SMS as SMS Service
    participant Redis as Redis (Session DB)
    participant DB as MongoDB

    Client->>API: POST /form/api/v1/auth/request-otp<br/>{mobile: "9876543210"}
    activate #API
    API->>DB: Find user by mobile
    DB-->>API: User document
    API->>API: Generate 6-digit OTP
    API->>Redis: Store OTP with 5-min TTL
    API->>SMS: Send OTP to mobile
    API-->>Client: 200 OK<br/>{message: "OTP sent successfully"}
    deactivate #API

    Note over Client: User receives SMS with OTP

    Client->>API: POST /form/api/v1/auth/login<br/>{mobile, otp: "123456"}
    activate #API
    API->>Redis: Retrieve OTP
    alt OTP Valid & Not Expired
        API->>API: Delete OTP from Redis
        API->>API: Generate JWT access & refresh tokens
        API->>Redis: Store refresh token JTI
        API-->>Client: 200 OK<br/>{access_token, refresh_token, user}
    else OTP Invalid
        API-->>Client: 401 Unauthorized<br/>{message: "Invalid OTP"}
    end
    deactivate #API
```

### 1.3 Token Refresh

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant Redis as Redis (Session DB)
    participant DB as MongoDB

    Note over Client: Access token expired (401 response)

    Client->>API: POST /form/api/v1/auth/refresh<br/>Authorization: Bearer <refresh_token>
    activate #API
    API->>API: Verify refresh token signature
    API->>Redis: Check if JTI is blocklisted
    alt Token Valid & Not Revoked
        API->>DB: Find user by token identity
        DB-->>API: User document
        API->>API: Generate NEW access & refresh tokens
        API->>Redis: Invalidate old refresh JTI
        API->>Redis: Store new refresh JTI
        API-->>Client: 200 OK<br/>{access_token, refresh_token}
    else Token Invalid or Revoked
        API-->>Client: 401 Unauthorized
    end
    deactivate #API
```

### 1.4 Logout

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant Redis as Redis (Session DB)

    Client->>API: POST /form/api/v1/auth/logout<br/>Authorization: Bearer <access_token>
    activate #API
    API->>API: Extract JTI from access token
    API->>Redis: Add JTI to blocklist
    API-->>Client: 200 OK<br/>{message: "Successfully logged out"}
    Note over Client: Server clears HttpOnly cookies
    deactivate #API
```

---

## 2. User Registration and Onboarding

### 2.1 New User Registration

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant DB as MongoDB

    Client->>API: POST /form/api/v1/auth/register<br/>{email, username, password, mobile}
    activate #API
    API->>API: Validate input (Pydantic schema)
    API->>DB: Check if email/username already exists
    alt User Exists
        API-->>Client: 400 Bad Request<br/>{message: "User already exists"}
    else User Does Not Exist
        API->>DB: Create new User document
        Note over DB: - Hash password with bcrypt<br/>- Set roles = ["user"]<br/>- Set is_active = True
        API->>DB: Save user
        API-->>Client: 201 Created<br/>{user: {...}, message: "User registered successfully"}
    end
    deactivate #API
```

### 2.2 Profile Fetch (After Login)

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant DB as MongoDB

    Client->>API: GET /form/api/v1/user/profile<br/>Authorization: Bearer <access_token>
    activate #API
    API->>API: Verify JWT token
    API->>API: Extract user identity from token
    API->>DB: Get User by ID
    DB-->>API: User document
    API->>API: Serialize with UserOut schema
    API-->>Client: 200 OK<br/>{user: {...}}
    deactivate #API
```

---

## 3. Form Creation and Publishing

### 3.1 Create New Form

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant DB as MongoDB

    Client->>API: POST /form/api/v1/forms/<br/>{title, description, ...}
    activate #API
    API->>API: Verify JWT token
    API->>API: Extract org_id from user context
    API->>API: Validate with FormCreateSchema
    API->>DB: Check slug uniqueness (if provided)
    API->>API: Generate slug from title (if not provided)
    API->>DB: Create Form document
    Note over DB: Set created_by = current_user.id<br/>Set organization_id = user.org_id<br/>Set editors = [user.id]<br/>Set status = "draft"
    API->>DB: Save form
    API-->>Client: 201 Created<br/>{form_id: "uuid", message: "Form created"}
    deactivate #API
```

### 3.2 Add Sections to Form

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant DB as MongoDB

    Client->>API: POST /form/api/v1/forms/<form_id>/sections<br/>{title, order, questions: [...]}
    activate #API
    API->>API: Verify JWT + permission
    API->>DB: Get Form by ID (scoped to org_id)
    API->>DB: Create Section document
    API->>DB: Add section to form.sections array
    API->>DB: Save form
    API-->>Client: 200 OK<br/>{section_id: "uuid", message: "Section added"}
    deactivate #API
```

### 3.3 Publish Form (Async)

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant Celery as Celery Worker
    participant DB as MongoDB

    Client->>API: POST /form/api/v1/forms/<form_id>/publish<br/>{major: false, minor: true}
    activate #API
    API->>API: Verify JWT + permission (edit)
    API->>API: Validate form has sections
    API->>Celery: async_publish_form.delay(form_id, org_id, major, minor)
    API-->>Client: 202 Accepted<br/>{task_id: "celery-task-uuid", message: "Form publishing initiated in background"}
    deactivate #API

    Note over Celery: Background task execution
    activate #Celery
    Celery->>DB: Get Form by ID
    Celery->>DB: Get current version or create new
    Celery->>DB: Create FormVersion with resolved_snapshot
    Note over DB: - Denormalize entire form structure<br/>- Increment version number<br/>- Store in resolved_snapshot
    Celery->>DB: Update Form.active_version_id
    Celery->>DB: Set Form.status = "published"
    Celery->>DB: Save all changes
    Celery-->>DB: Task complete
    deactivate #Celery
```

### 3.4 Check Publishing Status (Workaround - No Official Endpoint)

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant DB as MongoDB

    Note over Client: Since no task status endpoint exists,<br/>poll form status to infer completion

    loop Every 5 seconds
        Client->>API: GET /form/api/v1/forms/<form_id>
        activate #API
        API->>DB: Get Form by ID
        DB-->>API: Form document
        API-->>Client: 200 OK<br/>{form: {status: "...", active_version_id: "..."}}
        deactivate #API

        alt status == "published" and active_version_id exists
            Note over Client: Publishing complete
            Break
        else status == "draft"
            Note over Client: Still in progress
        end
    end
```

---

## 4. Form Submission Flow

### 4.1 Authenticated Form Submission

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant DB as MongoDB

    Client->>API: POST /form/api/v1/forms/<form_id>/responses<br/>Authorization: Bearer <token><br/>{data: {field1: "value1", ...}}
    activate #API
    API->>API: Verify JWT token
    API->>API: Extract org_id from user context
    API->>DB: Get Form by ID (scoped to org_id)
    API->>API: Check user permission (submit)
    API->>API: Validate form not expired (expires_at)
    API->>API: Validate form published (publish_at in past)
    API->>API: Validate input with FormResponseCreateSchema
    API->>DB: Create FormResponse document
    Note over DB: Set submitted_by = user.id<br/>Set form = form.id<br/>Set organization_id = user.org_id<br/>Set status = "submitted"<br/>Store data field
    API->>DB: Save response
    API-->>Client: 201 Created<br/>{response_id: "uuid", message: "Response submitted successfully"}
    deactivate #API
```

### 4.2 Anonymous/Public Form Submission

```mermaid
sequenceDiagram
    participant Client as Public Client
    participant API as API Server
    participant DB as MongoDB

    Note over Client: No authentication required

    Client->>API: POST /form/api/v1/forms/<form_id>/public-submit<br/>{data: {field1: "value1", ...}}
    activate #API
    API->>DB: Get Form by ID (no org scope)
    API->>API: Validate form.is_public == true
    API->>API: Validate form.status == "published"
    API->>API: Validate form not expired
    API->>API: Validate form available (publish_at in past)
    API->>DB: Create FormResponse document
    Note over DB: Set submitted_by = "anonymous"<br/>Set organization_id = form.organization_id<br/>Set status = "submitted"<br/>Store data field
    API->>DB: Save response
    API-->>Client: 201 Created<br/>{response_id: "uuid", message: "Response submitted successfully"}
    deactivate #API
```

---

## 5. Form Response Management

### 5.1 List Responses

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant DB as MongoDB

    Client->>API: GET /form/api/v1/forms/<form_id>/responses?page=1&page_size=20
    activate #API
    API->>API: Verify JWT token
    API->>API: Extract org_id from user context
    API->>DB: Get Form by ID (scoped to org_id)
    API->>API: Check user permission (view_responses)
    API->>DB: Query FormResponse with pagination
    Note over DB: WHERE form = form_id<br/>AND organization_id = user.org_id<br/>AND is_deleted = false<br/>ORDER BY submitted_at DESC<br/>LIMIT 20 OFFSET 0
    DB-->>API: Response documents
    API->>API: Serialize responses
    API-->>Client: 200 OK<br/>{items: [...], total: 100, page: 1, ...}
    deactivate #API
```

### 5.2 Get Response Count

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant DB as MongoDB

    Client->>API: GET /form/api/v1/forms/<form_id>/responses/count
    activate #API
    API->>API: Verify JWT token
    API->>API: Extract org_id from user context
    API->>DB: Get Form by ID (scoped to org_id)
    API->>DB: Count FormResponse
    Note over DB: WHERE form = form_id<br/>AND organization_id = user.org_id<br/>AND is_deleted = false
    DB-->>API: Count value
    API-->>Client: 200 OK<br/>{count: 42}
    deactivate #API
```

### 5.3 Delete All Responses (Admin Only, Hard Delete)

```mermaid
sequenceDiagram
    participant Client as Admin Client
    participant API as API Server
    participant DB as MongoDB

    Note over Client: WARNING: This is IRREVERSIBLE

    Client->>API: DELETE /form/api/v1/forms/<form_id>/responses<br/>Authorization: Bearer <admin_token>
    activate #API
    API->>API: Verify JWT + role (admin/superadmin)
    API->>DB: Get Form by ID (scoped to org_id)
    API->>DB: Delete ALL FormResponse documents
    Note over DB: WARNING: Hard delete - no soft delete<br/>DELETE FROM FormResponse<br/>WHERE form = form_id
    DB-->>API: Delete count
    API-->>Client: 200 OK<br/>{message: "Deleted X responses"}
    deactivate #API
```

---

## 6. Dashboard Widget Setup

### 6.1 Create Dashboard with Widgets

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant DB as MongoDB

    Client->>API: POST /form/api/v1/dashboards/<br/>{title, slug, widgets: [...]}
    activate #API
    API->>API: Verify JWT token
    API->>API: Extract org_id from user context
    API->>API: Check permission (dashboard.create)
    API->>API: Validate with DashboardCreateSchema
    API->>DB: Create Dashboard document
    Note over DB: Set created_by = user.id<br/>Set organization_id = user.org_id
    API->>DB: Save dashboard
    API-->>Client: 201 Created<br/>{dashboard_id: "uuid", ...}
    deactivate #API
```

### 6.2 Get Dashboard with Resolved Widget Data

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant DB as MongoDB

    Client->>API: GET /form/api/v1/dashboards/<slug_or_id>
    activate #API
    API->>API: Verify JWT token
    API->>API: Extract org_id from user context
    API->>DB: Get Dashboard by slug or ID (scoped to org_id)
    DB-->>API: Dashboard document with widgets
    API->>API: For each widget, resolve data
    loop For each widget
        API->>DB: Execute aggregation pipeline
        Note over DB: MATCH form = widget.form_id<br/>AND organization_id = user.org_id<br/>AND is_deleted = false<br/>[GROUP BY field][AGGREGATE]
        DB-->>API: Aggregated data
    end
    API-->>Client: 200 OK<br/>{dashboard: {...}, widgets: [{...data: ...}, ...]}
    deactivate #API
```

---

## 7. Export Data Flow

### 7.1 Export Responses to CSV (Streaming)

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant DB as MongoDB

    Client->>API: GET /form/api/v1/forms/<form_id>/export/csv
    activate #API
    API->>API: Verify JWT token
    API->>API: Extract org_id from user context
    API->>DB: Get Form by ID (scoped to org_id)
    API->>API: Check permission (view_responses)
    API->>DB: Get FormVersion by active_version_id
    DB-->>API: FormVersion with resolved_snapshot
    API->>API: Generate CSV headers from snapshot
    API->>API: Stream responses
    loop For each response (batch of 100)
        API->>DB: Query FormResponse (paginated)
        DB-->>API: Response documents
        API->>API: Map response.data to CSV columns
        API-->>Client: CSV row (stream)
    end
    deactivate #API
    Note over Client: Client receives streaming CSV file<br/>Content-Type: text/csv<br/>Content-Disposition: attachment;filename=...
```

### 7.2 Export Responses to JSON (Streaming)

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant DB as MongoDB

    Client->>API: GET /form/api/v1/forms/<form_id>/export/json
    activate #API
    API->>API: Verify JWT token
    API->>API: Extract org_id from user context
    API->>DB: Get Form by ID (scoped to org_id)
    API->>API: Check permission (view_responses)
    API->>API: Get FormVersion by active_version_id
    DB-->>API: FormVersion with resolved_snapshot
    API-->>Client: 200 OK<br/>Content-Type: application/json<br/>{form_metadata: {...}, responses: [...]}
    deactivate #API
```

---

## 8. Form Translation Flow

### 8.1 Start Translation Job (Threading-Based)

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant Thread as Background Thread
    participant Ollama as Ollama AI Service
    participant DB as MongoDB

    Client->>API: POST /form/api/v1/forms/translations/jobs<br/>{form_id, source_language, target_languages}
    activate #API
    API->>API: Verify JWT token
    API->>API: Extract org_id from user context
    API->>DB: Get Form by ID (scoped to org_id)
    API->>DB: Check permission (edit)
    API->>DB: Create TranslationJob document
    Note over DB: Set status = "pending"<br/>Set created_by = user.id
    API->>DB: Save job
    API->>Thread: Start background thread (process_translation_job)
    API-->>Client: 202 Accepted<br/>{job_id: "uuid", message: "Translation job started"}
    deactivate #API

    Note over Thread: Background execution (NOT Celery)
    activate #Thread
    Thread->>DB: Update job status = "inProgress"
    loop For each target language
        Thread->>Ollama: POST /api/generate<br/>{model: "llama3.2", prompt: "..."}
        Ollama-->>Thread: Translated text
        Thread->>DB: Update FormVersion translations[lang_code]
    end
    Thread->>DB: Update job status = "completed"
    Thread-->>DB: Job complete
    deactivate #Thread

    Note over Client: WARNING: Thread does NOT survive worker restart
```

### 8.2 Check Translation Job Status

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant DB as MongoDB

    Client->>API: GET /form/api/v1/forms/translations/jobs/<job_id>
    activate #API
    API->>API: Verify JWT token
    API->>DB: Get TranslationJob by ID
    DB-->>API: Job document
    API-->>Client: 200 OK<br/>{status: "completed"|"inProgress"|"failed", ...}
    deactivate #API

    alt status == "completed"
        Client->>API: GET /form/api/v1/forms/translations/jobs/<job_id>/content
        activate #API
        API->>DB: Get translated content
        API-->>Client: 200 OK<br/>{translations: {...}}
        deactivate #API
    end
```

---

## 9. Anomaly Detection Flow

### 9.1 Run Anomaly Detection on Form Responses

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant Service as AnomalyDetectionService
    participant DB as MongoDB

    Client->>API: POST /form/api/v1/forms/<form_id>/detect-anomalies<br/>{scan_type: "full", sensitivity: "medium"}
    activate #API
    API->>API: Verify JWT token
    API->>API: Extract org_id from user context
    API->>DB: Get Form by ID (scoped to org_id)
    API->>DB: Query FormResponse documents
    alt scan_type == "full"
        DB-->>API: All responses for form
    else scan_type == "incremental"
        DB-->>API: Recent 100 responses
    end
    API->>Service: Run detection (spam, outlier, impossible_value)
    activate #Service
    Service->>Service: Calculate baseline statistics
    Service->>Service: Apply thresholds (z-score, IQR, etc.)
    Service->>Service: Flag anomalies
    Service-->>API: {anomalies_detected: 12, anomalies: [...]}
    deactivate #Service
    API-->>Client: 200 OK<br/>{form_id, anomalies_detected, baseline: {...}, anomalies: [...]}
    deactivate #API
```

### 9.2 Get Anomaly Details for Specific Response

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant Service as AnomalyDetectionService
    participant DB as MongoDB

    Client->>API: GET /form/api/v1/forms/<form_id>/anomalies/<response_id>
    activate #API
    API->>API: Verify JWT token
    API->>DB: Get FormResponse by ID
    DB-->>API: Response document
    API->>Service: Detect spam for single response
    activate #Service
    Service->>Service: Analyze response text patterns
    Service->>Service: Check against spam indicators
    Service-->>API: {is_spam: true, spam_score: 85, indicators: [...]}
    deactivate #Service
    API-->>Client: 200 OK<br/>{response_id, anomaly_flags: {...}, suggested_actions: [...]}
    deactivate #API
```

---

## 10. Bulk Export Flow

### 10.1 Start Bulk Export Job

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant Celery as Celery Worker
    participant DB as MongoDB

    Client->>API: POST /form/api/v1/forms/export/bulk<br/>{form_ids: ["uuid1", "uuid2"]}
    activate #API
    API->>API: Verify JWT token
    API->>API: Extract org_id from user context
    API->>DB: Create BulkExport document
    Note over DB: Set status = "pending"<br/>Set form_ids = [...]<br/>Set organization_id = user.org_id
    API->>DB: Save job
    API->>Celery: async_bulk_export.delay(job_id, org_id)
    API-->>Client: 202 Accepted<br/>{job_id: "uuid", status: "pending"}
    deactivate #API

    Note over Celery: Background task execution
    activate #Celery
    Celery->>DB: Get BulkExport by ID
    Celery->>DB: Update status = "inProgress"
    loop For each form_id
        Celery->>DB: Get Form by ID
        Celery->>DB: Get FormVersion by active_version_id
        Celery->>DB: Query all FormResponse for form
        Celery->>Celery: Generate CSV/JSON for form
    end
    Celery->>Celery: Create ZIP file with all exports
    Celery->>DB: Store ZIP file path (or generate download URL)
    Celery->>DB: Update status = "completed"
    Celery-->>DB: Task complete
    deactivate #Celery
```

### 10.2 Check Bulk Export Status

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant DB as MongoDB

    loop Poll every 5 seconds
        Client->>API: GET /form/api/v1/forms/export/bulk/<job_id>
        activate #API
        API->>API: Verify JWT token
        API->>DB: Get BulkExport by ID
        DB-->>API: Job document
        API-->>Client: 200 OK<br/>{status: "pending"|"inProgress"|"completed"|"failed"}
        deactivate #API

        alt status == "completed"
            Break
        end
    end

    Client->>API: GET /form/api/v1/forms/export/bulk/<job_id>/download
    activate #API
    API->>API: Verify JWT token
    API->>DB: Get BulkExport by ID
    API->>DB: Retrieve ZIP file
    API-->>Client: 200 OK<br/>Content-Type: application/zip<br/>{binary file data}
    deactivate #API
```

---

## 11. Form Clone Flow

### 11.1 Clone Form (Async)

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant Celery as Celery Worker
    participant DB as MongoDB

    Client->>API: POST /form/api/v1/forms/<form_id>/clone<br/>{title: "Copy of Form", slug: "form-copy"}
    activate #API
    API->>API: Verify JWT token
    API->>API: Extract org_id from user context
    API->>API: Check permission (view)
    API->>DB: Get original Form by ID (scoped to org_id)
    API->>Celery: async_clone_form.delay(form_id, user_id, org_id, new_title, new_slug)
    API-->>Client: 202 Accepted<br/>{task_id: "celery-task-uuid", message: "Form cloning initiated in background"}
    deactivate #API

    Note over Celery: Background task execution
    activate #Celery
    Celery->>DB: Get original Form by ID
    Celery->>DB: Verify organization_id matches (security check)
    Celery->>DB: Deep clone sections (recursive)
    Note over DB: For each section:<br/>  - Create new Section document<br/>  - Copy all fields<br/>  - Recursively clone sub-sections
    Celery->>DB: Create new Form document
    Note over DB: Set title = new_title<br/>Set slug = new_slug<br/>Set created_by = user_id<br/>Set organization_id = org_id<br/>Set sections = [new_sections]<br/>Set status = "draft"
    Celery->>DB: Save new form
    Celery-->>DB: Task complete
    deactivate #Celery
```

---

## 12. Form Access Control Flow

### 12.1 Grant Form Permissions

```mermaid
sequenceDiagram
    participant Client as Admin Client
    participant API as API Server
    participant DB as MongoDB

    Client->>API: POST /form/api/v1/forms/<form_id>/share<br/>{editors: ["user_id_1"], viewers: ["user_id_2"]}
    activate #API
    API->>API: Verify JWT + role (admin/superadmin)
    API->>API: Extract org_id from user context
    API->>DB: Get Form by ID (scoped to org_id)
    API->>API: Validate request data
    API->>DB: Update Form editors/viewers/submitters arrays
    Note over DB: editors = [..., "user_id_1"]<br/>viewers = [..., "user_id_2"]
    API->>DB: Save form
    API-->>Client: 200 OK<br/>{message: "Permissions updated"}
    deactivate #API
```

### 12.2 Check User Permissions for Form

```mermaid
sequenceDiagram
    participant Client as Client App
    participant API as API Server
    participant Helper as Permission Helper
    participant DB as MongoDB

    Client->>API: GET /form/api/v1/forms/<form_id>/access-control
    activate #API
    API->>API: Verify JWT token
    API->>API: Extract user context (id, roles, org_id)
    API->>DB: Get Form by ID (scoped to org_id)
    DB-->>API: Form document
    API->>Helper: has_form_permission(user, form, action)
    activate #Helper
    loop For each action (view, edit, submit, view_responses, ...)
        Helper->>Helper: Check user roles
        Helper->>Helper: Check if user is superadmin
        Helper->>Helper: Check if user.id in form.editors
        Helper->>Helper: Check if user.id in form.viewers
        Helper->>Helper: Check if user.id in form.submitters
        Helper->>Helper: Check form.access_policy fields
        Helper-->>Helper: true or false
    end
    Helper-->>API: {view_form: true, submit_form: false, edit_design: true, ...}
    deactivate #Helper
    API-->>Client: 200 OK<br/>{form_id, permissions: {...}}
    deactivate #API
```

---

## Summary of Key Patterns

### Authentication Pattern

1. **Always include:** `Authorization: Bearer <token>` header OR use cookies
2. **After login:** Store access_token and refresh_token
3. **On 401:** Call `/auth/refresh` to get new tokens
4. **On logout:** Call `/auth/logout` to invalidate current session

### Form Operations Pattern

1. **Create:** `POST /forms` → Returns `{form_id}`
2. **Add sections:** `POST /forms/<form_id>/sections`
3. **Publish:** `POST /forms/<form_id>/publish` → Returns `{task_id}` (202)
4. **Check status:** Poll `GET /forms/<form_id>` to infer completion
5. **Submit response:** `POST /forms/<form_id>/responses` (authenticated) or `/public-submit` (anonymous)

### Dashboard Pattern

1. **Create:** `POST /dashboards` with widgets array
2. **View:** `GET /dashboards/<slug>` → Returns widgets with resolved data
3. **Widget data:** Automatically resolved via MongoDB aggregation

### Export Pattern

1. **Single form:** `GET /forms/<form_id>/export/csv` or `/export/json` → Streaming response
2. **Bulk:** `POST /forms/export/bulk` → Returns `{job_id}` (202)
3. **Check status:** `GET /forms/export/bulk/<job_id>`
4. **Download:** `GET /forms/export/bulk/<job_id>/download` → ZIP file

### Async Operations Pattern

1. **Start:** POST endpoint → Returns `{task_id}` with 202 Accepted
2. **Poll:** Since no task status endpoint exists, poll the resource itself
3. **Completion:** Resource status changes (e.g., form.status = "published")

### Error Handling Pattern

- **400:** Validation error
- **401:** Missing or invalid token → Try refresh
- **403:** Insufficient permissions → Check user roles and form ACLs
- **404:** Resource not found
- **429:** Rate limit exceeded → Implement exponential backoff
- **500:** Server error → Check logs and retry

---

**Note:** All endpoints are prefixed with `/form` due to gateway routing. Example:
- Full URL: `https://api.example.com/form/api/v1/forms/`
- Base path: `/form/api/v1/`

---

**Document Version:** 1.1
**Last Updated:** 2026-04-06
**Based on Codebase Version:** Current development branch
**Changes:** Fixed internal links (replaced & with and in headings)
