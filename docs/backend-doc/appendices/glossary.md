# Glossary

## A

**AccessPolicy**
An embedded MongoDB document within a `Form` that controls fine-grained permissions for viewing, editing, submitting, and managing a specific form. Distinct from global RBAC roles. Set via `POST/PUT /forms/<id>/access-policy`.

**active_version_id**
A field on the `Form` document that points to the most recently published `FormVersion`. Used by exports and form GET endpoints to resolve the current snapshot.

**anomaly detection**
A set of routes in `routes/v1/form/anomaly.py` that analyze FormResponse data for patterns like spam, outliers, impossible values, and duplicates.

**async task**
An operation offloaded to a Celery worker. The route returns a 202 response with a `task_id` immediately. The actual operation completes asynchronously. Examples: publish, clone, bulk export.

**audit_logger**
One of five named loggers. Used for compliance-relevant state changes: logins, logouts, creates, updates, deletes. All audit log lines are prefixed with `AUDIT:` by convention.

## B

**BulkExport**
A MongoDB document model in `models/Response.py` that tracks asynchronous multi-form export jobs. Stores job status, form IDs, and the binary ZIP file content when complete.

**base_prefix**
The `/form` string prepended to all route URLs. Defined in `routes/__init__.py` as `base_prefix = "/form"`. Exists for API gateway routing namespace separation.

**blocklist**
A Redis set storing JTIs (JWT ID claims) of revoked tokens. Checked on every authenticated request by Flask-JWT-Extended.

**blueprint**
A Flask `Blueprint` object that groups related routes. Registered in `routes/__init__.py` with a URL prefix. Each blueprint corresponds to a logical feature area.

## C

**Celery**
The distributed task queue used for async operations. Workers run in separate Docker containers. Multiple named queues: `celery`, `sms`, `mail`, `ehospital`, `request`, `employee`.

**created_by**
A field on `Form` storing the user ID of the form's creator. The creator has all form permissions by default.

**CSRF token**
Cross-Site Request Forgery protection token. Required when using cookie-based JWT auth. Sent in `X-CSRF-TOKEN-ACCESS` (for access token) or `X-CSRF-TOKEN-REFRESH` (for refresh).

## D

**Dashboard**
A named collection of widgets. Identified by a slug for reads, an ID for updates. Widget data is resolved live on each GET request via MongoDB aggregation.

**default_language**
A field on `Form` specifying which language the original form content is written in. Used as the source language for AI translation jobs.

## E

**editors**
A list of user IDs on a `Form` document. Users in this list have edit-level permissions for the form (edit design, view responses, etc.).

**employee_id**
One of the identifier fields on a `User` document. Can be used as the login identifier in password-based login.

**expires_at**
A datetime field on `Form`. When set, submissions are rejected after this timestamp. Does not change form status — the form remains `published` but new submissions are blocked.

## F

**FormResponse**
A MongoDB document storing a single form submission. Key fields: `form`, `organization_id`, `data`, `submitted_by`, `submitted_at`, `status`, `ip_address`, `user_agent`.

**FormSerializer**
A utility class in `utils/response_helper.py` that sanitizes form documents before returning them in API responses (e.g., converts ObjectId to string, removes internal fields).

**FormVersion**
An immutable MongoDB document created when a form is published. Contains `version_string`, `resolved_snapshot`, and `translations`. Never modified after creation.

**fine-grained permission**
A per-form permission evaluated by `has_form_permission()`. Distinct from global RBAC roles. Checked against `form.editors`, `form.viewers`, `form.submitters`, `form.created_by`, and `form.access_policy`.

## G

**g (Flask g)**
Flask's request-local storage object. Used to store `request_id` (set by request_id middleware) and `organization_id` (set by tenant_db middleware) for the duration of each request.

## H

**has_form_permission(user, form, action)**
Helper function in `routes/v1/form/helper.py`. Evaluates whether a user has a specific action permission on a given form. Used throughout form route handlers.

**hard delete**
Permanent removal from MongoDB. Distinct from soft delete. Used in: `DELETE /forms/<id>/responses` (deletes all FormResponse documents). Cannot be undone.

**HttpOnly cookie**
A cookie flag that prevents JavaScript access. Used for JWT tokens to mitigate XSS. Both access and refresh tokens are stored as HttpOnly cookies after login.

## I

**is_deleted**
Soft-delete flag on all MongoEngine documents. When `True`, the document is excluded from standard queries by `TenantIsolatedSoftDeleteQuerySet`.

**is_public**
A boolean field on `Form`. When `True`, the form allows anonymous submissions via `POST /forms/<id>/public-submit` without authentication.

**is_template**
A boolean field on `Form`. When `True`, the form is treated as a reusable template and appears in template listings.

## J

