# 🚀 API Reference Guide
> Comprehensive, industry-standard API documentation for the Forms Platform Backend.

<details><summary><strong>Authentication Guide</strong></summary>

Most endpoints under `/api/v1/` and `/form/api/v1/` require an `Authorization: Bearer <token>` header.
Endpoints are marked appropriately with 🔒 (Requires Auth) or 🔓 (Public).
</details>

---

## 📝 Form Responses & Meta
> Handles form data lifecycle, access control policies, and rich metadata operations.

### `GET`  `/form/api/v1/forms/<form_id>/access-control`
🔒 **Requires Authentication** | Module: `advanced_responses.get_form_access_control`

User access control for a forms.
Returns a detailed JSON report of the current user's permissions.

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `PUT`, `POST`  `/form/api/v1/forms/<form_id>/access-policy`
🔒 **Requires Authentication** | Module: `advanced_responses.update_access_policy`

Management route to update the Access Policy for a form.
Requires 'manage_access' permission.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "resource_type": "typing.Literal['form', 'project', 'submission', 'view']",
  "resource_id": "string",
  "access_level": "typing.Literal['private', 'group', 'organization', 'public']",
  "entries": [],
  "approval_workflow": "string",
  "is_active": false,
  "meta_data": "string",
  "tags": "string"
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/forms/<form_id>/fetch/same`
🔒 **Requires Authentication** | Module: `advanced_responses.fetch_same_form_data`

Fetch data from same form response where some question may have match for a value.

#### Query Parameters
| Parameter | Description |
|-----------|-------------|
| `question_id` | *Parameter* |
| `value` | *Parameter* |

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/forms/<form_id>/responses/meta`
🔒 **Requires Authentication** | Module: `advanced_responses.fetch_response_meta`

Fetching meta information about a form response like number of response etc.

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/forms/<form_id>/responses/questions`
🔒 **Requires Authentication** | Module: `advanced_responses.fetch_specific_questions`

Fetching particular questions responses from a form only.

#### Query Parameters
| Parameter | Description |
|-----------|-------------|
| `question_ids (comma separated)` | *Parameter* |

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/forms/fetch/external`
🔒 **Requires Authentication** | Module: `advanced_responses.fetch_external_form_data`

Fetch data from another form response where some question may have match for a value.

#### Query Parameters
| Parameter | Description |
|-----------|-------------|
| `form_id` | *Parameter* |
| `question_id` | *Parameter* |
| `value` | *Parameter* |

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/forms/micro-info`
🔒 **Requires Authentication** | Module: `advanced_responses.micro_info`

Route for micro informations (Placeholder).

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

## 🧠 AI Processing & Insights
> Core AI services for anomaly detection, cross-analysis, sentiment trends, and form processing.

### `POST`  `/form/api/v1/ai/<form_id>/anomalies`
🔒 **Requires Authentication** | Module: `ai.detect_form_anomalies`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/ai/<form_id>/anomaly-detect`
🔒 **Requires Authentication** | Module: `ai.detect_predictive_anomalies`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `DELETE`  `/form/api/v1/ai/<form_id>/cache`
🔒 **Requires Authentication** | Module: `ai.clear_form_cache`

Clear all cache for a specific form.

This endpoint clears all cached data for a form including:
- NLP search results
- Semantic search results
- Summarization results
- Popular queries
- Executive summaries

#### 📤 Output (Response)

```text
"form_id": "form-id",
    "keys_invalidated": 10,
    "cleared_at": "2026-02-04T10:00:00Z"
}
```

---

### `POST`  `/form/api/v1/ai/<form_id>/cache/invalidate`
🔒 **Requires Authentication** | Module: `ai.invalidate_form_cache`

Manual cache invalidation for a specific form.

Allows selective cache invalidation based on pattern:
- all: Invalidate all cache for the form
- nlp_search: Invalidate NLP search cache only
- summarization: Invalidate summarization cache only
- by_query: Invalidate cache for a specific query (requires 'query' parameter)

#### 📥 Input (Request Body)
Format: `application/json`

```text
"pattern": "all" | "nlp_search" | "summarization" | "by_query",
    "query": "search query text" (required for by_query pattern)
}
```

#### 📤 Output (Response)

```text
"form_id": "form-id",
    "pattern": "all",
    "keys_invalidated": 5,
    "invalidated_at": "2026-02-04T10:00:00Z"
}
```

---

### `POST`  `/form/api/v1/ai/<form_id>/export`
🔒 **Requires Authentication** | Module: `ai.export_form_ai_report`

Generate AI-powered export reports for form analytics.

Supports multiple export formats (PDF, Excel, CSV) with AI-generated insights.
Includes sentiment distribution, key insights, and charts data for visualization.

#### 📥 Input (Request Body)
Format: `application/json`

```text
"format": "pdf" | "excel" | "csv" | "json",
    "include_raw_data": true,
    "include_charts": true
}

Returns JSON data that can be converted to the requested format by the frontend.
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/ai/<form_id>/responses/<response_id>/analyze`
🔒 **Requires Authentication** | Module: `ai.analyze_response_ai`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/ai/<form_id>/responses/<response_id>/moderate`
🔒 **Requires Authentication** | Module: `ai.moderate_response_ai`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/ai/<form_id>/search`
🔒 **Requires Authentication** | Module: `ai.ai_powered_search`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/ai/<form_id>/security-scan`
🔒 **Requires Authentication** | Module: `ai.scan_form_security_ai`

Automated Security Scanning for Form Definitions.
Analyzes questions, settings, and permissions for vulnerabilities.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/ai/<form_id>/sentiment`
🔒 **Requires Authentication** | Module: `ai.get_form_sentiment_trends`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/ai/<form_id>/summarize`
🔒 **Requires Authentication** | Module: `ai.summarize_form_responses`

NLP Summarization: Summarize hundreds of feedback responses into 3 bullet points.

Uses extractive summarization with keyword extraction and sentiment grouping.

#### 📥 Input (Request Body)
Format: `application/json`

```text
"response_ids": ["id1", "id2", ...] (optional, defaults to all responses),
    "max_bullet_points": 3,
    "include_sentiment": true,
    "nocache": false (optional, default: false)
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/ai/<form_id>/validate-design`
🔒 **Requires Authentication** | Module: `ai.validate_form_design`

Analyzes the form design for UX/logical issues.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/ai/cross-analysis`
🔒 **Requires Authentication** | Module: `ai.compare_forms_ai`

Compare multiple forms' performance and sentiment.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/ai/generate`
🔒 **Requires Authentication** | Module: `ai.generate_form_ai`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/ai/health`
🔓 **Public Endpoint** | Module: `ai.ai_health_check`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/ai/suggestions`
🔒 **Requires Authentication** | Module: `ai.get_field_suggestions`

AI Field Suggestions based on current form context.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/ai/templates`
🔒 **Requires Authentication** | Module: `ai.list_ai_templates`

List available AI form templates.

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/ai/templates/<template_id>`
🔒 **Requires Authentication** | Module: `ai.get_ai_template`

Get a specific AI template structure.

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

## 📈 Analytics Data
> Aggregates statistics and metrics required to render dashboards and analytical views.

### `GET`  `/form/api/v1/analytics/dashboard`
🔒 **Requires Authentication** | Module: `analytics_bp.get_dashboard_stats`

System-wide Dashboard Analytics

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

## 🔐 Authentication
> Endpoints for user authentication, registration, session management, and OTP verification.

### `POST`  `/form/api/v1/auth/login`
🔓 **Public Endpoint** | Module: `auth_bp.login`

Authenticate via password or OTP and issue JWT tokens.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  "identifier": "string",
  "password": "string"
}
```

#### 📤 Output (Response)

```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "string",
  "expires_in": 0
}
```

---

### `POST`  `/form/api/v1/auth/logout`
🔒 **Requires Authentication** | Module: `auth_bp.logout`

Revoke the current JWT by adding its JTI to the blocklist.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/auth/refresh`
🔒 **Requires Authentication** | Module: `auth_bp.refresh`

Issue a new access token using a valid refresh token.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/auth/register`
🔓 **Public Endpoint** | Module: `auth_bp.register`

Register a new user account.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "username": "string",
  "email": "string",
  "employee_id": "string",
  "mobile": "string",
  "department": "string",
  "organization_id": "string",
  "user_type": "typing.Literal['employee', 'general']",
  "is_active": false,
  "is_admin": false,
  "is_email_verified": false,
  "roles": [],
  "failed_login_attempts": 0,
  "otp_resend_count": 0,
  "lock_until": "2026-03-02T12:00:00Z",
  "last_login": "2026-03-02T12:00:00Z"
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/auth/request-otp`
🔓 **Public Endpoint** | Module: `auth_bp.request_otp`

