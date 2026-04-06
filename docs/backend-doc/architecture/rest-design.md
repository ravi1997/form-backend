# REST API Design Patterns

**Purpose:** Documentation for REST API design patterns, idempotency, filtering, sorting, pagination, bulk operations, and async operations.

**Scope:** REST design patterns, idempotency matrix, filtering and sorting standards, pagination patterns, bulk operation limits, and async operation patterns.

---

## Overview

This document outlines REST API design patterns for the RIDP Form Platform, ensuring consistency, usability, and performance across all endpoints.

**Target Audience:** API developers, frontend developers, system architects

---

## RESTful Principles

### Resource Identification

**URI Structure:**

```
https://api.example.com/form/api/v1/{resource}/{id}

Examples:
- /form/api/v1/forms
- /form/api/v1/forms/507f1f77bcf86cd799439011
- /form/api/v1/forms/507f1f77bcf86cd799439011/responses
```

### Resource Representation

**Standard Response Format:**

```python
# utils/response_helper.py
def success_response(data=None, message=None, status_code=200):
    """Standard success response format."""
    response = {
        "success": True,
        "data": data,
        "message": message
    }
    return jsonify(response), status_code

def error_response(message=None, errors=None, status_code=400):
    """Standard error response format."""
    response = {
        "success": False,
        "error": message,
        "errors": errors
    }
    return jsonify(response), status_code
```

---

## HTTP Methods

### Method Semantics

| Method | Operation | Idempotent | Safe | Cacheable |
|--------|-----------|------------|------|------------|
| GET | Read resource | Yes | Yes | Yes |
| POST | Create resource | No | No | No |
| PUT | Update/Replace resource | Yes | No | No |
| PATCH | Partial update | Yes | No | No |
| DELETE | Delete resource | Yes | No | No |

### Usage Examples

**GET (Read):**
```python
@bp.route("/forms/<form_id>", methods=["GET"])
def get_form(form_id):
    """Get form by ID."""
    form = Form.objects.get(id=form_id)
    return success_response(data=form.to_dict())
```

**POST (Create):**
```python
@bp.route("/forms", methods=["POST"])
def create_form():
    """Create new form."""
    schema = FormCreateSchema(**request.get_json())
    form = form_service.create(schema)
    return success_response(data=form.to_dict(), status_code=201)
```

**PUT (Update/Replace):**
```python
@bp.route("/forms/<form_id>", methods=["PUT"])
def update_form(form_id):
    """Update entire form."""
    schema = FormUpdateSchema(**request.get_json())
    form = form_service.update(form_id, schema)
    return success_response(data=form.to_dict())
```

**PATCH (Partial Update):**
```python
@bp.route("/forms/<form_id>", methods=["PATCH"])
def patch_form(form_id):
    """Partially update form."""
    schema = FormPatchSchema(**request.get_json())
    form = form_service.patch(form_id, schema)
    return success_response(data=form.to_dict())
```

**DELETE (Delete):**
```python
@bp.route("/forms/<form_id>", methods=["DELETE"])
def delete_form(form_id):
    """Delete form."""
    form = Form.objects.get(id=form_id)
    form.update(set__is_deleted=True)
    return success_response(message="Form deleted")
```

---

## Idempotency

### Idempotency Matrix

| Endpoint | Method | Idempotent | Notes |
|----------|--------|------------|-------|
| /forms | GET | Yes | Always returns same data |
| /forms | POST | No | Creates new resource each time |
| /forms/<id> | GET | Yes | Always returns same data |
| /forms/<id> | PUT | Yes | Same result for same input |
| /forms/<id> | PATCH | Yes | Same result for same input |
| /forms/<id> | DELETE | Yes | Same result (404 on second call) |
| /forms/<id>/publish | POST | No | Changes state each time |

### Idempotency Implementation

**Idempotency Keys:**

```python
# utils/idempotency.py
def check_idempotency(idempotency_key: str) -> Optional[dict]:
    """Check if request with idempotency key has been processed."""
    # Check Redis for cached response
    cached_response = redis_client.get(f"idempotency:{idempotency_key}")

    if cached_response:
        return json.loads(cached_response)

    return None

def store_idempotency_response(idempotency_key: str, response: dict):
    """Store response for idempotency key."""
    redis_client.setex(
        f"idempotency:{idempotency_key}",
        3600,  # 1 hour TTL
        json.dumps(response)
    )
```

