# Blueprint: Analytics (`analytics_bp`)

## Registration

| Property | Value |
|----------|-------|
| Blueprint name | `analytics_bp` |
| URL prefix | `/form/api/v1/analytics` |
| Module | `routes/v1/analytics_route.py` |

---

## Overview

Provides analytics statistics scoped to the authenticated user's organization. `superadmin` users see system-wide counts; all other roles see only their own organization's data.

---

## Route Reference

### GET /form/api/v1/analytics/dashboard

**Summary:** Compute and return dashboard statistics.

**Authentication:** `@require_roles("admin", "superadmin", "manager")`

**Behavior:**
- Extracts `org_id` and `role` from JWT claims
- If `role == "superadmin"`: queries without org filter (system-wide)
- Otherwise: queries scoped to `organization_id = org_id`
- Counts forms, published forms, and responses for the resolved scope
- Fetches last 5 submissions for the resolved scope

**Response (200):**
```json
{
  "success": true,
  "data": {
    "total_forms": 42,
    "active_forms": 28,
    "total_responses": 1240,
    "recent_activity": [
      {
        "type": "New Submission",
        "details": "Response received for 'Patient Registration Form'",
        "timestamp": "2026-04-02T10:30:00Z",
        "id": "response-uuid"
      }
    ]
  }
}
```

**Note:** `superadmin` users see system-wide totals (all organizations). All other roles see only their organization's data.

**Error handling:** Individual corrupt `FormResponse` records are skipped with a warning log — they do not fail the entire request.

---

### GET /form/api/v1/analytics/summary

**Summary:** Return summary statistics.

**Authentication:** `@require_roles("admin", "superadmin")`

**Behavior:** Same org-scoping logic as `/dashboard`. `superadmin` sees all; others see their org only.

**Response (200):**
```json
{
  "success": true,
  "data": {
    "total_forms": 42,
    "total_responses": 1240
  }
}
```

---

### GET /form/api/v1/analytics/trends

**Summary:** Return analytics trends.

**Authentication:** `@jwt_required()`

**Status:** Stub implementation. Returns empty trends array. Not yet implemented.

**Response (200):**
```json
{
  "success": true,
  "data": { "trends": [] }
}
```

---

## Known Limitations

1. **Trends not implemented** (R-10): The `/trends` endpoint is a stub.

2. **No date range filtering**: Stats are computed over all time. There is no `from_date`/`to_date` parameter.

3. **No caching**: Each request triggers live MongoDB counts. Under heavy load, this could be slow.

---

## Dependencies

- `Form`, `FormResponse` models
- `require_roles` (`utils/security.py`)
- `get_jwt` (Flask-JWT-Extended) — for org_id and role extraction