Generate and send an OTP to the given mobile/email.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

## 📱 Dashboard Management
> CRUD operations to manage custom dashboards and analytical views.

### `POST`  `/form/api/v1/dashboards/`
🔒 **Requires Authentication** | Module: `dashboard.create_dashboard`

Create a new Dashboard configuration.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `PUT`  `/form/api/v1/dashboards/<dashboard_id>`
🔒 **Requires Authentication** | Module: `dashboard.update_dashboard`

Update Dashboard configuration.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/dashboards/<slug>`
🔒 **Requires Authentication** | Module: `dashboard.get_dashboard`

Get dashboard details AND fetch data for widgets.

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

## ⚙️ Dashboard Layout & Widgets
> Configures dashboard widget positions, layouts, and available analytics widgets.

### `PUT`  `/api/v1/dashboard/layout`
🔒 **Requires Authentication** | Module: `dashboard_settings.update_layout`

Update only the layout configuration.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
        "columns": 4,
        "rowHeight": 120,
        "margin": [15, 15],
        "compactType": "vertical",
        "positions": {
            "widget_id_1": {"x": 0, "y": 0}
        }
    }
```

#### 📤 Output (Response)

```text
200: Updated settings object
    400: Validation error
    401: Unauthorized
```

---

### `POST`  `/api/v1/dashboard/reset`
🔒 **Requires Authentication** | Module: `dashboard_settings.reset_dashboard_settings`

Reset user dashboard settings to defaults.

Resets all dashboard customization settings to their default values.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```text
200: Reset settings object
    401: Unauthorized
```

---

### `GET`  `/api/v1/dashboard/settings`
🔒 **Requires Authentication** | Module: `dashboard_settings.get_dashboard_settings`

Get user dashboard settings.

Returns the complete dashboard customization settings for the authenticated user.
If no settings exist, default settings are created and returned.

#### 📤 Output (Response)

```text
200: Dashboard settings object
    401: Unauthorized
```

---

### `PUT`  `/api/v1/dashboard/settings`
🔒 **Requires Authentication** | Module: `dashboard_settings.update_dashboard_settings`

Update user dashboard settings.

Updates the dashboard customization settings for the authenticated user.
All fields are optional - only provided fields will be updated.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
        "layout": {...},      // Layout configuration
        "widgets": [...],     // Widgets array
        "theme": "dark",      // Theme preference (light/dark/system)
        "language": "en",     // Language preference
        "timezone": "UTC"     // Timezone preference
    }
```

#### 📤 Output (Response)

```text
200: Updated settings object
    400: Validation error
    401: Unauthorized
```

---

### `GET`  `/api/v1/dashboard/widgets`
🔒 **Requires Authentication** | Module: `dashboard_settings.get_available_widgets`

Get list of available widget types.

Returns all available widget types that can be added to the dashboard.

#### 📤 Output (Response)

```text
200: List of widget types
    401: Unauthorized
```

---

### `POST`  `/api/v1/dashboard/widgets`
🔒 **Requires Authentication** | Module: `dashboard_settings.add_widget`

Add a widget to the user's dashboard.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
        "type": "form_statistics",  // Widget type ID
        "position": {"x": 0, "y": 4}, // Optional position
        "size": {"w": 2, "h": 2},     // Optional size
        "config": {...}               // Optional widget config
    }
```

#### 📤 Output (Response)

```text
201: Added widget object
    400: Validation error
    401: Unauthorized
```

---

### `DELETE`  `/api/v1/dashboard/widgets/<widget_id>`
🔒 **Requires Authentication** | Module: `dashboard_settings.remove_widget`

Remove a widget from the user's dashboard.

Args:
    widget_id: ID of the widget to remove

#### 📤 Output (Response)

```text
200: Success message
    404: Widget not found
    401: Unauthorized
```

---

### `PUT`  `/api/v1/dashboard/widgets/<widget_id>`
🔒 **Requires Authentication** | Module: `dashboard_settings.update_widget`

Update a widget's configuration.

Args:
    widget_id: ID of the widget to update

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
        "position": {"x": 0, "y": 4},  // Optional new position
        "size": {"w": 2, "h": 2},      // Optional new size
        "config": {...},               // Optional config updates
        "is_visible": true             // Optional visibility
    }
```

#### 📤 Output (Response)

```text
200: Updated widget object
    404: Widget not found
    401: Unauthorized
```

---

### `PUT`  `/api/v1/dashboard/widgets/positions`
🔒 **Requires Authentication** | Module: `dashboard_settings.update_widget_positions`

Update positions for multiple widgets.

Used for drag-and-drop reordering of widgets.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
        "positions": {
            "widget_id_1": {"x": 0, "y": 0},
            "widget_id_2": {"x": 2, "y": 0}
        }
    }
```

#### 📤 Output (Response)

```text
200: List of updated widgets
    400: Validation error
    401: Unauthorized
```

---

## 🛠️ Environment Configuration
> Administrative endpoint to manipulate dynamic environment and service configurations.

### `GET`  `/api/v1/admin/env-config/`
🔒 **Requires Authentication** | Module: `env_config.get_env_configs`

Retrieve all backend environment configurations.

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `PUT`, `POST`  `/api/v1/admin/env-config/`
🔒 **Requires Authentication** | Module: `env_config.update_env_configs`

Update backend environment configurations.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

## 🔌 External Integrations
> Endpoints acting as gateways to downstream services.

### `GET`  `/form/api/v1/external/employee/<string:employee_id>`
🔒 **Requires Authentication** | Module: `external_api.get_employee_details`

Fetch details of EMPLOYEE (Empty Route Placeholder).

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/external/mail`
🔒 **Requires Authentication** | Module: `external_api.send_mail`

Send mail (Empty Route Placeholder).

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/external/sms`
🔒 **Requires Authentication** | Module: `external_api.send_sms`

Send SMS (Empty Route Placeholder).

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/external/uhid/<string:uhid>`
🔒 **Requires Authentication** | Module: `external_api.get_uhid_details`

Fetch details of UHID (Empty Route Placeholder).

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

## 📄 Form Templates
> Manages structural form templates (questions, layout) serving as bases for new forms.

### `GET`  `/form/api/v1/templates/`
🔒 **Requires Authentication** | Module: `form_templates.list_field_templates`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/templates/`
🔒 **Requires Authentication** | Module: `form_templates.save_field_template`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/templates/<template_id>`
🔒 **Requires Authentication** | Module: `form_templates.get_field_template`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `DELETE`  `/form/api/v1/templates/<template_id>`
🔒 **Requires Authentication** | Module: `form_templates.delete_field_template`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

## ❤️ System Health
> Liveness and readiness probes.

### `GET`  `/health`
🔓 **Public Endpoint** | Module: `health_check`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

## 📚 Custom Field Library
> Centralized library for reusable custom form fields and partial templates.

### `GET`  `/form/api/v1/custom-fields/`
🔒 **Requires Authentication** | Module: `library.list_field_templates`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/custom-fields/`
🔒 **Requires Authentication** | Module: `library.save_field_template`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "label": "string",
  "field_type": "typing.Literal['input', 'textarea', 'number', 'email', 'mobile', 'url', 'password']",
  "help_text": "string",
  "default_value": "string",
  "order": 0,
  "variable_name": "string",
  "is_repeatable": false,
  "repeat_min": 0,
  "repeat_max": 0,
  "keep_last_value": false,
  "is_hidden": false,
  "is_read_only": false,
  "validation": "typing.Optional[schemas.form.ValidationSchema]",
  "logic": "typing.Optional[schemas.form.QuestionLogicSchema]",
  "ui": "typing.Optional[schemas.form.QuestionUISchema]",
  "response_templates": [],
  "options": [],
  "tags": "string",
  "meta_data": "string"
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/custom-fields/<template_id>`
🔒 **Requires Authentication** | Module: `library.get_field_template`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `DELETE`  `/form/api/v1/custom-fields/<template_id>`
🔒 **Requires Authentication** | Module: `library.delete_field_template`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

## 🔍 NLP & Semantic Search
> AI-powered semantic search capabilities, querying, history, and autocomplete suggestions.

### `POST`  `/api/v1/ai/forms/<form_id>/nlp-search`
🔒 **Requires Authentication** | Module: `nlp_search.nlp_search`

Natural language search across form responses with advanced filtering.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
        "query": "Show me all users who were unhappy with delivery",
        "options": {
            "max_results": 50,
            "include_sentiment": true,
            "semantic_search": true,
            "cache_results": true,
            "fallback_models": ["llama3.1", "mistral:7b", "gemma:2b"]
        },
        "filters": {
            "date_range": {
                "start_date": "2025-01-01T00:00:00Z",
                "end_date": "2025-03-31T23:59:59Z"
            },
            "field_filters": [
                {"field": "q_rating", "operator": ">", "value": "3"},
                {"field": "q_satisfaction", "operator": "contains", "value": "positive"}
            ],
            "submitted_by": ["user1", "user2"],
            "source": ["web", "mobile"]
        },
        "filter_mode": "and"  # "and" or "or"
    }
```

