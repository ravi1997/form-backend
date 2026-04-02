# Legacy Route Mapping & Alias Reference

This document maps alias routes to their canonical counterparts, and documents known route prefix duplications.

---

## 1. Dual-Registered Blueprints

### User Blueprint

The `user_bp` blueprint is registered at two URL prefixes:

| Alias Path | Canonical Path | Note |
|-----------|---------------|------|
| `/form/api/v1/users/profile` | `/form/api/v1/user/profile` | Same handler |
| `/form/api/v1/users/status` | `/form/api/v1/user/status` | Same handler |
| `/form/api/v1/users/change-password` | `/form/api/v1/user/change-password` | Same handler |
| `/form/api/v1/users/users` | `/form/api/v1/user/users` | Same handler |
| `/form/api/v1/users/users/<id>` | `/form/api/v1/user/users/<id>` | Same handler |
| `/form/api/v1/users/users/<id>/roles` | `/form/api/v1/user/users/<id>/roles` | Same handler |
| `/form/api/v1/users/users/<id>/lock` | `/form/api/v1/user/users/<id>/lock` | Same handler |
| `/form/api/v1/users/users/<id>/unlock` | `/form/api/v1/user/users/<id>/unlock` | Same handler |
| `/form/api/v1/users/security/lock-status/<id>` | `/form/api/v1/user/security/lock-status/<id>` | Same handler |

**Recommendation:** Use `/form/api/v1/user/` as canonical. The `/users/` alias may be removed in a future cleanup.

---

### Library / Custom Fields Blueprint

The `library_bp` blueprint is registered at two URL prefixes:

| Alias Path | Canonical Path | Note |
|-----------|---------------|------|
| `/form/api/v1/templates/` | `/form/api/v1/custom-fields/` | Same blueprint |
| `/form/api/v1/templates/<id>` | `/form/api/v1/custom-fields/<id>` | Same blueprint |

**Note:** "templates" in this context refers to reusable custom field definitions, NOT form templates (which are at `/forms/templates`). This naming conflict is a known source of confusion.

---

## 2. Blueprint URL Prefix Conflicts

These blueprints define a `url_prefix` in their `Blueprint()` constructor which conflicts with the registration-time prefix:

### `sms_bp`

```python
# Constructor (in sms_route.py):
sms_bp = Blueprint("sms", __name__, url_prefix="/api/v1/sms")

# Registration (in routes/__init__.py):
app.register_blueprint(sms_bp, url_prefix=f"{base_prefix}/api/v1/sms")
# Actual prefix: /form/api/v1/sms  (registration prefix wins)
```

The constructor prefix `/api/v1/sms` is overridden by the registration prefix. Routes are served at `/form/api/v1/sms/`.

### `nlp_search_bp`

```python
# Constructor (in nlp_search.py):
nlp_search_bp = Blueprint("nlp_search", __name__, url_prefix="/ai/search")

# Registration (in routes/__init__.py):
app.register_blueprint(nlp_search_bp, url_prefix=f"{base_prefix}/api/v1/ai/search")
# Actual prefix: /form/api/v1/ai/search  (registration prefix wins)
```

---

## 3. Blueprint URL Prefix Overlap

The following blueprints share the URL prefix `/form/api/v1/forms`:

| Blueprint | Routes |
|-----------|--------|
| `form_bp` | Core CRUD, responses, export, additional, summarization, expiry, misc |
| `advanced_responses_bp` | fetch/external, fetch/same, responses/questions, responses/meta, micro-info, access-control, access-policy |
| `permissions_bp` | Form permissions sub-routes |
| `translation_bp` | `/form/api/v1/forms/translations` (sub-prefix) |

Flask can handle multiple blueprints at the same URL prefix. Route conflicts are resolved by registration order — the first matching route is used. Verify actual behavior in the running app's route map.

---

## 4. Known Route Path Ambiguities

### Forms and Advanced Responses at Same Prefix

Both `form_bp` and `advanced_responses_bp` are registered at `/form/api/v1/forms`. They do not conflict because their route paths are distinct. However, this makes it non-obvious which blueprint handles which route.

Route ownership:
- `GET /forms/<form_id>/responses` — `form_bp` (responses.py)
- `GET /forms/<form_id>/responses/questions` — `advanced_responses_bp`
- `GET /forms/<form_id>/responses/meta` — `advanced_responses_bp`
- `GET /forms/<form_id>/responses/count` — `form_bp` (additional.py)
- `GET /forms/<form_id>/responses/last` — `form_bp` (additional.py)

### Translation and Form-Level Translation

Two distinct translation endpoints exist:

| Path | Blueprint | Purpose |
|------|-----------|---------|
| `GET /forms/translations?form_id=<id>` | `translation_bp` | Get stored AI translations from FormVersion |
| `POST /forms/<form_id>/translations` | `form_bp` (form.py) | Manually update form.translations dict |

These are different endpoints serving different translation data stores.

---

## 5. Swagger Documentation Notes

The Swagger UI at `/form/docs` and spec at `/form/apispec_1.json` cover all routes decorated with `@swag_from()`. Some routes in older modules may not have Swagger decorators and will not appear in the UI. Use the running app's `/form/docs` as the definitive source, not this documentation.

The Swagger spec is registered at:
- UI: `/form/docs`
- Static: `/form/flasgger_static`
- Spec JSON: `/form/apispec_1.json`
