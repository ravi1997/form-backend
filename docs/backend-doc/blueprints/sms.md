# Blueprint: SMS (`sms_bp`)

## Registration

| Property | Value |
|----------|-------|
| Blueprint name | `sms` |
| URL prefix | `/form/api/v1/sms` |
| Module | `routes/v1/sms_route.py` |
| Services used | `ExternalSMSService` (via `get_sms_service()`) |

**Note:** The `sms_bp` Blueprint constructor defines `url_prefix="/api/v1/sms"`. This constructor prefix is overridden by the registration prefix `/form/api/v1/sms` in `routes/__init__.py`. Actual routes are served at `/form/api/v1/sms/`.

---

## Overview

Wraps an external SMS API (AIIMS SMS provider) for sending single SMS messages, OTPs, and notifications. All endpoints are protected by JWT and rate-limited. SMS sending is restricted to privileged roles to prevent resource abuse.

---

## Route Reference

### POST /form/api/v1/sms/single

**Summary:** Send a single SMS message via the external provider.

**Authentication:** `@require_roles("admin", "superadmin", "manager")`

**Rate limit:** 10 per minute

**Request body:**
```json
{
  "mobile": "9876543210",
  "message": "Your appointment is confirmed for 10 AM tomorrow."
}
```

Both `mobile` and `message` are required.

**Behavior:**
1. Gets SMS service via `get_sms_service()` (instantiates with configured API URL and token)
2. Calls `sms_service.send_sms(mobile, message)`
3. Returns success with `message_id` and `status_code` from provider
4. On failure, returns error with provider's error message and status code

**Success response (200):**
```json
{
  "success": true,
  "message_id": "provider-message-id",
  "status_code": 200
}
```

**Failure response:**
```json
{
  "success": false,
  "error": "Provider error message",
  "status_code": 500
}
```

**Audit log:** `SMS sent successfully to <mobile> by user <user_id>`

---

### POST /form/api/v1/sms/otp

**Summary:** Manually send an OTP via the external provider. Admin tool.

**Authentication:** `@require_roles("admin", "superadmin")`

**Rate limit:** 5 per minute

**Request body:**
```json
{
  "mobile": "9876543210",
  "otp": "123456"
}
```

Both `mobile` and `otp` are required.

**Note:** This is a manual admin tool for sending pre-generated OTPs. The OTP flow for users (request + verify) is handled by `auth_route.py`. This route bypasses the OTP generation logic and sends a raw OTP directly.

**Success response (200):**
```json
{
  "success": true,
  "message_id": "provider-message-id"
}
```

**Audit log:** `OTP sent successfully to <mobile> by user <user_id>`

---

### POST /form/api/v1/sms/notify

**Summary:** Send a notification SMS with title and body.

**Authentication:** `@require_roles("admin", "superadmin", "manager")`

**Request body:**
```json
{
  "mobile": "9876543210",
  "title": "Appointment Reminder",
  "body": "Please complete your pre-admission form before your appointment."
}
```

`mobile` and `body` are required. `title` is optional (defaults to `""`).

**Behavior:** Calls `sms_service.send_notification(mobile, title, body)`.

**Success response (200):**
```json
{
  "success": true,
  "message_id": "provider-message-id"
}
```

**Audit log:** `Notification sent successfully to <mobile> by user <user_id>`

---

### GET /form/api/v1/sms/health

**Summary:** Verify SMS provider connectivity and configuration.

**Authentication:** `@jwt_required()` (any authenticated user)

**Behavior:**
- Checks if `sms_service.api_url` and `sms_service.api_token` are configured
- Returns `healthy` if both are present; `unhealthy` otherwise
- Does NOT make an actual request to the SMS provider

**Response (200):**
```json
{
  "status": "healthy",
  "service": "external_sms"
}
```

**Response (503) — not configured:**
```json
{
  "status": "unhealthy",
  "error": "API not configured"
}
```

---

## Rate Limit Summary

| Route | Limit |
|-------|-------|
| `/sms/single` | 10 per minute |
| `/sms/otp` | 5 per minute |
| `/sms/notify` | Not explicitly limited (inherits global) |
| `/sms/health` | Not rate-limited |

---

## Dependencies

- `ExternalSMSService` (`services/external_sms_service.py`) — AIIMS SMS API wrapper
- `get_sms_service()` — factory function that returns configured service instance
- `require_roles` (`utils/security.py`)
- `Flask-Limiter`

---

## Service Configuration

The SMS service is configured via environment variables (likely `SMS_API_URL` and `SMS_API_TOKEN`). If these are not set, the `/health` endpoint returns `unhealthy`. All send operations will fail if the service is not configured.