**Usage:**

```python
@bp.route("/forms/<form_id>/publish", methods=["POST"])
def publish_form(form_id):
    """Publish form with idempotency."""
    # Get idempotency key from header
    idempotency_key = request.headers.get("Idempotency-Key")

    if idempotency_key:
        # Check if already processed
        cached_response = check_idempotency(idempotency_key)
        if cached_response:
            return jsonify(cached_response), 200

    # Process request
    form = form_service.publish(form_id)

    # Store response for idempotency
    response_data = {
        "success": True,
        "data": form.to_dict()
    }

    if idempotency_key:
        store_idempotency_response(idempotency_key, response_data)

    return jsonify(response_data), 200
```

---

## Filtering and Sorting

### Filtering Parameters

**Standard Query Parameters:**

```python
@bp.route("/forms", methods=["GET"])
def list_forms():
    """List forms with filtering."""
    # Parse filter parameters
    filters = {
        "status": request.args.get("status"),
        "created_after": request.args.get("created_after"),
        "created_before": request.args.get("created_before"),
        "search": request.args.get("search"),
    }

    # Build query
    query = Form.objects(is_deleted=False)

    if filters["status"]:
        query = query.filter(status=filters["status"])

    if filters["search"]:
        query = query.filter(name__icontains=filters["search"])

    # Execute query
    forms = query.all()

    return success_response(data=forms)
```

### Sorting Parameters

**Standard Sort Parameter:**

```
GET /forms?sort=created_at&order=desc

sort: field to sort by
order: asc or desc
```

**Implementation:**

```python
@bp.route("/forms", methods=["GET"])
def list_forms():
    """List forms with sorting."""
    # Parse sort parameters
    sort_field = request.args.get("sort", "created_at")
    sort_order = request.args.get("order", "desc")

    # Validate sort field
    allowed_sort_fields = ["created_at", "updated_at", "name", "status"]
    if sort_field not in allowed_sort_fields:
        return error_response(
            message=f"Invalid sort field. Allowed: {', '.join(allowed_sort_fields)}",
            status_code=400
        )

    # Build sort query
    sort_param = f"{sort_field}"
    if sort_order == "desc":
        sort_param = f"-{sort_field}"

    # Execute query
    forms = Form.objects(is_deleted=False).order_by(sort_param).all()

    return success_response(data=forms)
```

### Advanced Filtering

**JSON Filtering:**

```python
@bp.route("/forms/advanced", methods=["POST"])
def advanced_search():
    """Advanced form search with JSON filtering."""
    # Get filter from request body
    filter_data = request.get_json()

    # Build query from filter
    query = Form.objects(is_deleted=False)

    if "status" in filter_data:
        query = query.filter(status__in=filter_data["status"])

    if "created_at" in filter_data:
        start = parse_datetime(filter_data["created_at"]["start"])
        end = parse_datetime(filter_data["created_at"]["end"])
        query = query.filter(created_at__gte=start, created_at__lte=end)

    # Execute query
    forms = query.all()

    return success_response(data=forms)
```

---

## Pagination

### Standard Pagination

**Parameters:**
```
GET /forms?page=1&pageSize=50

page: Page number (1-indexed)
pageSize: Items per page (default: 50, max: 200)
```

**Response Format:**

```python
@bp.route("/forms", methods=["GET"])
def list_forms():
    """List forms with pagination."""
    # Parse pagination parameters
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("pageSize", 50))

    # Validate page size
    if page_size > 200:
        page_size = 200

    # Calculate skip
    skip = (page - 1) * page_size

    # Query with pagination
    total_count = Form.objects(is_deleted=False).count()
    forms = Form.objects(is_deleted=False).skip(skip).limit(page_size).all()

    # Calculate total pages
    total_pages = (total_count + page_size - 1) // page_size

    # Build response
    response_data = {
        "items": [form.to_dict() for form in forms],
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "totalCount": total_count,
            "totalPages": total_pages,
            "hasNext": page < total_pages,
            "hasPrevious": page > 1
        }
    }

    return success_response(data=response_data)
```

### Cursor-Based Pagination (Alternative)

**For large datasets:**

