# Blueprint: View (`view_bp`)

## Registration

| Property | Value |
|----------|-------|
| Blueprint name | `view_bp` |
| URL prefix | `/form/api/v1/view` |
| Module | `routes/v1/view_route.py` |

---

## Overview

The view blueprint renders HTML pages — it is NOT a JSON API. These routes serve rendered Jinja2 templates for browser-based form viewing. They require no authentication and perform no organization scoping.

**Security note:** Any form ID can be rendered by any user — no authentication, no org isolation. See `risks-and-gaps.md` R-08.

---

## Route Reference

### GET /form/api/v1/view/

**Summary:** Render the login page.

**Authentication:** None

**Behavior:** Returns `render_template("login.html")`. On template error, returns "Login page not found" with 404.

**Response:** HTML page (`text/html`)

---

### GET /form/api/v1/view/`<form_id>`

**Summary:** Render a form for browser display.

**Authentication:** None

**Query parameters:**
- `lang` (optional) — language code. If provided, `apply_translations(form_dict, lang)` is called before rendering.

**Behavior:**
1. Queries `Form.objects.get(id=form_id)` — no `organization_id` filter, no `is_deleted` filter
2. If `lang` is specified, applies translation overlay
3. Normalizes `_id` → `id` in the dict
4. Renders `render_template("view.html", form=form_dict)`

**Response:** HTML page with form content

**Error responses:**
- `"Form not found"` with 404 — plain text (not JSON)
- `"Internal server error"` with 500 — plain text (not JSON)

---

## Limitations

1. **No authentication** — anyone with a form UUID can view the form structure in a browser
2. **No org isolation** — any form from any organization renders if the UUID is known
3. **No `is_deleted` filter** — soft-deleted forms still render
4. **Returns plain text errors** — not JSON, inconsistent with API error format

---

## Dependencies

- `Form` model
- `apply_translations` (`routes/v1/form/helper.py`)
- Jinja2 templates: `login.html`, `view.html` (must exist in Flask template directory)
