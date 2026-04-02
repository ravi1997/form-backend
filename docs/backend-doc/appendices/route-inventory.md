# Route Inventory — Complete Route Map

All routes in the RIDP Form Platform backend, organized by blueprint. Base prefix `/form` is shown explicitly.

---

## Auth Blueprint (`/form/api/v1/auth`)

| Method | Full Path | Auth | Rate Limit | Handler |
|--------|-----------|------|-----------|---------|
| POST | `/form/api/v1/auth/register` | None | 5/min | `register` |
| POST | `/form/api/v1/auth/login` | None | 5/min | `login` |
| POST | `/form/api/v1/auth/request-otp` | None | 3/min | `request_otp` |
| POST | `/form/api/v1/auth/refresh` | JWT (refresh) | — | `refresh` |
| POST | `/form/api/v1/auth/logout` | JWT | — | `logout` |
| POST | `/form/api/v1/auth/revoke-all` | JWT | — | `revoke_all` |

---

## User Blueprint (`/form/api/v1/user` and `/form/api/v1/users`)

| Method | Full Path | Auth | Min Role | Handler |
|--------|-----------|------|----------|---------|
| GET | `/form/api/v1/user/profile` | JWT | any | `get_profile` |
| GET | `/form/api/v1/user/status` | JWT | any | `get_profile` |
| POST | `/form/api/v1/user/change-password` | JWT | any | `change_password` |
| GET | `/form/api/v1/user/users` | JWT | admin | `list_users` |
| POST | `/form/api/v1/user/users` | JWT | admin | `create_user` |
| GET | `/form/api/v1/user/users/<user_id>` | JWT | admin | `get_user_by_id` |
| PUT | `/form/api/v1/user/users/<user_id>` | JWT | admin | `update_user_by_id` |
| DELETE | `/form/api/v1/user/users/<user_id>` | JWT | superadmin | `delete_user_by_id` |
| PUT | `/form/api/v1/user/users/<user_id>/roles` | JWT | admin | `update_user_roles` |
| POST | `/form/api/v1/user/users/<user_id>/lock` | JWT | admin | `lock_user_account` |
| POST | `/form/api/v1/user/users/<user_id>/unlock` | JWT | admin | `unlock_user_account` |
| GET | `/form/api/v1/user/security/lock-status/<user_id>` | JWT | admin | `get_lock_status` |

*All above also accessible at `/form/api/v1/users/...` (alias)*

---

## Forms Blueprint — Core (`/form/api/v1/forms`)

| Method | Full Path | Auth | Permission |
|--------|-----------|------|-----------|
| POST | `/form/api/v1/forms/` | JWT | any |
| GET | `/form/api/v1/forms/` | JWT | any |
| GET | `/form/api/v1/forms/<form_id>` | JWT | form:view |
| PUT | `/form/api/v1/forms/<form_id>` | JWT | form:edit |
| DELETE | `/form/api/v1/forms/<form_id>` | JWT | form:delete_form |
| POST | `/form/api/v1/forms/<form_id>/publish` | JWT | form:edit |
| POST | `/form/api/v1/forms/<form_id>/clone` | JWT | form:view |
| GET | `/form/api/v1/forms/templates` | JWT | any |
| GET | `/form/api/v1/forms/templates/<template_id>` | JWT | any |
| POST | `/form/api/v1/forms/import` | JWT | any |
| POST | `/form/api/v1/forms/<form_id>/sections` | JWT | any |
| GET | `/form/api/v1/forms/<form_id>/sections` | JWT | any |
| PUT | `/form/api/v1/forms/<form_id>/sections/<section_id>` | JWT | any |
| DELETE | `/form/api/v1/forms/<form_id>/sections/<section_id>` | JWT | any |
| PUT | `/form/api/v1/forms/<form_id>/sections/reorder` | JWT | any |
| POST | `/form/api/v1/forms/<form_id>/translations` | JWT | form:edit |

---

## Forms Blueprint — Responses

| Method | Full Path | Auth | Permission |
|--------|-----------|------|-----------|
| POST | `/form/api/v1/forms/<form_id>/responses` | JWT | form:submit |
| GET | `/form/api/v1/forms/<form_id>/responses` | JWT | form:view_responses |

---

## Forms Blueprint — Export

| Method | Full Path | Auth | Permission |
|--------|-----------|------|-----------|
| GET | `/form/api/v1/forms/<form_id>/export/csv` | JWT | form:view_responses |
| GET | `/form/api/v1/forms/<form_id>/export/json` | JWT | form:view_responses |
| POST | `/form/api/v1/forms/export/bulk` | JWT | any |
| GET | `/form/api/v1/forms/export/bulk/<job_id>` | JWT | any |
| GET | `/form/api/v1/forms/export/bulk/<job_id>/download` | JWT | any |