```python
@bp.route("/forms/cursor", methods=["GET"])
def list_forms_cursor():
    """List forms with cursor-based pagination."""
    # Get cursor
    cursor = request.args.get("cursor")
    page_size = int(request.args.get("pageSize", 50))

    # Build query
    query = Form.objects(is_deleted=False)

    if cursor:
        query = query.filter(id__gt=ObjectId(cursor))

    # Query with limit
    forms = query.limit(page_size + 1).all()

    # Determine if there are more results
    has_more = len(forms) > page_size
    items = forms[:page_size]

    # Get next cursor
    next_cursor = str(items[-1].id) if items else None

    return success_response(data={
        "items": [form.to_dict() for form in items],
        "pagination": {
            "nextCursor": next_cursor,
            "hasMore": has_more,
            "pageSize": page_size
        }
    })
```

---

## Field Projection

### Sparse Fieldsets

**Request:**
```
GET /forms/507f1f77bcf86cd799439011?fields=name,status,created_at
```

**Implementation:**

```python
@bp.route("/forms/<form_id>", methods=["GET"])
def get_form(form_id):
    """Get form with field projection."""
    form = Form.objects.get(id=form_id)

    # Get requested fields
    fields = request.args.get("fields", "").split(",")

    if fields:
        # Project only requested fields
        form_data = {
            field: getattr(form, field, None)
            for field in fields
            if hasattr(form, field)
        }
    else:
        # Return all fields
        form_data = form.to_dict()

    return success_response(data=form_data)
```

---

## Bulk Operations

### Bulk Create

**Request:**
```json
POST /forms/bulk
{
  "items": [
    {"name": "Form 1", "status": "draft"},
    {"name": "Form 2", "status": "draft"}
  ]
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "created": [
      {"id": "...", "name": "Form 1"},
      {"id": "...", "name": "Form 2"}
    ],
    "errors": []
  }
}
```

**Implementation:**

```python
@bp.route("/forms/bulk", methods=["POST"])
def bulk_create_forms():
    """Bulk create forms."""
    items = request.get_json().get("items", [])

    # Validate batch size
    MAX_BATCH_SIZE = 100
    if len(items) > MAX_BATCH_SIZE:
        return error_response(
            message=f"Batch size exceeds maximum of {MAX_BATCH_SIZE}",
            status_code=400
        )

    created = []
    errors = []

    for i, item in enumerate(items):
        try:
            schema = FormCreateSchema(**item)
            form = form_service.create(schema)
            created.append({
                "index": i,
                "id": str(form.id),
                "name": form.name
            })
        except Exception as e:
            errors.append({
                "index": i,
                "error": str(e)
            })

    response_data = {
        "created": created,
        "errors": errors
    }

    return success_response(
        data=response_data,
        message=f"Created {len(created)} forms",
        status_code=201 if not errors else 207  # Multi-Status
    )
```

### Bulk Update

**Request:**
```json
PATCH /forms/bulk
{
  "updates": [
    {"id": "...", "status": "published"},
    {"id": "...", "status": "published"}
  ]
}
```

**Implementation:**

```python
@bp.route("/forms/bulk", methods=["PATCH"])
def bulk_update_forms():
    """Bulk update forms."""
    updates = request.get_json().get("updates", [])

    # Validate batch size
    MAX_BATCH_SIZE = 100
    if len(updates) > MAX_BATCH_SIZE:
        return error_response(
            message=f"Batch size exceeds maximum of {MAX_BATCH_SIZE}",
            status_code=400
        )

    updated = []
    errors = []

    for i, update in enumerate(updates):
        try:
            form_id = update.get("id")
            schema = FormUpdateSchema(**update)
            form = form_service.update(form_id, schema)
            updated.append({
                "index": i,
                "id": str(form.id)
            })
        except Exception as e:
            errors.append({
                "index": i,
                "error": str(e)
            })

    response_data = {
        "updated": updated,
        "errors": errors
    }

    return success_response(
        data=response_data,
        message=f"Updated {len(updated)} forms",
        status_code=207 if errors else 200
    )
```

### Bulk Delete

**Request:**
```json
DELETE /forms/bulk
{
  "ids": ["...", "..."]
}
```

**Implementation:**

