# Blueprint: View (`view_bp`)

## Registration

| Property | Value |
|----------|-------|
| Blueprint name | `view_bp` |
| URL prefix | `/form/api/v1/view` |
| Module | `routes/v1/view_route.py` |

---

## Overview

The view blueprint renders HTML pages — it is NOT a JSON API. These routes serve rendered Jinja2 templates for browser-based form viewing. No authentication required. Forms must be `is_public = True` to be viewable.

---

## Route Reference

### GET /form/api/v1/view/

**Summary:** Render the login page.

**Authentication:** None

**Behavior:** Returns `render_template("login.html")`. On template error, returns "Login page not found" with 404.

**Response:** HTML page (`text/html`)

---

### GET /form/api/v1/view/`<form_id>`

**Summary:** Render a public form for browser display.

**Authentication:** None

**Query parameters:**
- `lang` (optional) — language code. If provided, `apply_translations(form_dict, lang)` is called before rendering.

**Behavior:**
1. Queries `Form.objects.get(id=form_id)` — no `organization_id` filter
2. Checks `form.is_public` — returns 403 "Form is private or requires authentication" if not public
3. If `lang` is specified, applies translation overlay
4. Normalizes `_id` → `id` in the dict
5. Renders `render_template("view.html", form=form_dict)`

**Response:** HTML page with form content

**Error responses:**
- `403` — Form is private: `"Form is private or requires authentication"` (plain text)
- `"Form not found"` with 404 — plain text (not JSON)
- `"Internal server error"` with 500 — plain text (not JSON)

---

## Remaining Limitations (see `risks-and-gaps.md` R-08)

1. **No `is_deleted` filter** — soft-deleted forms still render if `is_public = True`
2. **No org isolation** — cross-tenant form existence can be inferred via 404 vs 403 response distinction
3. **Returns plain text errors** — not JSON, inconsistent with API error format

---

## Dependencies

- `Form` model
- `apply_translations` (`routes/v1/form/helper.py`)
- Jinja2 templates: `login.html`, `view.html` (must exist in Flask template directory)