#### 📤 Output (Response)

```json
{
        "query": "Show me all users who were unhappy with delivery",
        "parsed_intent": {
            "sentiment_filter": "negative",
            "topic": "delivery",
            "entities": ["delivery", "users"],
            "date_range": {...},
            "field_filters": [...]
        },
        "results_count": 15,
        "results": [...],
        "processing_time_ms": 245,
        "cached": false,
        "filters_applied": {...}
    }
```

---

### `GET`  `/api/v1/ai/forms/<form_id>/popular-queries`
🔒 **Requires Authentication** | Module: `nlp_search.get_popular_queries`

Get popular search queries for a form.

Uses caching (1 hour TTL) for performance.

#### Query Parameters
| Parameter | Description |
|-----------|-------------|
| `` | *Parameter* |
| `limit` | Maximum number of results (default: 10, max: 50) |
| `nocache` | If "true", bypasses cache and fetches fresh data |

#### 📤 Output (Response)

```json
{
        "form_id": "form123",
        "popular_queries": [
            {"query": "delivery issues", "count": 45},
            {"query": "product quality", "count": 32},
            {"query": "customer support", "count": 28}
        ],
        "cached": true
    }
```

---

### `GET`  `/api/v1/ai/forms/<form_id>/query-suggestions`
🔒 **Requires Authentication** | Module: `nlp_search.query_suggestions`

Get query suggestions/autocomplete for a form.

Provides intelligent suggestions based on:
- Most common terms from existing responses
- Form question labels and field names
- Fuzzy matching for partial queries

#### Query Parameters
| Parameter | Description |
|-----------|-------------|
| `` | *Parameter* |
| `q` | Partial query string (required) |
| `limit` | Maximum number of suggestions (optional, default: 10) |

#### 📤 Output (Response)

```json
{
        "form_id": "form123",
        "query": "del",
        "suggestions": [
            {"text": "delivery", "count": 98, "match_score": 0.92, "is_form_term": false},
            {"text": "delivered", "count": 45, "match_score": 0.88, "is_form_term": false},
            {"text": "delay", "count": 23, "match_score": 0.75, "is_form_term": true}
        ],
        "total_suggestions": 3
    }
```

---

### `GET`  `/api/v1/ai/forms/<form_id>/search-history`
🔒 **Requires Authentication** | Module: `nlp_search.get_search_history`

Get user's search history for a form.

#### Query Parameters
| Parameter | Description |
|-----------|-------------|
| `` | *Parameter* |
| `limit` | Maximum number of results (default: 50, max: 100) |
| `offset` | Number of results to skip (default: 0) |

#### 📤 Output (Response)

```json
{
        "form_id": "form123",
        "user_id": "user456",
        "history": [
            {
                "id": "search_id",
                "query": "search text",
                "timestamp": "2024-01-15T10:30:00Z",
                "results_count": 15,
                "search_type": "nlp",
                "cached": false
            }
        ],
        "total": 50,
        "limit": 50,
        "offset": 0
    }
```

---

### `POST`  `/api/v1/ai/forms/<form_id>/search-history`
🔒 **Requires Authentication** | Module: `nlp_search.save_search_history`

Save a search query to user's search history.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
        "query": "search text",
        "results_count": 15,
        "parsed_intent": {...},
        "search_type": "nlp",
        "cached": false
    }
```

#### 📤 Output (Response)

```json
{
        "id": "search_id",
        "query": "search text",
        "timestamp": "2024-01-15T10:30:00Z",
        "message": "Search saved successfully"
    }
```

---

### `DELETE`  `/api/v1/ai/forms/<form_id>/search-history`
🔒 **Requires Authentication** | Module: `nlp_search.clear_search_history`

Clear user's search history for a form.

#### Query Parameters
| Parameter | Description |
|-----------|-------------|
| `` | *Parameter* |
| `all` | If "true", clears all search history (not just for this form) |

#### 📤 Output (Response)

```json
{
        "deleted_count": 15,
        "message": "Search history cleared successfully"
    }
```

---

### `DELETE`  `/api/v1/ai/forms/<form_id>/search-history/<search_id>`
🔒 **Requires Authentication** | Module: `nlp_search.delete_search_history_item`

Delete a specific search history item.

#### 📤 Output (Response)

```json
{
        "deleted_count": 1,
        "message": "Search record deleted successfully"
    }
```

---

### `GET`  `/api/v1/ai/forms/<form_id>/search-stats`
🔒 **Requires Authentication** | Module: `nlp_search.search_stats`

Get search-related statistics for a form.

#### 📤 Output (Response)

```json
{
        "total_responses": 250,
        "indexed_responses": 250,
        "ollama_available": true,
        "supported_query_types": ["sentiment", "topic", "semantic", "time"]
    }
```

---

### `POST`  `/api/v1/ai/forms/<form_id>/semantic-search`
🔒 **Requires Authentication** | Module: `nlp_search.semantic_search`

Pure semantic search using Ollama embeddings with advanced filtering.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
        "query": "What are the main complaints about product quality?",
        "similarity_threshold": 0.7,
        "max_results": 20,
        "fallback_models": ["llama3.1", "mistral:7b", "gemma:2b"],
        "date_range": {
            "start_date": "2025-01-01T00:00:00Z",
            "end_date": "2025-03-31T23:59:59Z"
        },
        "field_filters": [
            {"field": "q_rating", "operator": "<", "value": "3"}
        ],
        "submitted_by": ["user1", "user2"],
        "filter_mode": "and"
    }
```

#### 📤 Output (Response)

```json
{
        "query": "What are the main complaints about product quality?",
        "embedding_model": "nomic-embed-text",
        "results_count": 8,
        "results": [...],
        "filters_applied": {...}
    }
```

---

### `POST`  `/api/v1/ai/forms/<form_id>/semantic-search/stream`
🔒 **Requires Authentication** | Module: `nlp_search.semantic_search_stream`

Pure semantic search using Ollama embeddings with streaming response and advanced filtering.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
        "query": "What are the main complaints about product quality?",
        "similarity_threshold": 0.7,
        "max_results": 20,
        "fallback_models": ["llama3.1", "mistral:7b", "gemma:2b"],
        "date_range": {
            "start_date": "2025-01-01T00:00:00Z",
            "end_date": "2025-03-31T23:59:59Z"
        },
        "field_filters": [
            {"field": "q_rating", "operator": "<", "value": "3"}
        ],
        "filter_mode": "and"
    }
```

#### 📤 Output (Response)

```json
Server-Sent Events (SSE) Stream:
    data: { "content": "partial text", "done": false }
    ...
    data: { "content": "", "done": true, "model_used": "llama3.2", "results_count": 8 }
```

---

### `GET`  `/api/v1/ai/forms/health`
🔓 **Public Endpoint** | Module: `nlp_search.health_check`

Health check for NLP search service.

#### 📤 Output (Response)

```json
{
        "status": "healthy",
        "ollama": {...},
        "nlp": {...}
    }
```

---

## 🛡️ Access Control
> Granular route-level or form-level permission mappings and role modifications.

### `GET`  `/form/api/v1/forms/<form_id>/permissions`
🔒 **Requires Authentication** | Module: `permissions.get_form_permissions`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "resource_type": "typing.Literal['form', 'project', 'submission', 'view']",
  "resource_id": "string",
  "access_level": "typing.Literal['private', 'group', 'organization', 'public']",
  "entries": [],
  "approval_workflow": "string",
  "is_active": false,
  "meta_data": "string",
  "tags": "string"
}
```

---

### `POST`  `/form/api/v1/forms/<form_id>/permissions`
🔒 **Requires Authentication** | Module: `permissions.update_form_permissions`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "resource_type": "typing.Literal['form', 'project', 'submission', 'view']",
  "resource_id": "string",
  "access_level": "typing.Literal['private', 'group', 'organization', 'public']",
  "entries": [],
  "approval_workflow": "string",
  "is_active": false,
  "meta_data": "string",
  "tags": "string"
}
```

#### 📤 Output (Response)

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "resource_type": "typing.Literal['form', 'project', 'submission', 'view']",
  "resource_id": "string",
  "access_level": "typing.Literal['private', 'group', 'organization', 'public']",
  "entries": [],
  "approval_workflow": "string",
  "is_active": false,
  "meta_data": "string",
  "tags": "string"
}
```

---

## 🗨️ SMS Gateway
> Direct integrations with SMS providers for notifications and OTP delivery.

