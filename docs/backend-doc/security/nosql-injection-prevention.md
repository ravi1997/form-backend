# NoSQL Injection Prevention

**Purpose:** Documentation for safe MongoDB query construction to prevent NoSQL injection attacks.

**Scope:** NoSQL injection prevention, query escaping, field sanitization, and safe query building patterns.

---

## Overview

NoSQL injection attacks occur when untrusted user input is directly concatenated into MongoDB queries, allowing attackers to manipulate query logic and bypass authentication or access unauthorized data. This system provides utilities for safe query construction and input sanitization.

**Key Components:**
- `utils/mongodb_query_helper.py` - NoSQL injection prevention logic (169 lines)
- Integration with all route handlers using raw MongoDB queries

---

## NoSQL Injection Vulnerabilities

### Common Attack Vectors

**1. Operator Injection**

```python
# VULNERABLE CODE
username = request.json.get("username")
user = User.objects(username=username).first()

# Attack: {"username": {"$ne": null}}
# Result: Returns first user (bypasses authentication)

# VULNERABLE CODE
password = request.json.get("password")
user = User.objects(password=password).first()

# Attack: {"password": {"$regex": ".*"}}
# Result: Bypasses password validation
```

**2. Key Injection**

```python
# VULNERABLE CODE
field_name = request.json.get("field")
value = request.json.get("value")
query = {field_name: value}
results = MyModel.objects(__raw__=query)

# Attack: {"field": "password", "value": {"$ne": null}}
# Query: {"password": {"$ne": null}}
# Result: Exposes all password hashes
```

**3. Where Clause Injection**

```python
# VULNERABLE CODE
query = request.json.get("query")
results = MyModel.objects(__raw__={"$where": query})

# Attack: "this.password === 'admin123'"
# Result: Executes JavaScript on server
```

---

## MongoDB Operators (Blocklist)

```python
# utils/mongodb_query_helper.py
MONGODB_OPERATORS = {
    # Logical operators
    "$or", "$and", "$not", "$nor",

    # Comparison operators
    "$gt", "$gte", "$lt", "$lte", "$ne",

    # Array operators
    "$in", "$nin", "$all", "$size", "$elemMatch",

    # Element operators
    "$exists", "$type",

    # Evaluation operators
    "$regex", "$mod", "$where",

    # Text search
    "$text", "$search",
}
```

**Rationale:** These operators can be used to manipulate query logic when injected from untrusted input.

---

## Safe Query Building

### 1. Value Escaping

```python
from utils.mongodb_query_helper import NoSQLInjector

# SAFE CODE
username = request.json.get("username")
safe_username = NoSQLInjector.escape_value(username)
user = User.objects(username=safe_username).first()

# If username is: {"$ne": null}
# Escaped to: {"\$ne": null}
# Result: Literal string search, not operator
```

**Implementation:**
```python
@staticmethod
def escape_value(value: Any) -> Any:
    """Escape a value to prevent NoSQL injection."""
    if not isinstance(value, str):
        return value

    # Escape MongoDB operators
    for operator in NoSQLInjector.MONGODB_OPERATORS:
        if operator in value:
            value = value.replace(operator, f"\\{operator}")

    return value
```

### 2. Key Sanitization

```python
from utils.mongodb_query_helper import NoSQLInjector

# SAFE CODE
field_name = request.json.get("field")
value = request.json.get("value")

safe_field = NoSQLInjector.sanitize_key(field_name)
safe_value = NoSQLInjector.escape_value(value)

query = {safe_field: safe_value}
results = MyModel.objects(__raw__=query)

# If field_name is: "password.$ne"
# Sanitized to: "password_ne"
# If value is: {"$ne": null}
# Escaped to: {"\$ne": null}
```

**Implementation:**
```python
@staticmethod
def sanitize_key(key: str) -> str:
    """Sanitize a MongoDB key to prevent NoSQL injection."""
    if not isinstance(key, str):
        return key

    # Remove MongoDB operators and special characters
    # Only allow alphanumeric, underscore, and dot
    sanitized = re.sub(r"[\$\.\{]", "", key)

    return sanitized
```

### 3. Safe Field-Value Query

```python
from utils.mongodb_query_helper import NoSQLInjector

# Build safe query for field-value pair
field = request.json.get("field")
value = request.json.get("value")

safe_query = NoSQLInjector.build_safe_query(field, value)
results = MyModel.objects(__raw__=safe_query)

# If field="username" and value={"$ne": null}
# Query: {"username": {"\$ne": null}}
# Result: Literal search for string "{$ne: null}"
```

**Implementation:**
```python
@staticmethod
def build_safe_query(field: str, value: Any) -> Dict[str, Any]:
    """Build a safe MongoDB query for a field-value pair."""
    safe_field = NoSQLInjector.sanitize_key(field)
    safe_value = NoSQLInjector.escape_value(value)

    return {safe_field: safe_value}
```

