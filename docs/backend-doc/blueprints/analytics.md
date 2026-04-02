# Blueprint: Analytics (`analytics_bp`)

## Registration

| Property | Value |
|----------|-------|
| Blueprint name | `analytics_bp` |
| URL prefix | `/form/api/v1/analytics` |
| Module | `routes/v1/analytics_route.py` |

---

## Overview

Provides system-wide analytics statistics. All routes are restricted to privileged users. **Critical limitation:** Queries run without tenant (`organization_id`) scoping — they return system-wide counts across all organizations. This is documented as a known risk (R-04).

---

## Route Reference

### GET /form/api/v1/analytics/dashboard

**Summary:** Compute and return system-wide dashboard statistics.

**Authentication:** `@require_roles("admin", "superadmin", "manager")`

**Behavior:**
- Counts `Form.objects()` — all forms, all orgs (no filter)
- Counts `Form.objects(status="published")` — all published forms
- Counts `FormResponse.objects(is_deleted=False)` — all responses
- Fetches last 5 submissions across the entire system
- For each recent submission, safely resolves the associated form title

**Response (200):**
```json
{
  "success": true,
  "data": {
    "total_forms": 520,
    "active_forms": 312,
    "total_responses": 48320,
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

**Warning:** `total_forms`, `active_forms`, and `total_responses` are system-wide counts, NOT scoped to the authenticated user's organization. An admin of Organization A sees counts from all organizations.

**Error handling:** Individual corrupt `FormResponse` records are skipped with a warning log — they do not fail the entire request.

---

### GET /form/api/v1/analytics/summary

**Summary:** Return organization-wide summary statistics.

**Authentication:** `@require_roles("admin", "superadmin")`

**Behavior:** Same as dashboard stats but returns only aggregate counts. Same unscoped query issue.

**Response (200):**
```json
{
  "success": true,
  "data": {
    "total_forms": 520,
    "total_responses": 48320
  }
}
```

---

### GET /form/api/v1/analytics/trends

**Summary:** Return analytics trends.

**Authentication:** `@jwt_required()`

**Status:** Stub implementation. Returns empty trends array.

**Response (200):**
```json
{
  "success": true,
  "data": { "trends": [] }
}
```

---

## Known Limitations

1. **No tenant isolation** (R-04): All three endpoints query without `organization_id`. This is an information disclosure vulnerability — admins from any org see system-wide totals.

2. **Trends not implemented** (R-13): The `/trends` endpoint is a stub.

3. **No date range filtering**: Stats are always computed over all time. There is no `from_date`/`to_date` parameter.

4. **No caching**: Each request triggers live MongoDB queries. Under heavy load, `total_responses` counts could be slow.

---

## Dependencies

- `Form`, `FormResponse` models
- `require_roles` (`utils/security.py`)
