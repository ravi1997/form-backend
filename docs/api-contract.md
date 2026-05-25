# API Contract Standard

Version: 1

## Base

All versioned JSON APIs are served under `/form/api/v1`.
Health endpoints are outside the versioned prefix under `/form/health`.

## Success Envelope

```json
{
  "success": true,
  "message": "Success",
  "request_id": "uuid-or-client-provided-id",
  "data": {}
}
```

`data` is omitted only when the endpoint has no body payload.

## Error Envelope

```json
{
  "success": false,
  "request_id": "uuid-or-client-provided-id",
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Invalid payload",
    "details": {},
    "field_errors": {},
    "retry_after": 30
  }
}
```

Required error fields: `code`, `message`.
Optional error fields: `details`, `field_errors`, `retry_after`.

## Pagination

```json
{
  "items": [],
  "page": 1,
  "page_size": 50,
  "total": 0,
  "total_pages": 0,
  "has_next": false,
  "has_prev": false
}
```

## Canonical Form Routes

Project-scoped form routes are canonical:

- `GET /projects/{project_id}/forms`
- `POST /projects/{project_id}/forms`
- `GET /projects/{project_id}/forms/{form_id}`
- `PUT /projects/{project_id}/forms/{form_id}`
- `DELETE /projects/{project_id}/forms/{form_id}`
- `PUT /projects/{project_id}/forms/{form_id}/draft`
- `POST /projects/{project_id}/forms/{form_id}/publish`
- `POST /projects/{project_id}/forms/{form_id}/clone`

Global `/forms` routes are compatibility or cross-form routes only and must not
be used for canonical CRUD.

## Async Task Contract

Mutation endpoints that return a task use HTTP `202` and return:

```json
{
  "task_id": "uuid",
  "status_url": "/form/api/v1/tasks/{task_id}"
}
```

`GET /tasks/{task_id}` returns task state, progress, result, error, and retry
metadata in the standard success envelope.