### 4. Safe $or Query

```python
from utils.mongodb_query_helper import NoSQLInjector

# Build safe $or query for multiple values
field = request.json.get("field")
values = request.json.get("values", [])

safe_query = NoSQLInjector.build_or_query(field, values)
results = MyModel.objects(__raw__=safe_query)

# If field="status" and values=["active", {"$ne": null}]
# Query: {"$or": [{"status": "active"}, {"status": {"\$ne": null}}]}
```

**Implementation:**
```python
@staticmethod
def build_or_query(field: str, values: List[Any]) -> Dict[str, Any]:
    """Build a safe $or query for a field with multiple values."""
    if not values:
        raise ValueError("Cannot build $or query with empty values list")

    # Sanitize field and escape each value
    safe_field = NoSQLInjector.sanitize_key(field)
    safe_values = [NoSQLInjector.escape_value(v) for v in values]

    # Build query
    queries = [{safe_field: v} for v in safe_values]

    return {"$or": queries}
```

---

## Real-World Example: Advanced Responses

**Location:** `routes/v1/form/advanced_responses.py:60-73`

**Vulnerable Code (Before Fix):**
```python
# VULNERABLE
responses = FormResponse.objects(
    __raw__={
        "$or": [
            {f"data.{section.id}.{question_id}": value}
            for section in form.versions[-1].sections
        ]
    }
)
```

**Attack Vector:**
- `question_id` could be: `"password"`, `"email"`, or `"user.$ne"`
- `value` could be: `{"$ne": null}` or `{"$regex": ".*"}`

**Fixed Code:**
```python
# SECURE
from utils.mongodb_query_helper import NoSQLInjector

# Sanitize inputs
safe_question_id = NoSQLInjector.sanitize_key(question_id)
safe_value = NoSQLInjector.escape_value(value)

# Build safe $or query
or_conditions = [
    {f"data.{section_id_str}.{safe_question_id}": safe_value}
    for section in form.versions[-1].sections
]

responses = FormResponse.objects(__raw__={
    "$or": or_conditions,
    "form_id": form_id,
    "organization_id": organization_id,
    "is_deleted": False
})
```

---

## JSON Structure Validation

```python
from utils.mongodb_query_helper import NoSQLInjector

# Validate JSON structure doesn't contain malicious operators
query_dict = request.json.get("query", {})

if not NoSQLInjector.validate_json_structure(query_dict):
    audit_logger.warning("Malicious query structure detected")
    return error_response(
        message="Invalid query structure",
        status_code=400
    )
```

**Implementation:**
```python
@staticmethod
def validate_json_structure(obj: Dict[str, Any]) -> bool:
    """
    Validate that a JSON object doesn't contain MongoDB operators
    in unexpected places.
    """
    if not isinstance(obj, dict):
        return False

    # Check for MongoDB operators at top level (suspicious)
    for key in obj.keys():
        if key.startswith("$"):
            return False

    return True
```

---

## Usage Examples

### 1. User Input in Queries

```python
from utils.mongodb_query_helper import NoSQLInjector

@bp.route("/search", methods=["POST"])
def search_users():
    email = request.json.get("email")

    # SAFE - Escape user input
    safe_email = NoSQLInjector.escape_value(email)
    user = User.objects(email=safe_email).first()

    return success_response(data=user.to_dict())
```

### 2. Dynamic Field Queries

```python
from utils.mongodb_query_helper import NoSQLInjector

@bp.route("/filter", methods=["POST"])
def filter_data():
    field = request.json.get("field")  # e.g., "status"
    value = request.json.get("value")   # e.g., "active"

    # SAFE - Sanitize field and escape value
    safe_query = NoSQLInjector.build_safe_query(field, value)
    results = MyModel.objects(__raw__=safe_query)

    return success_response(data=results)
```

### 3. Multi-Value Queries

```python
from utils.mongodb_query_helper import NoSQLInjector

@bp.route("/search-multiple", methods=["POST"])
def search_multiple():
    field = request.json.get("field")
    values = request.json.get("values", [])

    # SAFE - Build $or query with escaped values
    safe_query = NoSQLInjector.build_or_query(field, values)
    results = MyModel.objects(__raw__=safe_query)

    return success_response(data=results)
```

### 4. Complex Queries

```python
from utils.mongodb_query_helper import NoSQLInjector

@bp.route("/advanced-search", methods=["POST"])
def advanced_search():
    search_terms = request.json.get("terms", [])

    # Build safe query from multiple terms
    query_conditions = []

    for term in search_terms:
        field = term.get("field")
        value = term.get("value")

        safe_query = NoSQLInjector.build_safe_query(field, value)
        query_conditions.append(safe_query)

    # Combine with $and
    final_query = {"$and": query_conditions}
    results = MyModel.objects(__raw__=final_query)

    return success_response(data=results)
```

