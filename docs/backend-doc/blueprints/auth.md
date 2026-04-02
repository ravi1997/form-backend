# Blueprint: Auth (`auth_bp`)

## Registration

| Property | Value |
|----------|-------|
| Blueprint name | `auth_bp` |
| URL prefix | `/form/api/v1/auth` |
| Module | `routes/v1/auth_route.py` |
| Services used | `AuthService`, `UserService` |

---

## Overview

The auth blueprint handles all authentication operations: user registration, password login, OTP-based login, token refresh, logout, and session revocation. All tokens are issued as HttpOnly cookies AND returned in the response body (dual-mode). Rate limiting is applied to all write operations.

---

## Route Reference

### POST /form/api/v1/auth/register

**Summary:** Register a new user account.

**Authentication:** None required

**Rate limit:** 5 per minute

**Request body:**
```json
{
  "email": "user@example.com",
  "username": "john_doe",
  "password": "secret123",
  "mobile": "9876543210"
}
```
Schema: `UserCreateSchema` (Pydantic)

**Success response (201):**
```json
{
  "success": true,
  "data": {
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "username": "john_doe",
      "roles": ["user"]
    }
  },
  "message": "User registered successfully"
}
```

**Error responses:**
- `400` — Validation error or user already exists (e.g., duplicate email)

**Audit log:** `AUDIT: New user registered: <username> (ID: <id>)`

---

### POST /form/api/v1/auth/login

**Summary:** Authenticate via password or OTP and issue JWT tokens.

**Authentication:** None required

**Rate limit:** 5 per minute

**Request body (password login):**
```json
{
  "email": "user@example.com",
  "password": "secret123"
}
```

Identifier can be: `email`, `username`, `employee_id`, or `identifier`. At least one must be present with `password`.

**Request body (OTP login):**
```json
{
  "mobile": "9876543210",
  "otp": "123456"
}
```

**Behavior:**
1. If `password` is present: calls `user_service.authenticate_employee(identifier, password)`
2. If `mobile + otp` are present: calls `user_service.verify_otp_login(mobile, otp)`
3. Issues tokens via `auth_service.generate_tokens(user_doc)`
4. Sets HttpOnly cookies (`set_access_cookies`, `set_refresh_cookies`)
5. Returns tokens in response body AND as cookies

**Success response (200):**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "user": { "id": "uuid", "email": "...", "roles": ["user"] }
  },
  "message": "Login successful"
}
```

**Error responses:**
- `400` — Invalid JSON payload or missing required fields
- `401` — `UnauthorizedError` re-raised (invalid credentials, locked account, inactive user)
- `500` — Unexpected server error during login workflow

**Audit log:** `AUDIT: Login successful for user id=<id>`

---

### POST /form/api/v1/auth/request-otp

**Summary:** Generate and send an OTP to the given mobile or email.

**Authentication:** None required

**Rate limit:** 3 per minute

**Request body:**
```json
{ "mobile": "9876543210" }
```
OR
```json
{ "email": "user@example.com" }
```

Either `mobile` or `email` must be provided. The system sends OTP to the provided identifier and stores it in Redis.

**Success response (200):**
```json
{
  "success": true,
  "message": "OTP sent successfully"
}
```

**Error responses:**
- `400` — Neither mobile nor email provided
- `403` — `UnauthorizedError` (user not found or inactive)
- `500` — OTP generation failed (provider error)

**Audit log:** `AUDIT: OTP requested for identifier: <identifier>`

---

### POST /form/api/v1/auth/refresh

**Summary:** Issue a new access token using a valid refresh token.

**Authentication:** `@jwt_required(refresh=True)` — requires a valid refresh token

**Request:** No body required. Token via `Authorization: Bearer <refresh_token>` header or refresh cookie.

When using cookies, must include `X-CSRF-TOKEN-REFRESH` header.

**Behavior:**
1. Extracts user ID from refresh token identity
2. Verifies user exists, is active, and is not deleted
3. Generates new token pair via `auth_service.generate_tokens(user)`
4. Sets new cookies and returns tokens in body

**Success response (200):**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ..."
  },
  "message": "Token refreshed"
}
```

**Error responses:**
- `404` — User not found or suspended (returns raw `jsonify`, not `success_response`)
- `401` — Token refresh failed (expired or invalid refresh token)

**Audit log:** `AUDIT: Token refreshed for user id=<id>`

---

### POST /form/api/v1/auth/logout

**Summary:** Revoke the current JWT session.

**Authentication:** `@jwt_required()` — requires a valid access token

**Request:** No body required.

**Behavior:**
1. Calls `auth_service.revoke_token_payload(get_jwt())` — adds JTI to Redis blocklist
2. Calls `unset_jwt_cookies(resp)` — clears cookies

**Success response (200):**
```json
{
  "success": true,
  "message": "Successfully logged out"
}
```

**Error responses:**
- `500` — Logout failed (Redis unavailable)

**Audit log:** `AUDIT: Logout successful for user id=<id>`

---

### POST /form/api/v1/auth/revoke-all

**Summary:** Revoke all active JWT sessions for the authenticated user.

**Authentication:** `@jwt_required()` — requires a valid access token

**Request:** No body required.

**Behavior:**
1. Calls `auth_service.revoke_all_user_sessions(user_id)` — invalidates all JTIs in Redis
2. Clears cookies

**Success response (200):**
```json
{
  "success": true,
  "message": "All sessions revoked successfully"
}
```

**Error responses:**
- `500` — Failed to revoke all sessions

**Audit log:** `AUDIT: All sessions revoked for user id=<id>`

---

## Rate Limit Summary

| Route | Limit |
|-------|-------|
| `/register` | 5 per minute |
| `/login` | 5 per minute |
| `/request-otp` | 3 per minute |
| `/refresh` | Not rate-limited |
| `/logout` | Not rate-limited |
| `/revoke-all` | Not rate-limited |

---

## Dependencies

- `AuthService` (`services/auth_service.py`) — token generation, blocklist, revocation
- `UserService` (`services/user_service.py`) — authentication, OTP management
- `Flask-JWT-Extended` — JWT validation, cookie management
- `Redis` (session DB) — OTP storage, JWT blocklist
- `Flask-Limiter` — rate limiting

---

## Security Notes

- `UnauthorizedError` and `ValidationError` are re-raised (not caught) in the login handler — they propagate to the global error handler which returns the appropriate 401/400 status
- All unexpected exceptions in login return a generic "Authentication failed" message to avoid information leakage
- Password is never logged — PII filter masks the field
- Cookie `Secure` flag is `True` in production (`JWT_COOKIE_SECURE = not DEBUG`)