### `GET`  `/api/v1/sms/health`
🔓 **Public Endpoint** | Module: `sms.health_check`

Health check endpoint for the SMS service.

This endpoint checks if the external SMS API is reachable.

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/api/v1/sms/notify`
🔓 **Public Endpoint** | Module: `sms.send_notification`

Send a notification via SMS.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
        "mobile": "9899378106",
        "title": "Appointment Reminder",
        "body": "Your appointment is tomorrow at 10 AM"
    }
```

#### 📤 Output (Response)

```json
{
        "success": true,
        "message_id": "...",
        "status_code": 200
    }
```

---

### `POST`  `/api/v1/sms/otp`
🔓 **Public Endpoint** | Module: `sms.send_otp`

Send an OTP via SMS.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
        "mobile": "9899378106",
        "otp": "123456"
    }
```

#### 📤 Output (Response)

```json
{
        "success": true,
        "message_id": "...",
        "status_code": 200
    }
```

---

### `POST`  `/api/v1/sms/single`
🔓 **Public Endpoint** | Module: `sms.send_single_sms`

Send a single SMS message via external API.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
        "mobile": "9899378106",
        "message": "Hello from AIIMS"
    }
```

#### 📤 Output (Response)

```json
{
        "success": true,
        "message_id": "...",
        "status_code": 200
    }
```

---

## 📊 AI Summarization
> Generates and retrieves executive, thematic, and temporal summaries of form responses.

### `POST`  `/api/v1/ai/forms/<form_id>/executive-summary`
🔒 **Requires Authentication** | Module: `summarization.executive_summary`

Generate executive summary for leadership.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
        "response_ids": [],
        "audience": "leadership",
        "tone": "formal",
        "max_points": 5,
        "detail_level": "standard",
        "include_examples": true,
        "fallback_models": ["llama3.1", "mistral:7b", "gemma:2b"]
    }
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/api/v1/ai/forms/<form_id>/summarize`
🔒 **Requires Authentication** | Module: `summarization.summarize`

Generate summary from form responses.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
        "response_ids": [],
        "strategy": "hybrid",
        "format": "bullet_points",
        "config": {},
        "max_points": 5,
        "detail_level": "standard",
        "include_examples": true,
        "fallback_models": ["llama3.1", "mistral:7b", "gemma:2b"],
        "save_snapshot": true
    }
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/api/v1/ai/forms/<form_id>/summarize/stream`
🔒 **Requires Authentication** | Module: `summarization.summarize_stream`

Generate summary from form responses with streaming response.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
        "response_ids": [],
        "strategy": "hybrid",
        "format": "bullet_points",
        "config": {},
        "max_points": 5,
        "detail_level": "standard",
        "include_examples": true,
        "fallback_models": ["llama3.1", "mistral:7b", "gemma:2b"]
    }
```

#### 📤 Output (Response)

```json
Server-Sent Events (SSE) Stream:
    data: { "content": "partial text", "done": false }
    ...
    data: { "content": "", "done": true, "model_used": "llama3.2", "responses_analyzed": 150 }
```

---

### `GET`  `/api/v1/ai/forms/<form_id>/summary-comparison`
🔒 **Requires Authentication** | Module: `summarization.summary_comparison`

Compare summaries across multiple time periods.

#### Query Parameters
| Parameter | Description |
|-----------|-------------|
| `` | *Parameter* |
| `period_ranges` | JSON array of period ranges with 'start', 'end', and optional 'label' |
| `Example` | [{"start": "2025-01-01T00:00:00Z", "end": "2025-01-31T23:59:59Z", "label": "January 2025"}, |
| `{"start"` | "2025-02-01T00:00:00Z", "end": "2025-02-28T23:59:59Z", "label": "February 2025"}] |
| `preset` | Optional preset period comparison (last_7_days, last_30_days, last_90_days, month_over_month) |
| `If provided` | *Parameter* |
| `period_ranges is ignored` | *Parameter* |

#### 📤 Output (Response)

```text
Comparison data with trend analysis across periods
```

---

### `GET`  `/api/v1/ai/forms/<form_id>/summary-snapshots`
🔒 **Requires Authentication** | Module: `summarization.list_summary_snapshots`

List all summary snapshots for a form.

#### Query Parameters
| Parameter | Description |
|-----------|-------------|
| `` | *Parameter* |
| `limit` | Maximum number of snapshots to return. Default: 20 |
| `offset` | Number of snapshots to skip. Default: 0 |

#### 📤 Output (Response)

```text
List of summary snapshots
```

---

### `GET`  `/api/v1/ai/forms/<form_id>/summary-trends`
🔒 **Requires Authentication** | Module: `summarization.summary_trends`

Get trend data for a specific metric over time.

#### Query Parameters
| Parameter | Description |
|-----------|-------------|
| `` | *Parameter* |
| `metric` | Metric to track (sentiment, theme, response_count). Default: sentiment |
| `limit` | Maximum number of snapshots to include. Default: 10 |

#### 📤 Output (Response)

```text
Trend data for the specified metric
```

---

### `POST`  `/api/v1/ai/forms/<form_id>/theme-summary`
🔒 **Requires Authentication** | Module: `summarization.theme_summary`

Generate theme-based summary.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
        "themes": ["delivery", "product", "support", "pricing"],
        "include_quote_examples": true,
        "sentiment_per_theme": true,
        "max_points": 5,
        "detail_level": "standard",
        "include_examples": true,
        "fallback_models": ["llama3.1", "mistral:7b", "gemma:2b"]
    }
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

## 💻 System Administration
> Global system configurations impacting platform-wide behavior.

### `GET`  `/api/v1/admin/system-settings/`
🔒 **Requires Authentication** | Module: `system_settings.get_system_settings`

Retrieve the global system configuration.

#### 📤 Output (Response)

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "env_key": "string",
  "jwt_access_token_expires_minutes": 0,
  "jwt_refresh_token_expires_days": 0,
  "max_failed_login_attempts": 0,
  "account_lock_duration_hours": 0,
  "password_expiration_days": 0,
  "otp_expiration_minutes": 0,
  "max_otp_resends": 0,
  "max_upload_size_mb": 0,
  "allowed_upload_extensions": "string",
  "cache_enabled": false,
  "cache_default_ttl_seconds": 0,
  "cache_form_schema_ttl_seconds": 0,
  "cache_user_session_ttl_seconds": 0,
  "cache_query_result_ttl_seconds": 0,
  "cache_dashboard_widget_ttl_seconds": 0,
  "cache_api_response_ttl_seconds": 0,
  "llm_provider": "string",
  "llm_api_url": "string",
  "llm_model": "string",
  "ollama_api_url": "string",
  "ollama_embedding_model": "string",
  "ollama_pool_size": 0,
  "ollama_pool_timeout_seconds": 0,
  "ollama_connection_timeout_seconds": 0,
  "redis_host": "string",
  "redis_port": 0,
  "redis_db": 0,
  "redis_max_connections": 0,
  "redis_socket_timeout_seconds": 0,
  "cors_enabled": false,
  "debug_mode": false,
  "rate_limit_enabled": false,
  "rate_limit_requests_per_minute": 0,
  "updated_by": "string"
}
```

---

### `PUT`  `/api/v1/admin/system-settings/`
🔒 **Requires Authentication** | Module: `system_settings.update_system_settings`

Update the global system configuration.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "env_key": "string",
  "jwt_access_token_expires_minutes": 0,
  "jwt_refresh_token_expires_days": 0,
  "max_failed_login_attempts": 0,
  "account_lock_duration_hours": 0,
  "password_expiration_days": 0,
  "otp_expiration_minutes": 0,
  "max_otp_resends": 0,
  "max_upload_size_mb": 0,
  "allowed_upload_extensions": "string",
  "cache_enabled": false,
  "cache_default_ttl_seconds": 0,
  "cache_form_schema_ttl_seconds": 0,
  "cache_user_session_ttl_seconds": 0,
  "cache_query_result_ttl_seconds": 0,
  "cache_dashboard_widget_ttl_seconds": 0,
  "cache_api_response_ttl_seconds": 0,
  "llm_provider": "string",
  "llm_api_url": "string",
  "llm_model": "string",
  "ollama_api_url": "string",
  "ollama_embedding_model": "string",
  "ollama_pool_size": 0,
  "ollama_pool_timeout_seconds": 0,
  "ollama_connection_timeout_seconds": 0,
  "redis_host": "string",
  "redis_port": 0,
  "redis_db": 0,
  "redis_max_connections": 0,
  "redis_socket_timeout_seconds": 0,
  "cors_enabled": false,
  "debug_mode": false,
  "rate_limit_enabled": false,
  "rate_limit_requests_per_minute": 0,
  "updated_by": "string"
}
```

#### 📤 Output (Response)

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "env_key": "string",
  "jwt_access_token_expires_minutes": 0,
  "jwt_refresh_token_expires_days": 0,
  "max_failed_login_attempts": 0,
  "account_lock_duration_hours": 0,
  "password_expiration_days": 0,
  "otp_expiration_minutes": 0,
  "max_otp_resends": 0,
  "max_upload_size_mb": 0,
  "allowed_upload_extensions": "string",
  "cache_enabled": false,
  "cache_default_ttl_seconds": 0,
  "cache_form_schema_ttl_seconds": 0,
  "cache_user_session_ttl_seconds": 0,
  "cache_query_result_ttl_seconds": 0,
  "cache_dashboard_widget_ttl_seconds": 0,
  "cache_api_response_ttl_seconds": 0,
  "llm_provider": "string",
  "llm_api_url": "string",
  "llm_model": "string",
  "ollama_api_url": "string",
  "ollama_embedding_model": "string",
  "ollama_pool_size": 0,
  "ollama_pool_timeout_seconds": 0,
  "ollama_connection_timeout_seconds": 0,
  "redis_host": "string",
  "redis_port": 0,
  "redis_db": 0,
  "redis_max_connections": 0,
  "redis_socket_timeout_seconds": 0,
  "cors_enabled": false,
  "debug_mode": false,
  "rate_limit_enabled": false,
  "rate_limit_requests_per_minute": 0,
  "updated_by": "string"
}
```

