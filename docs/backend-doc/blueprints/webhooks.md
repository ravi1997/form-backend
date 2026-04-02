# Blueprint: Webhooks (`webhooks_bp`)

## Registration

| Property | Value |
|----------|-------|
| Blueprint name | `webhooks` |
| URL prefix | `/form/api/v1/webhooks` |
| Module | `routes/v1/webhooks.py` |
| Services used | `WebhookService` |

---

## Overview

The webhook blueprint provides management and delivery endpoints for outbound webhook notifications. Webhooks can be triggered manually, scheduled, retried, and cancelled. All operations require at minimum the `manager` role.

---

## Route Reference

### POST /form/api/v1/webhooks/deliver

**Summary:** Trigger webhook delivery.

**Authentication:** `@require_roles("admin", "superadmin", "manager")`

**Request body:**
```json
{
  "url": "https://target.example.com/webhook",
  "webhook_id": "wh-uuid",
  "form_id": "form-uuid",
  "payload": {
    "event": "form_submitted",
    "data": { "response_id": "resp-uuid" }
  },
  "max_retries": 5,
  "timeout": 10,
  "headers": {
    "X-Custom-Auth": "token123"
  },
  "schedule_for": "2026-04-02T15:00:00Z"
}
```

All of `url`, `webhook_id`, `form_id`, and `payload` are required. Other fields are optional:
- `max_retries` — default 5
- `timeout` — default 10 seconds
- `headers` — additional HTTP headers to include in the webhook request
- `schedule_for` — ISO 8601 datetime; if provided, delivery is scheduled for that time

`schedule_for` validation: if provided but not a valid ISO 8601 string, returns 400.

**Behavior:** Calls `WebhookService.send_webhook()` with all parameters. The `created_by` field is set to `get_jwt_identity()`.

**Response (200):** Result from `WebhookService.send_webhook()` (service-defined shape).

**Audit log:** `Webhook delivery triggered. Form ID: <id>, Webhook ID: <id>, URL: <url>, User: <user>`

---

### GET /form/api/v1/webhooks/`<delivery_id>`/status

**Summary:** View status of a specific delivery.

**Authentication:** `@jwt_required()`

**Behavior:** Calls `WebhookService.get_webhook_status(delivery_id)`. Returns 404 if not found.

**Response (200):** Webhook delivery status document from the service.

---

### GET /form/api/v1/webhooks/`<delivery_id>`/history

**Summary:** View delivery history for a specific webhook delivery.

**Authentication:** `@jwt_required()` (inferred from blueprint pattern)

---

### POST /form/api/v1/webhooks/`<delivery_id>`/retry

**Summary:** Retry a failed webhook delivery.

**Authentication:** `@require_roles("admin", "superadmin", "manager")`

---

### POST /form/api/v1/webhooks/`<delivery_id>`/cancel

**Summary:** Cancel a scheduled webhook delivery.

**Authentication:** `@require_roles("admin", "superadmin", "manager")`

---

### POST /form/api/v1/webhooks/`<webhook_id>`/test

**Summary:** Send a test payload to verify webhook endpoint connectivity.

**Authentication:** `@require_roles("admin", "superadmin", "manager")`

---

### GET /form/api/v1/webhooks/`<webhook_id>`/logs

**Summary:** Retrieve delivery logs for a webhook.

**Authentication:** `@jwt_required()`

---

## Route Summary

| Method | Path | Auth |
|--------|------|------|
| POST | `/webhooks/deliver` | JWT + manager |
| GET | `/webhooks/<delivery_id>/status` | JWT |
| GET | `/webhooks/<delivery_id>/history` | JWT |
| POST | `/webhooks/<delivery_id>/retry` | JWT + manager |
| POST | `/webhooks/<delivery_id>/cancel` | JWT + manager |
| POST | `/webhooks/<webhook_id>/test` | JWT + manager |
| GET | `/webhooks/<webhook_id>/logs` | JWT |

---

## Dependencies

- `WebhookService` (`services/webhook_service.py`) — all webhook operations
- `require_roles` (`utils/security.py`)
- `Flask-Limiter` (imported but limits not shown for all routes)