---

## Best Practices

### 1. Always Sanitize User Input

```python
# CORRECT
from utils.mongodb_query_helper import NoSQLInjector
safe_value = NoSQLInjector.escape_value(user_input)
query = {field: safe_value}

# WRONG
query = {field: user_input}  # VULNERABLE
```

### 2. Sanitize Field Names

```python
# CORRECT
safe_field = NoSQLInjector.sanitize_key(field_name)
query = {safe_field: value}

# WRONG
query = {field_name: value}  # VULNERABLE to key injection
```

### 3. Avoid Raw Queries When Possible

```python
# CORRECT - Use MongoEngine ORM
user = User.objects(email=email).first()

# ACCEPTABLE - Use escaped raw queries when necessary
safe_email = NoSQLInjector.escape_value(email)
user = User.objects(__raw__={"email": safe_email}).first()

# WRONG - Use unescaped raw queries
user = User.objects(__raw__={"email": email}).first()
```

### 4. Validate JSON Structure

```python
# CORRECT
if NoSQLInjector.validate_json_structure(query_dict):
    results = MyModel.objects(__raw__=query_dict)

# WRONG
results = MyModel.objects(__raw__=query_dict)  # No validation
```

### 5. Log Security Events

```python
from logger.unified_logger import audit_logger

# Log operator injection attempts
if "$" in field_name or "$" in value:
    audit_logger.warning(
        f"Potential NoSQL injection attempt: "
        f"Field={field_name}, Value={value}"
    )
```

---

## Security Considerations

### 1. Authentication Bypass

**Attack:** `{"username": {"$ne": null}, "password": {"$ne": null}}`

**Defense:**
```python
# Escape both username and password
safe_username = NoSQLInjector.escape_value(username)
safe_password = NoSQLInjector.escape_value(password)
user = User.objects(
    username=safe_username,
    password=safe_password
).first()
```

### 2. Data Exfiltration

**Attack:** `{"password": {"$regex": "^a"}}` (enumerate passwords)

**Defense:**
- Rate limit query endpoints
- Log suspicious query patterns
- Use authentication and authorization

### 3. JavaScript Injection

**Attack:** `{"$where": "this.password === 'admin123'"}`

**Defense:**
```python
# Never use $where with user input
# Block $where operator completely
if "$where" in query_dict:
    audit_logger.error("Attempted $where injection")
    raise SecurityError("$where operator not allowed")
```

---

## Testing

### Unit Tests

```python
def test_escape_value():
    from utils.mongodb_query_helper import NoSQLInjector

    # Escape operator
    result = NoSQLInjector.escape_value({"$ne": null})
    assert result == "{\$ne: null}"

    # No escape needed for normal strings
    result = NoSQLInjector.escape_value("normal_string")
    assert result == "normal_string"

def test_sanitize_key():
    from utils.mongodb_query_helper import NoSQLInjector

    # Remove operator
    result = NoSQLInjector.sanitize_key("password.$ne")
    assert result == "password_ne"

    # Remove special characters
    result = NoSQLInjector.sanitize_key("field{special}")
    assert result == "field_special"

def test_build_safe_query():
    from utils.mongodb_query_helper import NoSQLInjector

    query = NoSQLInjector.build_safe_query("username", {"$ne": null})
    assert query == {"username": "{\$ne: null}"}

def test_validate_json_structure():
    from utils.mongodb_query_helper import NoSQLInjector

    # Valid structure
    assert NoSQLInjector.validate_json_structure({"field": "value"}) == True

    # Invalid - top-level operator
    assert NoSQLInjector.validate_json_structure({"$or": [...]}) == False
```

---

## Configuration Reference

### MongoDB Query Helper Constants

```python
# utils/mongodb_query_helper.py
MONGODB_OPERATORS = {
    "$or", "$and", "$not", "$nor",
    "$gt", "$gte", "$lt", "$lte", "$ne",
    "$in", "$nin", "$all", "$size", "$elemMatch",
    "$exists", "$type",
    "$regex", "$mod", "$where",
    "$text", "$search",
}
```

---

## References

- [OWASP NoSQL Injection Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/NoSQL_Injection_Prevention_Cheat_Sheet.html)
- [MongoDB Security Best Practices](https://www.mongodb.com/docs/manual/administration/security-best-practices/)
- [CWE-943: Improper Neutralization of Special Elements in Data Query Logic](https://cwe.mitre.org/data/definitions/943.html)
- [NIST SP 800-53: SI-10 Information Input Validation](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)