---

## 🌐 Localization & Translation
> Handles async translation jobs, multi-lingual previews, and content localization caches.

### `GET`  `/form/api/v1/forms/translations`
🔒 **Requires Authentication** | Module: `translation.get_translations`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/forms/translations`
🔒 **Requires Authentication** | Module: `translation.save_translations`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`, `POST`  `/form/api/v1/forms/translations/jobs`
🔒 **Requires Authentication** | Module: `translation.handle_jobs`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/forms/translations/jobs/<job_id>`
🔒 **Requires Authentication** | Module: `translation.get_job_status`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `DELETE`  `/form/api/v1/forms/translations/jobs/<job_id>`
🔒 **Requires Authentication** | Module: `translation.delete_job`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `PATCH`  `/form/api/v1/forms/translations/jobs/<job_id>/cancel`
🔒 **Requires Authentication** | Module: `translation.cancel_job`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/forms/translations/jobs/<job_id>/content`
🔒 **Requires Authentication** | Module: `translation.get_translated_content`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/forms/translations/languages`
🔒 **Requires Authentication** | Module: `translation.list_languages`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/forms/translations/preview`
🔒 **Requires Authentication** | Module: `translation.preview_translation`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

## 👤 User Profile
> Self-service endpoints for user profiling, password changes, and security statuses.

### `POST`  `/form/api/v1/user/change-password`
🔒 **Requires Authentication** | Module: `user_bp.change_password`

Change the current user's password.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/user/request-otp`
🔓 **Public Endpoint** | Module: `user_bp.request_otp`

Request an OTP for mobile/email login.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/user/reset-password`
🔓 **Public Endpoint** | Module: `user_bp.reset_password`

Reset password via OTP or admin user_id (unauthenticated).

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/user/security/lock-status/<user_id>`
🔒 **Requires Authentication** | Module: `user_bp.lock_status`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/user/status`
🔒 **Requires Authentication** | Module: `user_bp.auth_status`

Return profile of the authenticated user.

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/user/users`
🔒 **Requires Authentication** | Module: `user_bp.list_users`

List all users. Requires admin role.

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/user/users`
🔒 **Requires Authentication** | Module: `user_bp.create_user`

Create a new user.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "username": "string",
  "email": "string",
  "employee_id": "string",
  "mobile": "string",
  "department": "string",
  "organization_id": "string",
  "user_type": "typing.Literal['employee', 'general']",
  "is_active": false,
  "is_admin": false,
  "is_email_verified": false,
  "roles": [],
  "failed_login_attempts": 0,
  "otp_resend_count": 0,
  "lock_until": "2026-03-02T12:00:00Z",
  "last_login": "2026-03-02T12:00:00Z"
}
```

#### 📤 Output (Response)

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "username": "string",
  "email": "string",
  "employee_id": "string",
  "mobile": "string",
  "department": "string",
  "organization_id": "string",
  "user_type": "typing.Literal['employee', 'general']",
  "is_active": false,
  "is_admin": false,
  "is_email_verified": false,
  "roles": [],
  "failed_login_attempts": 0,
  "otp_resend_count": 0,
  "lock_until": "2026-03-02T12:00:00Z",
  "last_login": "2026-03-02T12:00:00Z"
}
```

---

### `GET`  `/form/api/v1/user/users/<user_id>`
🔒 **Requires Authentication** | Module: `user_bp.get_user`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "username": "string",
  "email": "string",
  "employee_id": "string",
  "mobile": "string",
  "department": "string",
  "organization_id": "string",
  "user_type": "typing.Literal['employee', 'general']",
  "is_active": false,
  "is_admin": false,
  "is_email_verified": false,
  "roles": [],
  "failed_login_attempts": 0,
  "otp_resend_count": 0,
  "lock_until": "2026-03-02T12:00:00Z",
  "last_login": "2026-03-02T12:00:00Z"
}
```

---

### `PUT`  `/form/api/v1/user/users/<user_id>`
🔒 **Requires Authentication** | Module: `user_bp.update_user`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "username": "string",
  "email": "string",
  "employee_id": "string",
  "mobile": "string",
  "department": "string",
  "organization_id": "string",
  "user_type": "typing.Literal['employee', 'general']",
  "is_active": false,
  "is_admin": false,
  "is_email_verified": false,
  "roles": [],
  "failed_login_attempts": 0,
  "otp_resend_count": 0,
  "lock_until": "2026-03-02T12:00:00Z",
  "last_login": "2026-03-02T12:00:00Z"
}
```

#### 📤 Output (Response)

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "username": "string",
  "email": "string",
  "employee_id": "string",
  "mobile": "string",
  "department": "string",
  "organization_id": "string",
  "user_type": "typing.Literal['employee', 'general']",
  "is_active": false,
  "is_admin": false,
  "is_email_verified": false,
  "roles": [],
  "failed_login_attempts": 0,
  "otp_resend_count": 0,
  "lock_until": "2026-03-02T12:00:00Z",
  "last_login": "2026-03-02T12:00:00Z"
}
```

---

### `DELETE`  `/form/api/v1/user/users/<user_id>`
🔒 **Requires Authentication** | Module: `user_bp.delete_user`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/user/users/<user_id>/lock`
🔒 **Requires Authentication** | Module: `user_bp.lock_user`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/form/api/v1/user/users/<user_id>/unlock`
🔒 **Requires Authentication** | Module: `user_bp.unlock_user`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

## 👥 Admin User Management
> Administrative endpoints to manage user accounts, lifecycle, and permissions.

### `GET`  `/api/v1/admin/users/`
🔒 **Requires Authentication** | Module: `user_mgmt.list_users_admin`

List all users (paginated).

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/api/v1/admin/users/`
🔒 **Requires Authentication** | Module: `user_mgmt.create_user_admin`

Create a user (admin only).

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "username": "string",
  "email": "string",
  "employee_id": "string",
  "mobile": "string",
  "department": "string",
  "organization_id": "string",
  "user_type": "typing.Literal['employee', 'general']",
  "is_active": false,
  "is_admin": false,
  "is_email_verified": false,
  "roles": [],
  "failed_login_attempts": 0,
  "otp_resend_count": 0,
  "lock_until": "2026-03-02T12:00:00Z",
  "last_login": "2026-03-02T12:00:00Z"
}
```

#### 📤 Output (Response)

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "username": "string",
  "email": "string",
  "employee_id": "string",
  "mobile": "string",
  "department": "string",
  "organization_id": "string",
  "user_type": "typing.Literal['employee', 'general']",
  "is_active": false,
  "is_admin": false,
  "is_email_verified": false,
  "roles": [],
  "failed_login_attempts": 0,
  "otp_resend_count": 0,
  "lock_until": "2026-03-02T12:00:00Z",
  "last_login": "2026-03-02T12:00:00Z"
}
```

---

### `GET`  `/api/v1/admin/users/<user_id>`
🔒 **Requires Authentication** | Module: `user_mgmt.get_user_admin`

Get a single user by ID.

#### 📤 Output (Response)

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "username": "string",
  "email": "string",
  "employee_id": "string",
  "mobile": "string",
  "department": "string",
  "organization_id": "string",
  "user_type": "typing.Literal['employee', 'general']",
  "is_active": false,
  "is_admin": false,
  "is_email_verified": false,
  "roles": [],
  "failed_login_attempts": 0,
  "otp_resend_count": 0,
  "lock_until": "2026-03-02T12:00:00Z",
  "last_login": "2026-03-02T12:00:00Z"
}
```

