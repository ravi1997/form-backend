# Lifecycle Matrices

## 1. Form Lifecycle

```
                    ┌─────────────────┐
                    │      draft      │ ◄──── restore (from archived)
                    └────────┬────────┘
                             │ publish (Celery async)
                             ▼
                    ┌─────────────────┐
                    │    published    │
                    └────────┬────────┘
                        ▲    │ archive
                        │    ▼
                    ┌─────────────────┐
                    │    archived     │
                    └─────────────────┘

(All states) ──── delete ────► is_deleted=True (soft delete, excluded from queries)
```

### State Transitions

| From | To | Trigger | Permission |
|------|----|---------|-----------|
| — | `draft` | `POST /forms/` (create) | JWT (any) |
| `draft` | `published` | `POST /forms/<id>/publish` | form:edit |
| `published` | `archived` | `PATCH /forms/<id>/archive` | admin role |
| `archived` | `draft` | `PATCH /forms/<id>/restore` | admin role |
| Any | `is_deleted=True` | `DELETE /forms/<id>` | form:delete_form |

### State-Dependent Behavior

| State | Submit responses | View form | Appear in list |
|-------|-----------------|-----------|---------------|
| `draft` | No (403 for public) | Yes (with edit perm) | Yes |
| `published` | Yes (if not expired/scheduled) | Yes | Yes |
| `archived` | No (403 for public) | Yes (with edit perm) | Yes (unless filtered) |
| `is_deleted=True` | No | No | No |

---

## 2. Form Response Lifecycle

```
         ┌─────────────────┐
         │    submitted    │ ◄── POST /responses or /public-submit
         └────────┬────────┘
              (no state change mechanism — status is set at creation)
              │
              │ DELETE /forms/<id>/responses (admin, HARD DELETE)
              ▼
         [permanently removed]
```

| Field | Value | Meaning |
|-------|-------|---------|
| `status` | `"submitted"` | Normal completed submission |
| `status` | `"draft"` | Incomplete / in-progress submission |
| `is_deleted` | `False` | Active |
| `submitted_by` | user UUID | Authenticated submission |
| `submitted_by` | `"anonymous"` | Public submission |

---

## 3. JWT Token Lifecycle

```
Login ──────────────────────────────► access_token (short-lived) + refresh_token (long-lived)
         │
         │ JWT_REFRESH_COOKIE_PATH: /form/api/v1/auth/refresh
         ├─ refresh → new access_token + new refresh_token
         │
         │ /auth/logout: JTI added to Redis blocklist
         └─ logout → access_token invalidated

         /auth/revoke-all → all JTIs for user invalidated in Redis
```

### Token States

| State | Meaning |
|-------|---------|
| Valid | Signature OK, not expired, JTI not in blocklist |
| Expired | Past `exp` claim timestamp |
| Revoked | JTI present in Redis blocklist |
| Invalid | Signature mismatch or malformed |

---

## 4. User Account Lifecycle

```
register ──► active (is_active=True, is_deleted=False)
                │
                ├─── failed login attempts ──► lock_account() → locked (lock_until set)
                │         │
                │         └─ time passes or admin unlock ──► unlocked
                │
                ├─── admin: is_active=False ──► inactive (can't login)
                │
                └─── superadmin: DELETE /users/<id> ──► is_deleted=True (soft-deleted)
```

### Login Validation Order

1. Find user by identifier (email, username, employee_id, or mobile)
2. Check `is_active = True`
3. Check `is_deleted = False`
4. Check `is_locked()` (evaluates `lock_until > now`)
5. Verify password hash or OTP
6. On failure: increment `failed_login_attempts`; if threshold reached, call `lock_account()`
7. On success: reset `failed_login_attempts = 0`

---

## 5. Translation Job Lifecycle

```
POST /translations/jobs ──► status: "pending"
         │
         └─ Python thread starts ──► status: "inProgress" (started_at set)
                    │
                    ├─ translating language 1 of N...
                    │    │
                    │    └─ cancel check (job.reload().status == "cancelled") ──► stop
                    │
                    ├─ translating language 2 of N... (progress updated)
                    │
                    └─ all done ──► status: "completed" (completed_at, results set)
                              OR ──► status: "failed" (error_message set)

PATCH /cancel ──► status: "cancelled" (cooperative, not immediate)
DELETE /jobs/<id> ──► hard delete from MongoDB
```

### Job Status Values

| Status | Meaning |
|--------|---------|
| `pending` | Created, thread not yet started |
| `inProgress` | Thread is running translations |
| `completed` | All languages processed successfully |
| `failed` | Fatal error during processing |
| `cancelled` | User cancelled before/during processing |

---

## 6. Bulk Export Job Lifecycle

```
POST /forms/export/bulk ──► status: "pending", Celery task dispatched
         │
         └─ Celery worker picks up ──► status: "processing"
                    │
                    └─ ZIP assembled ──► status: "completed" (file_binary stored)
                              OR ──► status: "failed" (error_message stored)

GET /export/bulk/<job_id>/download ──► returns file_binary as ZIP
```

### Job Status Values

| Status | Meaning |
|--------|---------|
| `pending` | Created, not yet picked up by worker |
| `processing` | Worker actively building ZIP |
| `completed` | ZIP ready for download |
| `failed` | Export failed |

---

## 7. Webhook Delivery Lifecycle

```
POST /webhooks/deliver ──► delivery record created
         │
         └─ WebhookService sends HTTP request to target URL
                    │
                    ├─ success ──► status: "delivered"
                    │
                    └─ failure ──► retry up to max_retries times
                              └─ all retries exhausted ──► status: "failed"

PATCH /cancel ──► cancel scheduled delivery
POST /retry ──► manually retry a failed delivery
```

---

## 8. Form Version Lifecycle

```
Form created ──► no versions (active_version_id: null)
         │
         └─ POST /forms/<id>/publish (Celery task) ──► FormVersion created
                    │                                   resolved_snapshot frozen
                    │                                   active_version_id updated
                    │
                    └─ subsequent publish ──► new FormVersion (version incremented)
                              active_version_id points to latest
                              old versions remain (immutable, queryable)
```

### Version Numbering

- `minor=True, major=False` (default): `1.0.0` → `1.1.0` → `1.2.0`
- `major=True`: `1.2.0` → `2.0.0`
- Version is stored as `version_string` on `FormVersion`

### Snapshot Immutability

The `resolved_snapshot` field on `FormVersion` is written once at publish time and never modified. It contains a complete denormalized copy of the form structure (sections, questions, options) as it existed at the moment of publishing. This is what exports use.