**JTI (JWT ID)**
A unique identifier embedded in each JWT. Used as the key when revoking tokens — the JTI is added to the Redis blocklist.

**jwt_required()**
Flask-JWT-Extended decorator. Validates the JWT from either the `Authorization` header or the `access_token` cookie.

## L

**library_bp**
The blueprint for custom field templates. Registered at two URL prefixes: `/custom-fields` and `/templates`.

**lock_account()**
A method on the `User` model that sets `is_locked = True` and `lock_until = future_datetime`. Called automatically after N failed login attempts, or manually by admins.

## M

**middleware**
Flask functions that execute for every request. Three middleware layers: `request_id.py`, `security_waf.py`, `tenant_db.py`. Applied in this order.

**MongoEngine**
The Python ODM (Object Document Mapper) used to interact with MongoDB. Provides document model definitions, queryset operations, and relationship references.

## N

**nlp_search_bp**
The NLP/semantic search blueprint. Registered at `/form/api/v1/ai/search`. Provides keyword and semantic (embedding-based) search over form responses.

**nomic-embed-text**
The Ollama embedding model used for semantic search. Generates vector embeddings from text for similarity comparison.

## O

**Ollama**
A local LLM inference server. Used for text generation (summarization, translation) and embeddings (semantic search). Runs as a Docker service. Default model: `llama3.2`.

**organization_id**
The primary multi-tenancy identifier. Present on all model documents. Extracted from JWT claims by `tenant_db.py` middleware and enforced in querysets.

## P

**Pydantic v2**
The Python data validation library used for all input schemas. All request bodies are validated by instantiating a Pydantic model before reaching service layer.

**publish_at**
A datetime field on `Form`. When set, the form is not available for submission until this timestamp is reached.

## R

**RBAC (Role-Based Access Control)**
The global permission model. Four roles: `user`, `manager`, `admin`, `superadmin`. Enforced by `@require_roles()` decorator.

**resolved_snapshot**
The `dict` field on `FormVersion` containing the complete denormalized form structure at the time of publishing. Used for exports. Immutable.

**require_roles(*roles)**
Decorator in `utils/security.py`. Wraps `@jwt_required()`. Checks that the user has at least one of the specified roles.

**require_permission(resource, action)**
Decorator in `utils/security_helpers.py`. Resource-level permission check at the route boundary.

## S

**Section**
A MongoEngine document grouping questions within a form. Forms can have multiple ordered sections. Each section has a title, description, order, and list of questions.

**SectionService**
Service in `services/section_service.py` handling section CRUD and reordering within forms.

**slug**
A URL-safe identifier for forms (e.g., `patient-intake-form`). Globally unique across all organizations. Auto-generated from title if not provided.

**soft delete**
Setting `is_deleted = True` on a document instead of removing it from MongoDB. Documents with `is_deleted = True` are excluded from all standard querysets by `TenantIsolatedSoftDeleteQuerySet`.

**submitters**
A list of user IDs on a `Form` document. Users in this list have permission to submit responses to the form.

**SummarizationService**
Service in `services/summarization_service.py`. Uses Ollama to generate text summaries from form response data.

## T

**task_id**
The Celery task ID returned in 202 responses for async operations (publish, clone, bulk export). Can be used with Celery's `AsyncResult` API to check task status (no public endpoint currently).

**TenantIsolatedSoftDeleteQuerySet**
A custom MongoEngine QuerySet class in `models/base.py`. Automatically appends `organization_id` and `is_deleted=False` filters to all queries.

**tenant_db.py**
Flask middleware that extracts `org_id` from JWT claims on every request and stores it in `g`. Required for `TenantIsolatedSoftDeleteQuerySet` to function.

**TranslationJob**
A MongoDB document tracking an AI batch translation operation. Includes status, progress, source/target languages, results per language, and error information.

## U

**UserOut**
Pydantic schema in `schemas/user.py` used for user objects in API responses. Excludes sensitive fields (password hash, internal flags).

## V

**variable_name**
A field on a form question that serves as the key in `FormResponse.data`. The CSV export uses `variable_name` to look up response values for each column.

**viewers**
A list of user IDs on a `Form` document. Users in this list have read-only (view) permission for the form.

## W

**WAF (Web Application Firewall)**
Custom middleware in `middleware/security_waf.py`. Inspects all incoming requests for OWASP Top-10 attack patterns and rejects malicious requests before they reach route handlers.

**widget**
A configurable data display component within a Dashboard. Types: `chart_bar`, `chart_pie`, `chart_line`, `counter`, `kpi`, `table`, `list_view`. Widget data is resolved via MongoDB aggregation on each Dashboard GET.

**workflow**
An `ApprovalWorkflow` document defining a sequence of approval steps triggered by form submission. Accessible via `/form/api/v1/workflows`. Linked to forms via `trigger_form_id`.