---

### `PUT`  `/api/v1/admin/users/<user_id>`
🔒 **Requires Authentication** | Module: `user_mgmt.update_user_admin`

Update a user's details (admin only).

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "username": "string",
  "email": "string",
  "employee_id": "string",
  "mobile": "string",
  "department": "string",
  "organization_id": "string",
  "user_type": "typing.Literal['employee', 'general']",
  "is_active": false,
  "is_admin": false,
  "is_email_verified": false,
  "roles": [],
  "failed_login_attempts": 0,
  "otp_resend_count": 0,
  "lock_until": "2026-03-02T12:00:00Z",
  "last_login": "2026-03-02T12:00:00Z"
}
```

#### 📤 Output (Response)

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "username": "string",
  "email": "string",
  "employee_id": "string",
  "mobile": "string",
  "department": "string",
  "organization_id": "string",
  "user_type": "typing.Literal['employee', 'general']",
  "is_active": false,
  "is_admin": false,
  "is_email_verified": false,
  "roles": [],
  "failed_login_attempts": 0,
  "otp_resend_count": 0,
  "lock_until": "2026-03-02T12:00:00Z",
  "last_login": "2026-03-02T12:00:00Z"
}
```

---

### `DELETE`  `/api/v1/admin/users/<user_id>`
🔒 **Requires Authentication** | Module: `user_mgmt.delete_user_admin`

Soft-delete a user (admin only).

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/api/v1/admin/users/<user_id>/lock`
🔒 **Requires Authentication** | Module: `user_mgmt.lock_user_admin`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/api/v1/admin/users/<user_id>/reset-password`
🔒 **Requires Authentication** | Module: `user_mgmt.admin_reset_password`

Admin force-resets a user's password.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `POST`  `/api/v1/admin/users/<user_id>/unlock`
🔒 **Requires Authentication** | Module: `user_mgmt.unlock_user_admin`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  // Payload schema not explicitly defined
}
```

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

## 🖼️ Frontend Views
> Routes designated to serve static or frontend views.

### `GET`  `/form/`
🔓 **Public Endpoint** | Module: `view_bp.index`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/<form_id>`
🔓 **Public Endpoint** | Module: `view_bp.view_form`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

## 🪝 Webhook Dispatcher
> Manages outbound webhook lifecycles including delivery, retries, logs, and testing.

### `DELETE`  `/api/v1/webhooks/<delivery_id>/cancel`
🔒 **Requires Authentication** | Module: `webhooks.cancel_webhook`

Cancel a pending or retrying webhook delivery.

#### Path Parameters
| Parameter | Description |
|-----------|-------------|
| `delivery_id` | The ID of the webhook delivery |

#### 📤 Output (Response)

```json
{
    "status": "success",
    "delivery_id": "delivery_id",
    "message": "Webhook delivery cancelled successfully"
}
```

---

### `GET`  `/api/v1/webhooks/<delivery_id>/history`
🔒 **Requires Authentication** | Module: `webhooks.get_webhook_history`

Get webhook delivery history for a specific delivery.

#### Path Parameters
| Parameter | Description |
|-----------|-------------|
| `delivery_id` | The ID of the webhook delivery |

#### Query Parameters
| Parameter | Description |
|-----------|-------------|
| `` | *Parameter* |
| `form_id` | Filter by form ID (optional) |
| `webhook_id` | Filter by webhook ID (optional) |
| `status` | Filter by status (optional): pending, in_progress, success, failed, retrying, cancelled |
| `page` | Page number (default: 1) |
| `per_page` | Number of items per page (default: 20) |

#### 📤 Output (Response)

```json
{
    "deliveries": [...],
    "total": 100,
    "page": 1,
    "per_page": 20,
    "total_pages": 5
}
```

---

### `POST`  `/api/v1/webhooks/<delivery_id>/retry`
🔒 **Requires Authentication** | Module: `webhooks.retry_webhook`

Retry a failed webhook delivery.

#### Path Parameters
| Parameter | Description |
|-----------|-------------|
| `delivery_id` | The ID of the webhook delivery |

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
    "reset_count": false
}
```

#### 📤 Output (Response)

```json
{
    "status": "success" | "failed",
    "delivery_id": "new_delivery_id",
    "attempt_count": int,
    "message": str,
    "error": str (optional),
    "previous_delivery_id": "old_delivery_id"
}
```

---

### `GET`  `/api/v1/webhooks/<delivery_id>/status`
🔒 **Requires Authentication** | Module: `webhooks.get_webhook_status`

Get webhook delivery status.

#### Path Parameters
| Parameter | Description |
|-----------|-------------|
| `delivery_id` | The ID of the webhook delivery |

#### 📤 Output (Response)

```json
{
    "id": "delivery_id",
    "webhook_id": "webhook_config_id",
    "url": "https://example.com/webhook",
    "form_id": "form_id",
    "payload": {...},
    "status": "success",
    "attempt_count": 1,
    "max_retries": 5,
    "last_attempt_at": "2026-02-04T08:00:00Z",
    "next_retry_at": "2026-02-04T08:02:00Z",
    "created_by": "user_id",
    "response_code": 200,
    "response_body": "...",
    "error_message": null,
    "metadata": {...},
    "created_at": "2026-02-04T08:00:00Z",
    "completed_at": "2026-02-04T08:00:00Z"
}
```

---

### `POST`  `/api/v1/webhooks/deliver`
🔒 **Requires Authentication** | Module: `webhooks.deliver_webhook`

Trigger webhook delivery with retry mechanism.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
    "url": "https://example.com/webhook",
    "webhook_id": "webhook_config_id",
    "form_id": "form_id",
    "payload": {
        "event": "submitted",
        "data": {"key": "value"}
    },
    "max_retries": 5,
    "headers": {
        "Authorization": "Bearer token"
    },
    "timeout": 10,
    "schedule_for": "2026-02-04T10:00:00Z"
}
```

#### 📤 Output (Response)

```json
{
    "status": "success" | "failed" | "scheduled",
    "delivery_id": "delivery_id",
    "attempt_count": int,
    "message": str,
    "error": str (optional),
    "next_retry_at": "ISO-8601 timestamp" (optional)
}
```

---

### `GET`  `/api/v1/webhooks/logs`
🔒 **Requires Authentication** | Module: `webhooks.get_webhook_logs`

Retrieve webhook logs with optional filtering (legacy endpoint).

#### Query Parameters
| Parameter | Description |
|-----------|-------------|
| `` | *Parameter* |
| `url` | Filter by webhook URL (optional) |
| `status` | Filter by status (optional): pending, success, failed, retrying |
| `limit` | Maximum number of logs to return (default: 100) |

#### 📤 Output (Response)

```json
{
    "count": 10,
    "logs": [
        {
            "id": "log_id",
            "url": "https://example.com/webhook",
            "payload": {...},
            "status": "success",
            "attempt_count": 1,
            "last_attempt": "2026-02-04T09:00:00Z",
            "error_message": null,
            "status_code": 200,
            "created_at": "2026-02-04T09:00:00Z",
            "metadata": {...}
        }
    ]
}
```

---

### `GET`  `/api/v1/webhooks/logs/<log_id>`
🔒 **Requires Authentication** | Module: `webhooks.get_webhook_log`

Retrieve a specific webhook log by ID (legacy endpoint).

#### Path Parameters
| Parameter | Description |
|-----------|-------------|
| `log_id` | The ID of the webhook log |

#### 📤 Output (Response)

```json
{
    "id": "log_id",
    "url": "https://example.com/webhook",
    "payload": {...},
    "status": "success",
    "attempt_count": 1,
    "last_attempt": "2026-02-04T09:00:00Z",
    "error_message": null,
    "status_code": 200,
    "created_at": "2026-02-04T09:00:00Z",
    "metadata": {...}
}
```

---

### `POST`  `/api/v1/webhooks/test`
🔒 **Requires Authentication** | Module: `webhooks.test_webhook`

Test webhook delivery with retry mechanism.

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
    "url": "https://example.com/webhook",
    "payload": {
        "event": "test",
        "data": {"key": "value"}
    },
    "max_retries": 3,
    "headers": {
        "Authorization": "Bearer token"
    }
}
```

#### 📤 Output (Response)

```json
{
    "status": "success" | "failed",
    "attempt_count": int,
    "log_id": str,
    "message": str,
    "error": str (optional)
}
```

---

## 🔄 Form Workflows
> Business logic orchestrator managing states and triggers for form submittals.

### `POST`  `/form/api/v1/workflows/`
🔒 **Requires Authentication** | Module: `workflow.create_workflow`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "organization_id": "string",
  "workflow_definition": "string",
  "resource_type": "typing.Literal['form_response']",
  "resource_id": "string",
  "status": "typing.Literal['pending', 'in_review', 'approved', 'rejected', 'reverted']",
  "current_step_order": 0,
  "history": [],
  "started_at": "2026-03-02T12:00:00Z",
  "completed_at": "2026-03-02T12:00:00Z",
  "meta_data": "string"
}
```

