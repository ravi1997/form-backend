# Blueprint: User (`user_bp`)

## Registration

| Property | Value |
|----------|-------|
| Blueprint name | `user_bp` |
| URL prefix (canonical) | `/form/api/v1/user` |
| URL prefix (alias) | `/form/api/v1/users` (registered as `user_bp_plural`) |
| Module | `routes/v1/user_route.py` |
| Services used | `UserService` |

**Note:** Both `/user` and `/users` prefixes are active and serve identical routes. Use `/form/api/v1/user/` as canonical. The `/users` alias exists for backwards compatibility.

---

## Overview

The user blueprint handles self-service operations for authenticated users (profile, password change) and administrative user management for admins and superadmins. It is divided into two logical sections:

1. **Self-service** — any authenticated user
2. **Administrative CRUD** — requires `admin` or `superadmin` role
3. **Account security** — lock/unlock/status (requires `admin` or `superadmin`)

---

## Route Reference

### GET /form/api/v1/user/profile

**Summary:** Return the currently authenticated user's profile.

**Authentication:** `@jwt_required()`

**Also available at:** `GET /form/api/v1/user/status`

**Response (200):**
```json
{
  "success": true,
  "data": {
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "username": "john_doe",
      "mobile": "9876543210",
      "employee_id": "EMP001",
      "roles": ["user"],
      "organization_id": "org-uuid",
      "is_active": true,
      "is_admin": false
    }
  }
}
```

Uses `UserOut` Pydantic schema — excludes password hash and internal flags.

---

### POST /form/api/v1/user/change-password

**Summary:** Securely change the current user's password.

**Authentication:** `@jwt_required()`

**Rate limit:** 3 per hour

**Request body:**
```json
{
  "current_password": "old_secret",
  "new_password": "new_secret123"
}
```

**Behavior:**
1. Checks `current_user.check_password(current_pw)` — raises `ValidationError` if wrong
2. Calls `current_user.set_password(new_pw)` — bcrypt hashes the new password
3. Saves the user document

**Success response (200):**
```json
{
  "success": true,
  "message": "Password changed successfully"
}
```

**Error responses:**
- `400` — Incorrect current password (ValidationError re-raised → global handler)
- `500` — Unexpected error during save (re-raised)

**Audit log:** `Password changed successfully for user <id>`

---

### GET /form/api/v1/user/users

**Summary:** List all registered users (paginated). Admin only.

**Authentication:** `@require_roles("admin", "superadmin")`

**Query parameters:**
- `page` (int, default: 1)
- `page_size` (int, default: 20)

**Response (200):**
```json
{
  "success": true,
  "data": {
    "items": [ { UserOut }, ... ],
    "total": 150,
    "page": 1,
    "page_size": 20,
    "total_pages": 8
  }
}
```

**Error responses:**
- `500` — Failed to list users

---

### GET /form/api/v1/user/users/`<user_id>`

**Summary:** Fetch details of a specific user. Admin only.

**Authentication:** `@require_roles("admin", "superadmin")`

**Path parameters:** `user_id` — UUID of the target user

**Response (200):**
```json
{
  "success": true,
  "data": { UserOut }
}
```

**Error responses:**
- `404` — `NotFoundError` re-raised
- `500` — Failed to fetch user

---

### POST /form/api/v1/user/users

**Summary:** Provision a new user account. Admin only.

**Authentication:** `@require_roles("admin", "superadmin")`

**Request body:** (Same schema as self-registration, `UserCreateSchema`)
```json
{
  "email": "newuser@example.com",
  "username": "new_user",
  "password": "pass123",
  "roles": ["user"],
  "organization_id": "org-uuid"
}
```

**Success response (201):**
```json
{
  "success": true,
  "data": { "user": { UserOut } },
  "message": "User created"
}
```

**Error responses:**
- `400` — Validation error or duplicate user

**Audit log:** `User <id> created by admin <admin_id>`

---

### PUT /form/api/v1/user/users/`<user_id>`

**Summary:** Update user attributes. Admin only.

**Authentication:** `@require_roles("admin", "superadmin")`

**Request body:** (`UserUpdateSchema` — all fields optional)
```json
{
  "email": "updated@example.com",
  "is_active": false
}
```

