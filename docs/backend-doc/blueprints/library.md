# Blueprint: Library / Custom Fields (`library_bp`)

## Registration

| Property | Value |
|----------|-------|
| Blueprint name | `library_bp` |
| URL prefix (canonical) | `/form/api/v1/custom-fields` |
| URL prefix (alias) | `/form/api/v1/templates` (registered as `form_templates`) |
| Module | `routes/v1/form/library.py` |

**Note:** The same blueprint instance is registered twice under two different URL prefixes. Both prefixes expose identical routes. Use `/custom-fields` as the canonical prefix. The `/templates` prefix exists for backwards compatibility or alias access.

---

## Overview

The library blueprint provides CRUD operations for reusable custom field templates — predefined question definitions that can be shared across forms. These are form-agnostic building blocks (e.g., a standard "Patient Name" text field with label, validation rules, and help text) that form designers can insert into forms without redefining from scratch.

---

## Route Reference

Standard REST CRUD. All routes require authentication.

### POST /form/api/v1/custom-fields/

**Summary:** Create a new custom field template.

**Authentication:** `@jwt_required()`

**Request body:**
```json
{
  "name": "Patient Name",
  "type": "text",
  "label": "Full Patient Name",
  "placeholder": "Enter patient's full name",
  "help_text": "As per medical record",
  "required": true,
  "validation": {
    "min_length": 2,
    "max_length": 100
  },
  "organization_id": "org-uuid"
}
```

**Response (201):** Created custom field template document.

---

### GET /form/api/v1/custom-fields/

**Summary:** List all custom field templates accessible to the user.

**Authentication:** `@jwt_required()`

**Query parameters:** `page`, `page_size`

**Response (200):** Paginated list of custom field templates.

---

### GET /form/api/v1/custom-fields/`<field_id>`

**Summary:** Get a specific custom field template.

**Authentication:** `@jwt_required()`

**Response (200):** Single custom field template document.

---

### PUT /form/api/v1/custom-fields/`<field_id>`

**Summary:** Update a custom field template.

**Authentication:** `@jwt_required()`

**Request body:** Fields to update.

---

### DELETE /form/api/v1/custom-fields/`<field_id>`

**Summary:** Delete a custom field template (soft delete).

**Authentication:** `@jwt_required()`

---

## Alias Routes (same behavior)

All the same routes are available under `/form/api/v1/templates/`:

```
POST   /form/api/v1/templates/
GET    /form/api/v1/templates/
GET    /form/api/v1/templates/<field_id>
PUT    /form/api/v1/templates/<field_id>
DELETE /form/api/v1/templates/<field_id>
```

---

## Notes

- Custom field templates are distinct from form templates (`Form` documents with `is_template = True`)
- Form templates are accessed via `GET /forms/templates` and `GET /forms/templates/<id>`
- Custom field templates (this blueprint) are reusable question definitions, not full form templates
- The dual registration means Flask generates two sets of endpoint names — this can cause `url_for()` conflicts if internal reverse URL lookup is used