#### 📤 Output (Response)

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "organization_id": "string",
  "workflow_definition": "string",
  "resource_type": "typing.Literal['form_response']",
  "resource_id": "string",
  "status": "typing.Literal['pending', 'in_review', 'approved', 'rejected', 'reverted']",
  "current_step_order": 0,
  "history": [],
  "started_at": "2026-03-02T12:00:00Z",
  "completed_at": "2026-03-02T12:00:00Z",
  "meta_data": "string"
}
```

---

### `GET`  `/form/api/v1/workflows/`
🔒 **Requires Authentication** | Module: `workflow.list_workflows`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

### `GET`  `/form/api/v1/workflows/<workflow_id>`
🔒 **Requires Authentication** | Module: `workflow.get_workflow`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "organization_id": "string",
  "workflow_definition": "string",
  "resource_type": "typing.Literal['form_response']",
  "resource_id": "string",
  "status": "typing.Literal['pending', 'in_review', 'approved', 'rejected', 'reverted']",
  "current_step_order": 0,
  "history": [],
  "started_at": "2026-03-02T12:00:00Z",
  "completed_at": "2026-03-02T12:00:00Z",
  "meta_data": "string"
}
```

---

### `PUT`  `/form/api/v1/workflows/<workflow_id>`
🔒 **Requires Authentication** | Module: `workflow.update_workflow`

*(Standard endpoint operation.)*

#### 📥 Input (Request Body)
Format: `application/json`

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "organization_id": "string",
  "workflow_definition": "string",
  "resource_type": "typing.Literal['form_response']",
  "resource_id": "string",
  "status": "typing.Literal['pending', 'in_review', 'approved', 'rejected', 'reverted']",
  "current_step_order": 0,
  "history": [],
  "started_at": "2026-03-02T12:00:00Z",
  "completed_at": "2026-03-02T12:00:00Z",
  "meta_data": "string"
}
```

#### 📤 Output (Response)

```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "organization_id": "string",
  "workflow_definition": "string",
  "resource_type": "typing.Literal['form_response']",
  "resource_id": "string",
  "status": "typing.Literal['pending', 'in_review', 'approved', 'rejected', 'reverted']",
  "current_step_order": 0,
  "history": [],
  "started_at": "2026-03-02T12:00:00Z",
  "completed_at": "2026-03-02T12:00:00Z",
  "meta_data": "string"
}
```

---

### `DELETE`  `/form/api/v1/workflows/<workflow_id>`
🔒 **Requires Authentication** | Module: `workflow.delete_workflow`

*(Standard endpoint operation.)*

#### 📤 Output (Response)

```json
{
  // Response schema not explicitly defined
}
```

---

---

## 📘 Schema Definitions Dictionary
> Complete list of all Pydantic component schemas referenced throughout the API.

### `AccessEntrySchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "grantee_type": "typing.Literal['user', 'group']",
  "grantee_user": "string",
  "grantee_group": "string",
  "permissions": []
}
```

### `ApprovalLogSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "action_by": "string",
  "action": "typing.Literal['approve', 'reject', 'revert', 'claim']",
  "comment": "string",
  "timestamp": "2026-03-02T12:00:00Z",
  "step_name": "string"
}
```

### `ApprovalStepSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "step_name": "string",
  "order": 0,
  "approvers": "string",
  "approver_groups": "string",
  "approval_type": "typing.Literal['sequential', 'parallel', 'maker-checker', 'any_one']",
  "min_approvals_required": 0,
  "on_approve_script": "string",
  "on_reject_script": "string"
}
```

### `ApprovalWorkflowSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "name": "string",
  "description": "string",
  "initiator_groups": "string",
  "steps": [],
  "is_active": false,
  "meta_data": "string",
  "tags": "string"
}
```

### `BaseEmbeddedSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z"
}
```

### `BaseSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z"
}
```

### `ConditionSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "name": "string",
  "type": "typing.Literal['simple', 'group']",
  "logical_operator": "typing.Literal['AND', 'OR', 'NOT', 'NOR', 'NAND']",
  "conditions": [],
  "source_type": "typing.Literal['field', 'hidden_field', 'url_param', 'user_info', 'calculated_value']",
  "source_id": "string",
  "operator": [],
  "comparison_type": "typing.Literal['constant', 'field', 'url_param', 'user_info', 'calculation']",
  "comparison_value": "string",
  "custom_script": "string",
  "meta_data": "string",
  "is_debuggable": false,
  "test_payload": "string",
  "expression_string": "string",
  "cross_validation_enabled": false
}
```

### `ConditionSchemaStruct`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "name": "string",
  "type": "typing.Literal['simple', 'group']",
  "logical_operator": "typing.Literal['AND', 'OR', 'NOT', 'NOR', 'NAND']",
  "conditions": [],
  "source_type": "typing.Literal['field', 'hidden_field', 'url_param', 'user_info', 'calculated_value']",
  "source_id": "string",
  "operator": [],
  "comparison_type": "typing.Literal['constant', 'field', 'url_param', 'user_info', 'calculation']",
  "comparison_value": "string",
  "custom_script": "string",
  "meta_data": "string",
  "is_debuggable": false,
  "test_payload": "string",
  "expression_string": "string",
  "cross_validation_enabled": false
}
```