**Response (200):**
```json
{
  "success": true,
  "data": { UserOut }
}
```

**Error responses:**
- `400` — Validation or update error

**Audit log:** `User <user_id> updated by admin <admin_id>`

---

### DELETE /form/api/v1/user/users/`<user_id>`

**Summary:** Soft-delete a user account. Superadmin only.

**Authentication:** `@require_roles("superadmin")` — only superadmin can delete

**Behavior:** Sets `is_deleted = True` on the user document. The user can no longer log in.

**Response (200):**
```json
{
  "success": true,
  "message": "User account deactivated"
}
```

**Error responses:**
- Unexpected exceptions are re-raised (caught by global error handler)

**Audit log:** `User <user_id> deactivated by superadmin <admin_id>`

---

### PUT /form/api/v1/user/users/`<user_id>`/roles

**Summary:** Update user roles. Admin only.

**Authentication:** `@require_roles("admin", "superadmin")`

**Request body:**
```json
{ "roles": ["admin", "manager"] }
```

**Behavior:**
- Replaces the user's entire `roles` list
- If `admin` or `superadmin` is in the new roles, also sets `is_admin = True`
- Old roles are overwritten, not merged

**Response (200):**
```json
{
  "success": true,
  "data": { UserOut },
  "message": "Roles updated"
}
```

**Error responses:**
- `400` — `roles` field missing from request body
- `404` — User not found (`NotFoundError` raised)
- `400` — Any other error

**Audit log:** `Roles for user <id> updated from [old] to [new] by admin <admin_id>`

---

### POST /form/api/v1/user/users/`<user_id>`/lock

**Summary:** Manually lock a user account. Admin only.

**Authentication:** `@require_roles("admin", "superadmin")`

**Behavior:** Calls `user.lock_account()` method on the User model, which sets `is_locked` flag and `lock_until` timestamp.

**Response (200):**
```json
{
  "success": true,
  "message": "User <user_id> account locked"
}
```

**Error responses:**
- `404` — `NotFoundError` raised
- Other exceptions re-raised

**Audit log:** `User <user_id> account manually locked by admin <admin_id>`

---

### POST /form/api/v1/user/users/`<user_id>`/unlock

**Summary:** Manually unlock a user account. Admin only.

**Authentication:** `@require_roles("admin", "superadmin")`

**Behavior:** Calls `user.unlock_account()` — clears lock flags and resets failed attempt counter.

**Response (200):**
```json
{
  "success": true,
  "message": "User <user_id> account unlocked"
}
```

**Audit log:** `User <user_id> account manually unlocked by admin <admin_id>`

---

### GET /form/api/v1/user/security/lock-status/`<user_id>`

**Summary:** Get account lock status for a specific user. Admin only.

**Authentication:** `@require_roles("admin", "superadmin")`

**Response (200):**
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

`lock_until` is `null` if the account is not locked.

**Error responses:**
- `404` — User not found (re-raised)
- Other exceptions re-raised

---

## Route Summary

| Method | Path | Auth | Min Role |
|--------|------|------|----------|
| GET | `/user/profile` | JWT | any |
| GET | `/user/status` | JWT | any |
| POST | `/user/change-password` | JWT | any |
| GET | `/user/users` | JWT | admin |
| POST | `/user/users` | JWT | admin |
| GET | `/user/users/<id>` | JWT | admin |
| PUT | `/user/users/<id>` | JWT | admin |
| DELETE | `/user/users/<id>` | JWT | superadmin |
| PUT | `/user/users/<id>/roles` | JWT | admin |
| POST | `/user/users/<id>/lock` | JWT | admin |
| POST | `/user/users/<id>/unlock` | JWT | admin |
| GET | `/user/security/lock-status/<id>` | JWT | admin |

---

## Dependencies

- `UserService` (`services/user_service.py`) — all user CRUD operations
- `UserOut`, `UserCreateSchema`, `UserUpdateSchema` (Pydantic schemas in `schemas/user.py`)
- `require_roles` (`utils/security.py`)
- `Flask-JWT-Extended` (`current_user`, `get_jwt_identity`)