```python
@bp.route("/forms/bulk", methods=["DELETE"])
def bulk_delete_forms():
    """Bulk delete forms."""
    ids = request.get_json().get("ids", [])

    # Validate batch size
    MAX_BATCH_SIZE = 100
    if len(ids) > MAX_BATCH_SIZE:
        return error_response(
            message=f"Batch size exceeds maximum of {MAX_BATCH_SIZE}",
            status_code=400
        )

    deleted = []
    errors = []

    for i, form_id in enumerate(ids):
        try:
            form = Form.objects.get(id=form_id)
            form.update(set__is_deleted=True)
            deleted.append({
                "index": i,
                "id": form_id
            })
        except Exception as e:
            errors.append({
                "index": i,
                "error": str(e)
            })

    response_data = {
        "deleted": deleted,
        "errors": errors
    }

    return success_response(
        data=response_data,
        message=f"Deleted {len(deleted)} forms",
        status_code=207 if errors else 200
    )
```

---

## Async Operations

### Task Queue Pattern

**Long-running operations:**

```python
@bp.route("/forms/<form_id>/publish", methods=["POST"])
def publish_form_async():
    """Publish form asynchronously."""
    form_id = request.form_id

    # Enqueue task
    task = async_publish_form.delay(form_id)

    # Return 202 Accepted with task ID
    return success_response(
        data={"task_id": task.id},
        message="Form publication started",
        status_code=202
    )
```

### Task Status Polling

**Status Endpoint:**

```python
@bp.route("/tasks/<task_id>", methods=["GET"])
def get_task_status(task_id):
    """Get task status."""
    task = celery.AsyncResult(task_id)

    response_data = {
        "task_id": task_id,
        "status": task.state,
        "result": task.result if task.ready() else None
    }

    if task.failed():
        response_data["error"] = str(task.info)

    return success_response(data=response_data)
```

### Streaming Responses

**Server-Sent Events (SSE):**

```python
@bp.route("/forms/<form_id>/summarize-stream", methods=["GET"])
def summarize_form_stream(form_id):
    """Stream LLM summarization results."""
    def generate():
        # Process form
        for chunk in llm_summarize(form_id):
            yield f"data: {chunk}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
```

---

## ETag and Caching

### ETag Implementation

**Generate ETag:**

```python
@bp.route("/forms/<form_id>", methods=["GET"])
def get_form(form_id):
    """Get form with ETag support."""
    form = Form.objects.get(id=form_id)
    form_data = form.to_dict()

    # Generate ETag (hash of form data)
    etag = hashlib.md5(json.dumps(form_data, sort_keys=True).encode()).hexdigest()

    # Check If-None-Match header
    if_none_match = request.headers.get("If-None-Match")
    if if_none_match == etag:
        return "", 304  # Not Modified

    # Return response with ETag
    response = jsonify(form_data)
    response.set_etag(etag)

    return response
```

---

## Best Practices

### 1. Use Proper HTTP Methods

```python
# CORRECT - Appropriate method
@bp.route("/forms", methods=["POST"])
def create_form():
    pass

# WRONG - Wrong method
@bp.route("/forms", methods=["GET"])
def create_form():
    # Don't use GET for creation
```

### 2. Return Proper Status Codes

```python
# CORRECT - Appropriate status codes
return success_response(data=data, status_code=201)  # Created
return error_response(message="Not found", status_code=404)  # Not Found
return error_response(message="Unauthorized", status_code=401)  # Unauthorized

# WRONG - Always return 200
return success_response(data={"error": "Not found"}, status_code=200)
```

### 3. Use Consistent Response Format

```python
# CORRECT - Consistent format
return success_response(data=form_data)
return error_response(message="Validation failed")

# WRONG - Inconsistent formats
return jsonify({"form": form_data})
return jsonify({"error": "Validation failed", "code": "VALIDATION_ERROR"})
```

### 4. Implement Pagination

```python
# CORRECT - Paginated results
return success_response(data={
    "items": items,
    "pagination": {"page": page, "pageSize": page_size, "totalCount": total}
})

# WRONG - Return all results
return success_response(data=all_items)  # May be huge
```

### 5. Version Your API

```python
# CORRECT - Versioned API
@bp.route("/api/v1/forms", methods=["GET"])
def list_forms():
    pass

# WRONG - Unversioned API
@bp.route("/forms", methods=["GET"])
def list_forms():
    # Hard to evolve without breaking changes
```

---

## References

- [REST API Design Best Practices](https://restfulapi.net/)
- [Microsoft REST Guidelines](https://docs.microsoft.com/en-us/azure/architecture/best-practices/api-design)
- [Google API Design Guide](https://cloud.google.com/apis/design)
- [HTTP Status Codes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status)
- [JSON API Specification](https://jsonapi.org/)