---

## Forms Blueprint — Admin Operations

| Method | Full Path | Auth | Min Role |
|--------|-----------|------|----------|
| GET | `/form/api/v1/forms/slug-available` | JWT | any |
| POST | `/form/api/v1/forms/<form_id>/share` | JWT | admin |
| PATCH | `/form/api/v1/forms/<form_id>/archive` | JWT | admin |
| PATCH | `/form/api/v1/forms/<form_id>/restore` | JWT | admin |
| DELETE | `/form/api/v1/forms/<form_id>/responses` | JWT | admin |
| PATCH | `/form/api/v1/forms/<form_id>/toggle-public` | JWT | admin |
| GET | `/form/api/v1/forms/<form_id>/responses/count` | JWT | any |
| GET | `/form/api/v1/forms/<form_id>/responses/last` | JWT | any |
| POST | `/form/api/v1/forms/<form_id>/check-duplicate` | JWT | any |

---

## Forms Blueprint — Summarization

| Method | Full Path | Auth |
|--------|-----------|------|
| POST | `/form/api/v1/forms/<form_id>/summarize` | JWT |
| POST | `/form/api/v1/forms/<form_id>/summarize-stream` | JWT |

---

## Forms Blueprint — Expiry

| Method | Full Path | Auth | Min Role |
|--------|-----------|------|----------|
| PATCH | `/form/api/v1/forms/<form_id>/expire` | JWT | admin |
| GET | `/form/api/v1/forms/expired` | JWT | admin |

---

## Forms Blueprint — Misc (Public + History + Workflow)

| Method | Full Path | Auth |
|--------|-----------|------|
| POST | `/form/api/v1/forms/<form_id>/public-submit` | None |
| GET | `/form/api/v1/forms/<form_id>/history` | JWT |
| GET | `/form/api/v1/forms/<form_id>/next-action` | JWT |

---

## Advanced Responses Blueprint (`/form/api/v1/forms`)

| Method | Full Path | Auth |
|--------|-----------|------|
| GET | `/form/api/v1/forms/fetch/external` | JWT |
| GET | `/form/api/v1/forms/<form_id>/fetch/same` | JWT |
| GET | `/form/api/v1/forms/<form_id>/responses/questions` | JWT |
| GET | `/form/api/v1/forms/<form_id>/responses/meta` | JWT |
| GET | `/form/api/v1/forms/micro-info` | JWT |
| GET | `/form/api/v1/forms/<form_id>/access-control` | JWT |
| POST | `/form/api/v1/forms/<form_id>/access-policy` | JWT |
| PUT | `/form/api/v1/forms/<form_id>/access-policy` | JWT |

---

## Translation Blueprint (`/form/api/v1/forms/translations`)

| Method | Full Path | Auth |
|--------|-----------|------|
| GET | `/form/api/v1/forms/translations` | JWT |
| POST | `/form/api/v1/forms/translations` | JWT |
| GET | `/form/api/v1/forms/translations/languages` | JWT |
| POST | `/form/api/v1/forms/translations/preview` | JWT |
| GET | `/form/api/v1/forms/translations/jobs` | JWT |
| POST | `/form/api/v1/forms/translations/jobs` | JWT |
| GET | `/form/api/v1/forms/translations/jobs/<job_id>` | JWT |
| PATCH | `/form/api/v1/forms/translations/jobs/<job_id>/cancel` | JWT |
| DELETE | `/form/api/v1/forms/translations/jobs/<job_id>` | JWT |
| GET | `/form/api/v1/forms/translations/jobs/<job_id>/content` | JWT |

---

## Library / Custom Fields Blueprint

| Method | Full Path | Auth |
|--------|-----------|------|
| POST | `/form/api/v1/custom-fields/` | JWT |
| GET | `/form/api/v1/custom-fields/` | JWT |
| GET | `/form/api/v1/custom-fields/<field_id>` | JWT |
| PUT | `/form/api/v1/custom-fields/<field_id>` | JWT |
| DELETE | `/form/api/v1/custom-fields/<field_id>` | JWT |

*Same routes also available at `/form/api/v1/templates/`*

---

## AI Blueprint (`/form/api/v1/ai`)

| Method | Full Path | Auth |
|--------|-----------|------|
| GET | `/form/api/v1/ai/health` | None |

---

## NLP Search Blueprint (`/form/api/v1/ai/search`)

