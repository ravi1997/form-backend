# Blueprint: Dashboard (`dashboard_bp`)

## Registration

| Property | Value |
|----------|-------|
| Blueprint name | `dashboard` |
| URL prefix | `/form/api/v1/dashboards` |
| Module | `routes/v1/dashboard_route.py` |
| Services used | `DashboardService` |

---

## Overview

The dashboard blueprint manages configurable dashboards with live data widgets. Dashboards contain widgets that query `FormResponse` data using MongoDB aggregation pipelines and return resolved data directly in the dashboard GET response. Each dashboard is identified by a slug (for GET) or ID (for PUT).

**Known risk:** Widget data aggregation does not include `organization_id` in the match query. See `risks-and-gaps.md` R-03.

---

## Route Reference

### POST /form/api/v1/dashboards/

**Summary:** Create a new dashboard configuration.

**Authentication:** `@jwt_required()` + `@require_permission("dashboard", "create")`

**Request body:**
```json
{
  "title": "Patient Overview",
  "slug": "patient-overview",
  "widgets": [
    {
      "title": "Total Submissions",
      "type": "counter",
      "form_id": "form-uuid"
    },
    {
      "title": "Age Distribution",
      "type": "chart_bar",
      "form_id": "form-uuid",
      "group_by_field": "age_group",
      "aggregate_field": null,
      "calculation_type": "count"
    }
  ]
}
```

Schema: `DashboardCreateSchema`

**`created_by`** is set to `get_jwt_identity()`. **`organization_id`** is set to `get_jwt().get("org_id")`.

**Response (201):**
```json
{
  "success": true,
  "data": { dashboard schema dump },
  "message": "Dashboard created"
}
```

**Audit log:** `Dashboard created: ID=<id>, Title='<title>', CreatedBy=<user>, OrgID=<org>`

---

### GET /form/api/v1/dashboards/`<slug>`

**Summary:** Get dashboard details AND resolve live widget data.

**Authentication:** `@jwt_required()` + `@require_permission("dashboard", "view")`

**Path parameter:** `slug` — the dashboard's unique slug string

**Behavior:**
1. Fetches dashboard from `DashboardService.get_by_slug(slug, organization_id=org_id)`
2. For each widget in the dashboard, calls `resolve_widget_data(widget, org_id)`
3. Returns dashboard config with `widgets` array containing both config and resolved data

**Widget data resolution (`resolve_widget_data`):**

The `resolve_widget_data` function runs MongoDB aggregation based on widget type:

| Widget type | Resolution method |
|------------|------------------|
| `chart_bar`, `chart_pie`, `chart_line` | `$group` aggregation by `group_by_field`, with sum/avg/max/min/count on `aggregate_field` |
| `counter`, `kpi` | `.count()` on matching responses |
| `table`, `list_view` | `.limit(config.limit).only("id", "data", "submitted_at")` |
| Other | `data: null` |

**Widget match query:**
```python
match_query = {
    "form": widget.form_id,
    "is_deleted": False
}
```

**Security gap:** `organization_id` is NOT included in `match_query` despite `org_id` being available. See R-03.

Optional widget filters: If `widget.filters` is set, each filter key-value is added as `data.<key> = value` to the match query.

**Response (200):**
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "title": "Patient Overview",
    "slug": "patient-overview",
    "organization_id": "org-uuid",
    "widgets": [
      {
        "title": "Total Submissions",
        "type": "counter",
        "form_id": "form-uuid",
        "data": 247
      },
      {
        "title": "Age Distribution",
        "type": "chart_bar",
        "form_id": "form-uuid",
        "data": {
          "labels": ["18-30", "31-50", "51+"],
          "values": [45, 120, 82]
        }
      }
    ]
  }
}
```

If a widget aggregation fails, its `data` becomes `{"error": "Aggregation failure"}`.

**Error responses:**
- `404` — Dashboard not found
- `500` — Failed to load dashboard data

---

### PUT /form/api/v1/dashboards/`<dashboard_id>`

**Summary:** Update a dashboard's configuration.

**Authentication:** `@jwt_required()` + `@require_permission("dashboard", "edit")`

**Path parameter:** `dashboard_id` — UUID of the dashboard

**Request body:** (`DashboardUpdateSchema` — all fields optional)
```json
{
  "title": "Updated Title",
  "widgets": [ ... ]
}
```

**Behavior:** Requires `org_id` from JWT claims (400 if missing). Delegates to `DashboardService.update(dashboard_id, schema, organization_id=org_id)`.

**Response (200):**
```json
{
  "success": true,
  "data": { updated dashboard schema dump },
  "message": "Dashboard updated"
}
```

**Audit log:** `Dashboard updated: ID=<id>, Title='<title>', UpdatedBy=<user>, OrgID=<org>`

---

## Widget Schema

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Display name |
| `type` | string | `chart_bar`, `chart_pie`, `chart_line`, `counter`, `kpi`, `table`, `list_view` |
| `form_id` | UUID | Form to query responses from |
| `group_by_field` | string | Field path in `data` to group by (for charts) |
| `aggregate_field` | string | Field path to aggregate (sum/avg/etc.) |
| `calculation_type` | string | `sum`, `average`, `max`, `min`, `count` |
| `filters` | dict | Additional `data.<key>: value` filters |
| `config` | dict | Widget-specific config (e.g., `limit` for table widgets) |

---

## Dependencies

- `DashboardService` (`services/dashboard_service.py`)
- `DashboardCreateSchema`, `DashboardUpdateSchema`, `WidgetSchema` (Pydantic)
- `FormResponse` model — queried directly in `resolve_widget_data`
- `require_permission` (`utils/security_helpers.py`)