### `ConditionalValidationSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "logical_operator": "string",
  "conditions": [],
  "error_message": "string"
}
```

### `DynamicViewDefinitionSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "organization_id": "string",
  "view_name": "string",
  "description": "string",
  "form": "string",
  "project": "string",
  "pipeline": "string",
  "tags": "string"
}
```

### `FormBlueprintSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "name": "string",
  "description": "string",
  "category": "string",
  "tags": "string",
  "sections": [],
  "response_templates": [],
  "icon": "string",
  "estimated_completion_time": 0,
  "industry": "string",
  "usage_count": 0,
  "is_official": false,
  "meta_data": "string"
}
```

### `FormResponseSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "project": "string",
  "form": "string",
  "form_version": "string",
  "organization_id": "string",
  "data": "string",
  "submitted_by": "string",
  "submitted_at": "2026-03-02T12:00:00Z",
  "ip_address": "string",
  "user_agent": "string",
  "status": "typing.Literal['submitted', 'processed', 'error', 'archived']",
  "review_status": "typing.Literal['pending', 'approved', 'rejected']",
  "meta_data": "string",
  "tags": "string"
}
```

### `FormSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "title": "string",
  "slug": "string",
  "organization_id": "string",
  "created_by": "string",
  "status": "typing.Literal['draft', 'published', 'archived']",
  "ui_type": "typing.Literal['flex', 'grid-cols-2', 'tabbed', 'custom', 'grid-cols-3', 'full-width', 'cards', 'card']",
  "active_version": "string",
  "description": "string",
  "help_text": "string",
  "expires_at": "2026-03-02T12:00:00Z",
  "publish_at": "2026-03-02T12:00:00Z",
  "is_template": false,
  "is_public": false,
  "supported_languages": "string",
  "default_language": "string",
  "tags": "string",
  "editors": "string",
  "viewers": "string",
  "submitters": "string",
  "approval_enabled": false,
  "style": "string",
  "response_templates": [],
  "triggers": []
}
```

### `FormVersionSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "form": "string",
  "version": "string",
  "sections": [],
  "translations": "string",
  "status": "typing.Literal['draft', 'published', 'archived']"
}
```

### `InboundPayloadSchema`
```json
{}
```

### `LogicComponentSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "visibility_condition": "typing.Optional[schemas.components.ConditionSchemaStruct]",
  "is_disabled": false,
  "on_change": "string",
  "field_api_call": "typing.Optional[typing.Literal['uhid', 'employee_id', 'form', 'otp', 'custom']]",
  "custom_script": "string",
  "conditional_logic": "string",
  "action_config": "string",
  "triggers": []
}
```

### `LoginRequest`
```json
{
  "identifier": "string",
  "password": "string"
}
```

### `OptionSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "description": "string",
  "is_default": false,
  "is_disabled": false,
  "option_code": "string",
  "option_label": "string",
  "option_value": "string",
  "order": 0,
  "visibility_condition": "typing.Optional[schemas.components.ConditionSchemaStruct]"
}
```

### `PaginatedResult`
```json
{
  "items": [],
  "total": 0,
  "page": 0,
  "page_size": 0,
  "has_next": false
}
```

### `ProjectBlueprintSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "name": "string",
  "description": "string",
  "tags": "string",
  "form_blueprints": "string",
  "hierarchy_definition": "string",
  "is_template": false,
  "meta_data": "string"
}
```

### `ProjectSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "title": "string",
  "description": "string",
  "help_text": "string",
  "organization_id": "string",
  "status": "typing.Literal['draft', 'published', 'archived']",
  "sub_projects": "string",
  "forms": "string",
  "active_version": "string",
  "tags": "string",
  "triggers": []
}
```

### `ProjectVersionSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "project": "string",
  "version": "string",
  "forms": "string",
  "sub_projects": "string",
  "status": "typing.Literal['draft', 'published', 'archived']"
}
```

### `QuestionLogicSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "visibility_condition": "typing.Optional[schemas.components.ConditionSchemaStruct]",
  "is_disabled": false,
  "on_change": "string",
  "field_api_call": "typing.Optional[typing.Literal['uhid', 'employee_id', 'form', 'otp', 'custom']]",
  "custom_script": "string",
  "conditional_logic": "string",
  "action_config": "string",
  "triggers": [],
  "calculated_value": "string"
}
```

### `QuestionSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "label": "string",
  "field_type": "typing.Literal['input', 'textarea', 'number', 'email', 'mobile', 'url', 'password']",
  "help_text": "string",
  "default_value": "string",
  "order": 0,
  "variable_name": "string",
  "is_repeatable": false,
  "repeat_min": 0,
  "repeat_max": 0,
  "keep_last_value": false,
  "is_hidden": false,
  "is_read_only": false,
  "validation": "typing.Optional[schemas.form.ValidationSchema]",
  "logic": "typing.Optional[schemas.form.QuestionLogicSchema]",
  "ui": "typing.Optional[schemas.form.QuestionUISchema]",
  "response_templates": [],
  "options": [],
  "tags": "string",
  "meta_data": "string"
}
```

### `QuestionUISchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "style": "string",
  "visible_header": false,
  "visible_name": "string",
  "placeholder": "string"
}
```

### `ResourceAccessControlSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "resource_type": "typing.Literal['form', 'project', 'submission', 'view']",
  "resource_id": "string",
  "access_level": "typing.Literal['private', 'group', 'organization', 'public']",
  "entries": [],
  "approval_workflow": "string",
  "is_active": false,
  "meta_data": "string",
  "tags": "string"
}
```

### `ResponseTemplateSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "name": "string",
  "description": "string",
  "structure": "string",
  "tags": "string",
  "meta_data": "string"
}
```

### `SectionLogicSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "visibility_condition": "typing.Optional[schemas.components.ConditionSchemaStruct]",
  "is_disabled": false,
  "on_change": "string",
  "field_api_call": "typing.Optional[typing.Literal['uhid', 'employee_id', 'form', 'otp', 'custom']]",
  "custom_script": "string",
  "conditional_logic": "string",
  "action_config": "string",
  "triggers": [],
  "is_repeatable": false,
  "repeat_min": 0,
  "repeat_max": 0
}
```

### `SectionSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "title": "string",
  "description": "string",
  "help_text": "string",
  "order": 0,
  "logic": "typing.Optional[schemas.form.SectionLogicSchema]",
  "ui": "typing.Optional[schemas.form.SectionUISchema]",
  "questions": [],
  "sections": [],
  "response_templates": [],
  "tags": "string",
  "meta_data": "string"
}
```

### `SectionSchemaStruct`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "title": "string",
  "description": "string",
  "help_text": "string",
  "order": 0,
  "logic": "typing.Optional[schemas.form.SectionLogicSchema]",
  "ui": "typing.Optional[schemas.form.SectionUISchema]",
  "questions": [],
  "sections": [],
  "response_templates": [],
  "tags": "string",
  "meta_data": "string"
}
```

### `SectionUISchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "style": "string",
  "visible_header": false,
  "visible_name": "string",
  "layout_type": "typing.Literal['flex', 'grid-cols-2', 'tabbed', 'custom', 'grid-cols-3', 'full-width', 'cards', 'card']"
}
```

### `SoftDeleteBaseSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z"
}
```

### `SystemSettingsSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "env_key": "string",
  "jwt_access_token_expires_minutes": 0,
  "jwt_refresh_token_expires_days": 0,
  "max_failed_login_attempts": 0,
  "account_lock_duration_hours": 0,
  "password_expiration_days": 0,
  "otp_expiration_minutes": 0,
  "max_otp_resends": 0,
  "max_upload_size_mb": 0,
  "allowed_upload_extensions": "string",
  "cache_enabled": false,
  "cache_default_ttl_seconds": 0,
  "cache_form_schema_ttl_seconds": 0,
  "cache_user_session_ttl_seconds": 0,
  "cache_query_result_ttl_seconds": 0,
  "cache_dashboard_widget_ttl_seconds": 0,
  "cache_api_response_ttl_seconds": 0,
  "llm_provider": "string",
  "llm_api_url": "string",
  "llm_model": "string",
  "ollama_api_url": "string",
  "ollama_embedding_model": "string",
  "ollama_pool_size": 0,
  "ollama_pool_timeout_seconds": 0,
  "ollama_connection_timeout_seconds": 0,
  "redis_host": "string",
  "redis_port": 0,
  "redis_db": 0,
  "redis_max_connections": 0,
  "redis_socket_timeout_seconds": 0,
  "cors_enabled": false,
  "debug_mode": false,
  "rate_limit_enabled": false,
  "rate_limit_requests_per_minute": 0,
  "updated_by": "string"
}
```

### `TokenPayload`
```json
{
  "sub": "string",
  "jti": "string",
  "exp": 0,
  "iat": 0,
  "roles": "string"
}
```

### `TokenResponse`
```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "string",
  "expires_in": 0
}
```

### `TriggerSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "name": "string",
  "event_type": "typing.Literal['on_load', 'on_submit', 'on_change', 'on_status_change', 'on_validate', 'on_approval_step', 'on_creation']",
  "condition": "typing.Optional[schemas.components.ConditionSchemaStruct]",
  "action_type": "typing.Literal['webhook', 'email', 'sms', 'notification', 'update_field', 'execute_script', 'hide_show', 'enable_disable', 'validation_error', 'calculation', 'api_call']",
  "action_config": "string",
  "custom_script": "string",
  "is_active": false,
  "order": "string",
  "meta_data": "string"
}
```

### `UIComponentSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "style": "string",
  "visible_header": false,
  "visible_name": "string"
}
```

### `UserGroupSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "name": "string",
  "description": "string",
  "members": "string",
  "owners": "string",
  "organization_id": "string",
  "is_active": false,
  "meta_data": "string",
  "tags": "string"
}
```

### `UserSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "username": "string",
  "email": "string",
  "employee_id": "string",
  "mobile": "string",
  "department": "string",
  "organization_id": "string",
  "user_type": "typing.Literal['employee', 'general']",
  "is_active": false,
  "is_admin": false,
  "is_email_verified": false,
  "roles": [],
  "failed_login_attempts": 0,
  "otp_resend_count": 0,
  "lock_until": "2026-03-02T12:00:00Z",
  "last_login": "2026-03-02T12:00:00Z"
}
```

### `ValidationSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_required": false,
  "logical_operator": "string",
  "required_conditions": [],
  "min_length": 0,
  "max_length": 0,
  "min_value": "string",
  "max_value": "string",
  "min_word_count": 0,
  "max_word_count": 0,
  "regex": "string",
  "error_message": "string",
  "date_min": "string",
  "date_max": "string",
  "disable_past_dates": false,
  "disable_future_dates": false,
  "disable_weekends": false,
  "allowed_file_types": "string",
  "max_files": 0,
  "max_file_size": 0,
  "min_selection": 0,
  "max_selection": 0,
  "is_unique": false,
  "requires_confirmation": false,
  "input_mask": "string",
  "custom_validations": []
}
```

### `VersionSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "form": "string",
  "project": "string",
  "major": 0,
  "minor": 0,
  "patch": 0,
  "version_string": "string"
}
```

### `WorkflowInstanceSchema`
```json
{
  "id": "string",
  "created_at": "2026-03-02T12:00:00Z",
  "updated_at": "2026-03-02T12:00:00Z",
  "is_deleted": false,
  "deleted_at": "2026-03-02T12:00:00Z",
  "organization_id": "string",
  "workflow_definition": "string",
  "resource_type": "typing.Literal['form_response']",
  "resource_id": "string",
  "status": "typing.Literal['pending', 'in_review', 'approved', 'rejected', 'reverted']",
  "current_step_order": 0,
  "history": [],
  "started_at": "2026-03-02T12:00:00Z",
  "completed_at": "2026-03-02T12:00:00Z",
  "meta_data": "string"
}
```