| Method | Full Path | Auth |
|--------|-----------|------|
| GET | `/form/api/v1/ai/search/nlp-search` | JWT |
| POST | `/form/api/v1/ai/search/semantic-search` | JWT |
| POST | `/form/api/v1/ai/search/semantic-search/stream` | JWT |
| GET | `/form/api/v1/ai/search/search-stats` | JWT |
| GET | `/form/api/v1/ai/search/query-suggestions` | JWT |
| GET | `/form/api/v1/ai/search/health` | JWT |
| GET | `/form/api/v1/ai/search/search-history` | JWT |
| DELETE | `/form/api/v1/ai/search/search-history` | JWT |
| GET | `/form/api/v1/ai/search/popular-queries` | JWT |

---

## Dashboard Blueprint (`/form/api/v1/dashboards`)

| Method | Full Path | Auth | Permission |
|--------|-----------|------|-----------|
| POST | `/form/api/v1/dashboards/` | JWT | dashboard:create |
| GET | `/form/api/v1/dashboards/<slug>` | JWT | dashboard:view |
| PUT | `/form/api/v1/dashboards/<dashboard_id>` | JWT | dashboard:edit |

---

## Analytics Blueprint (`/form/api/v1/analytics`)

| Method | Full Path | Auth | Min Role |
|--------|-----------|------|----------|
| GET | `/form/api/v1/analytics/dashboard` | JWT | manager |
| GET | `/form/api/v1/analytics/summary` | JWT | admin |
| GET | `/form/api/v1/analytics/trends` | JWT | any |

---

## Webhooks Blueprint (`/form/api/v1/webhooks`)

| Method | Full Path | Auth | Min Role |
|--------|-----------|------|----------|
| POST | `/form/api/v1/webhooks/deliver` | JWT | manager |
| GET | `/form/api/v1/webhooks/<delivery_id>/status` | JWT | any |
| GET | `/form/api/v1/webhooks/<delivery_id>/history` | JWT | any |
| POST | `/form/api/v1/webhooks/<delivery_id>/retry` | JWT | manager |
| POST | `/form/api/v1/webhooks/<delivery_id>/cancel` | JWT | manager |
| POST | `/form/api/v1/webhooks/<webhook_id>/test` | JWT | manager |
| GET | `/form/api/v1/webhooks/<webhook_id>/logs` | JWT | any |

---

## SMS Blueprint (`/form/api/v1/sms`)

| Method | Full Path | Auth | Min Role | Rate Limit |
|--------|-----------|------|----------|-----------|
| POST | `/form/api/v1/sms/single` | JWT | manager | 10/min |
| POST | `/form/api/v1/sms/otp` | JWT | admin | 5/min |
| POST | `/form/api/v1/sms/notify` | JWT | manager | — |
| GET | `/form/api/v1/sms/health` | JWT | any | — |

---

## View Blueprint (`/form/api/v1/view`)

| Method | Full Path | Auth |
|--------|-----------|------|
| GET | `/form/api/v1/view/` | None |
| GET | `/form/api/v1/view/<form_id>` | None |

---

## Health Blueprint (`/form/health`)

| Method | Full Path | Auth |
|--------|-----------|------|
| GET | `/form/health` | None |

---

## Additional Admin Blueprints

| Blueprint | URL Prefix | Notes |
|-----------|-----------|-------|
| `system_settings_bp` | `/form/api/v1/admin/system-settings` | System config management |
| `env_config_bp` | `/form/api/v1/admin/env-config` | Environment variable management |
| `system_bp` | `/form/api/v1/system` | System operations |
| `workflow_bp` | `/form/api/v1/workflows` | Approval workflow management |
| `external_api_bp` | `/form/api/v1/external` | External API integrations |
| `dashboard_settings_bp` | `/form/api/v1/dashboard-settings` | Dashboard settings |
| `permissions_bp` | `/form/api/v1/forms` | Form permissions sub-routes |

---

## Route Count Summary

| Blueprint | Route Count |
|-----------|------------|
| Auth | 6 |
| User | 12 |
| Forms (Core) | 16 |
| Forms (Responses) | 2 |
| Forms (Export) | 5 |
| Forms (Admin/Additional) | 9 |
| Forms (Summarization) | 2 |
| Forms (Expiry) | 2 |
| Forms (Misc) | 3 |
| Advanced Responses | 8 |
| Translation | 10 |
| Library/Custom Fields | 5 (+5 alias) |
| AI | 1 |
| NLP Search | 9 |
| Dashboard | 3 |
| Analytics | 3 |
| Webhooks | 7 |
| SMS | 4 |
| View | 2 |
| Health | 1 |
| **Total (approx)** | **~120+** |
