# File Upload Security

**Purpose:** Comprehensive documentation for secure file upload validation and handling in the RIDP Form Platform.

**Scope:** File upload endpoints, validation rules, MIME type checking, size limits, filename sanitization, and secure storage procedures.

---

## Overview

The file upload security system implements OWASP recommendations for protecting against common file upload vulnerabilities including malicious file execution, path traversal, and content-type spoofing. All file uploads pass through multiple validation layers before being stored.

**Key Components:**
- `utils/file_validator.py` - Core validation logic (420 lines)
- `utils/file_handler.py` - Secure file storage handler (153 lines)
- `routes/v1/form/files.py` - File upload endpoints

---

## File Upload Workflow

```python
# Upload flow diagram
User Upload Request
    ↓
File Size Check (Flask MAX_CONTENT_LENGTH)
    ↓
File Validation (file_validator.validate_upload)
    ├─ Filename validation
    ├─ Extension whitelist check
    ├─ Extension blocklist check
    ├─ MIME type detection (python-magic)
    ├─ MIME type comparison
    └─ File size validation
    ↓
Secure Filename Generation (UUID suffix)
    ↓
Storage to Organized Directory Structure
    ↓
Return File Metadata
```

---

## File Validation Rules

### 1. Allowed File Extensions (Whitelist)

**Image Files:**
```python
ALLOWED_IMAGES = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico"]
MAX_SIZE = 5MB
```

**Document Files:**
```python
ALLOWED_DOCUMENTS = [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", 
                     ".odt", ".ods", ".odp", ".txt", ".rtf", ".csv"]
MAX_SIZE = 25MB
```

**Archive Files:**
```python
ALLOWED_ARCHIVES = [".zip", ".rar", ".7z", ".tar", ".gz"]
MAX_SIZE = 100MB
```

**Configuration:**
```python
# config/settings.py
MAX_FILE_SIZE_FORM: int = 10 * 1024 * 1024  # 10MB default
MAX_FILE_SIZE_EXPORT: int = 50 * 1024 * 1024  # 50MB for exports
MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16MB request limit
```

### 2. Blocked File Extensions (Blocklist)

**Dangerous Extensions (NEVER ALLOWED):**
```python
BLOCKED_EXTENSIONS = {
    # Web server scripts
    ".php", ".php3", ".php4", ".php5", ".phtml",
    ".jsp", ".jspx", ".jsw", ".jsv", ".jspf",
    ".asp", ".aspx", ".asa", ".asax", ".ascx", ".ashx", ".asmx",

    # Executables
    ".exe", ".bat", ".cmd", ".com", ".scr", ".pif", ".vbs",
    ".js", ".jar", ".sh", ".ps1", ".ps2", ".msi", ".msp",

    # System files
    ".msc", ".appx", ".appbundle", ".deb", ".rpm", ".dmg", ".pkg", ".elf",
}
```

**Rationale:** These extensions can execute code on the server or client, leading to remote code execution (RCE) attacks.

### 3. MIME Type Validation

**Purpose:** Detect actual file content type to prevent content-type spoofing attacks.

**Implementation:**
```python
import magic

def validate_mime_type(file: FileStorage) -> Tuple[bool, Optional[str]]:
    """Validate file MIME type against declared content type."""
    # Read first 2048 bytes for detection
    file_content = file.read(2048)
    file.seek(0)  # Reset file pointer

    # Detect actual MIME type using python-magic
    detected_mime = magic.from_buffer(file_content, mime=True)

    # Check against allowed MIME types for extension
    allowed_mimes = ALLOWED_MIME_TYPES.get(ext, [])
    if detected_mime not in allowed_mimes:
        return False, f"MIME type mismatch: {detected_mime}"

    return True, None
```

**Allowed MIME Types:**
```python
ALLOWED_MIME_TYPES = {
    ".jpg": ["image/jpeg"],
    ".png": ["image/png"],
    ".pdf": ["application/pdf"],
    ".docx": ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
    ".zip": ["application/zip", "application/x-zip-compressed"],
    # ... (full mapping in file_validator.py)
}
```

**Example Attacks Prevented:**
- Renaming `malicious.php` to `malicious.jpg`
- Embedding script code in image file headers
- Polyglot files that parse as multiple types

### 4. Filename Validation and Sanitization

**Validation Rules:**
```python
def validate_filename(filename: str) -> Tuple[bool, Optional[str]]:
    # 1. No path traversal
    if ".." in filename or filename.startswith("/"):
        return False, "Invalid filename: path traversal detected"

    # 2. No null bytes
    if "\x00" in filename:
        return False, "Invalid filename: null bytes detected"

    # 3. Length limit
    if len(filename) > 255:
        return False, "Filename too long (max 255 characters)"

    # 4. No reserved Windows names
    reserved_names = ["con", "prn", "aux", "nul", "com1-9", "lpt1-9"]
    # ... check against reserved names
```

**Sanitization:**
```python
def sanitize_filename(filename: str) -> str:
    # Remove dangerous characters, keep only alphanumeric, underscore, hyphen, space, dot
    name = "".join(c for c in name if c.isalnum() or c in "._- ")
    name = name.strip(" ._")

    # Add UUID suffix to prevent collisions
    uuid_suffix = uuid.uuid4().hex[:12]
    return f"{name}_{uuid_suffix}{ext}"
```

**Example:**
```
Input:  "../../../../etc/passwd"
Output: "etc_passwd_a1b2c3d4e5f6.ext"

Input:  "my report.pdf"
Output: "my_report_a1b2c3d4e5f6.pdf"
```

---

## File Storage Structure

**Directory Organization:**
```
uploads/
├── form_id_1/
│   ├── field_id_1/
│   │   ├── file_abc123.pdf
│   │   └── file_def456.jpg
│   ├── field_id_2/
│   │   └── file_ghi789.docx
│   └── signatures/
│       ├── sig_jkl012.png
│       └── sig_mno345.png
├── form_id_2/
│   └── ...
```

**Isolation Benefits:**
- Tenant isolation via form_id
- Field-level organization
- Separate signature storage
- Easy cleanup per form

**Configuration:**
```python
# config/settings.py
UPLOAD_FOLDER: str = os.environ.get("UPLOAD_FOLDER", "uploads")
```

---

## Usage Examples

### Basic File Upload Validation

```python
from utils.file_validator import validate_upload, FileUploadError
from werkzeug.datastructures import FileStorage

@bp.route("/upload", methods=["POST"])
@jwt_required()
def upload_file():
    file = request.files.get("file")

    try:
        # Comprehensive validation
        is_valid, error = validate_upload(file, max_size=10*1024*1024)
        if not is_valid:
            return error_response(message=error, status_code=400)

        # File is safe to process
        file_info = save_uploaded_file(file, form_id, field_id)
        return success_response(data=file_info)

    except FileUploadError as e:
        return error_response(
            message=f"Validation failed: {e}",
            error_code=e.error_code,
            status_code=400
        )
```

### Custom Allowed Extensions

```python
from utils.file_validator import validate_upload, ALLOWED_EXTENSIONS

# Restrict to images only
image_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp"]

is_valid, error = validate_upload(
    file,
    max_size=5*1024*1024,
    allowed_extensions=image_extensions
)
```

### Secure Filename Generation

```python
from utils.file_validator import generate_secure_filename

original = "My Report (Final).pdf"
secure = generate_secure_filename(original)
# Output: "My_Report__Final__a1b2c3d4e5f6.pdf"
```

### Custom Error Handling

```python
from utils.file_validator import FileUploadError

try:
    validate_upload(file)
except FileUploadError as e:
    if e.error_code == "INVALID_FILENAME":
        # Handle path traversal attempt
        audit_logger.warning(f"Path traversal attempt: {file.filename}")
    elif e.error_code == "INVALID_MIME_TYPE":
        # Handle MIME spoofing
        audit_logger.warning(f"MIME spoofing attempt: {file.filename}")
    elif e.error_code == "FILE_TOO_LARGE":
        # Handle size limit exceeded
        pass
    # ... handle other error codes
```

---

## Best Practices

### 1. Always Validate Before Processing

```python
# CORRECT
validate_upload(file)
save_uploaded_file(file, form_id, field_id)

# WRONG
file.save(os.path.join(upload_dir, file.filename))  # NEVER DO THIS
```

### 2. Use Secure Filenames

```python
# CORRECT
secure_filename = generate_secure_filename(file.filename)
filepath = os.path.join(upload_dir, secure_filename)

# WRONG
filepath = os.path.join(upload_dir, file.filename)  # Vulnerable
```

### 3. Check File Size Early

```python
# Set Flask app-level limit
app.config["MAX_CONTENT_LENGTH"] = settings.MAX_CONTENT_LENGTH

# Validate specific limits per file type
validate_upload(file, max_size=5*1024*1024)  # 5MB for images
```

### 4. Log Validation Failures

```python
from logger.unified_logger import app_logger, audit_logger

try:
    validate_upload(file)
except FileUploadError as e:
    audit_logger.warning(
        f"File upload validation failed: {e.error_code} - {file.filename}"
    )
    error_logger.error(
        f"File validation error: {str(e)}", exc_info=True
    )
```

### 5. Never Trust User Input

```python
# CORRECT - Validate all inputs
if not file or not file.filename:
    raise FileUploadError("No file provided", "NO_FILE")

# WRONG - Trusting user-provided data
ext = os.path.splitext(request.form.get("filename"))[1]  # Don't do this
```

---

## Integration Points

### 1. File Upload Endpoints

**Location:** `routes/v1/form/files.py`

**Endpoints:**
- `POST /form/api/v1/forms/upload` - General file upload
- `POST /form/api/v1/forms/signatures` - Signature upload
- `GET /form/api/v1/forms/<id>/files/<qid>/<filename>` - File serving

### 2. Rate Limiting

```python
from extensions import limiter

@bp.route("/upload", methods=["POST"])
@limiter.limit("10 per minute")
def upload_file():
    # ... upload logic
```

**Configuration:**
```python
# config/settings.py
RATE_LIMIT_FILE_UPLOAD: str = "10 per minute"
```

### 3. Virus Scanning (Future)

**Current Status:** Placeholder implementation

**Recommended Integration:**
```python
# TODO: Integrate ClamAV or VirusTotal API
def scan_file_for_viruses(filepath: str) -> bool:
    """Scan file using ClamAV."""
    import pyclamd

    cd = pyclamd.ClamdAgnostic()
    scan_result = cd.scan_file(filepath)

    if scan_result is not None and scan_result.get(filepath) is not None:
        # File is infected
        return False

    return True
```

**Integration Point:** Add to `validate_upload()` after MIME type validation.

---

## Security Considerations

### 1. MIME Type Spoofing Prevention

**Attack Vector:** Attacker renames malicious file to benign extension.

**Defense:** 
- Use `python-magic` to detect actual file content
- Validate detected MIME against allowed types for extension
- Reject mismatches

### 2. Path Traversal Prevention

**Attack Vector:** `../../../etc/passwd` in filename

**Defense:**
- Block `..` in filenames
- Block leading `/` in filenames
- Use `os.path.join()` for path construction
- Generate UUID-based filenames

### 3. Null Byte Injection Prevention

**Attack Vector:** `malicious.php\x00.jpg` to bypass extension checks

**Defense:**
- Explicitly check for `\x00` in filenames
- Reject if found

### 4. Reserved Name Prevention

**Attack Vector:** Windows reserved names can cause system issues

**Defense:**
- Block Windows reserved device names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)

### 5. File Size DoS Prevention

**Attack Vector:** Upload large files to exhaust disk space

**Defense:**
- Flask `MAX_CONTENT_LENGTH` limit (16MB)
- Per-file-type size limits (5MB images, 25MB docs, 100MB archives)
- Early validation before file read

---

## Monitoring and Alerting

### 1. Log Validation Failures

```python
audit_logger.warning(
    f"File upload blocked - {error_code} - "
    f"User: {user_id} - File: {filename} - Size: {size}"
)
```

### 2. Monitor Upload Patterns

**Metrics to Track:**
- Upload success rate
- Upload failure reasons (by error code)
- Average file size
- Files per user per hour
- MIME type distribution

### 3. Alert on Suspicious Activity

**Alert Conditions:**
- High rate of MIME type mismatches (spoofing attempts)
- Path traversal attempts
- Multiple large file uploads from same user
- Unusual file type combinations

---

## Testing

### Unit Tests

```python
def test_extension_whitelist():
    # Should pass
    assert is_extension_allowed("document.pdf") == True
    assert is_extension_allowed("image.jpg") == True

    # Should fail
    assert is_extension_allowed("malicious.php") == False
    assert is_extension_allowed("script.js") == False

def test_mime_type_validation():
    # Create test file with fake extension
    with open("test.php.jpg", "wb") as f:
        f.write(b"<?php system($_GET['cmd']); ?>")

    file = FileStorage(open("test.php.jpg", "rb"), filename="test.php.jpg")
    is_valid, error = validate_mime_type(file)

    # Should reject (PHP content detected)
    assert is_valid == False
```

### Integration Tests

```python
def test_file_upload_flow():
    client = app.test_client()

    # Upload valid file
    response = client.post(
        "/form/api/v1/forms/upload",
        data={"file": (io.BytesIO(b"test content"), "test.pdf")},
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert "filename" in response.json
```

---

## Configuration Reference

### File Validator Constants

```python
# utils/file_validator.py
MAX_FILE_SIZE_IMAGE = 5 * 1024 * 1024      # 5MB
MAX_FILE_SIZE_DOCUMENT = 25 * 1024 * 1024 # 25MB
MAX_FILE_SIZE_ARCHIVE = 100 * 1024 * 1024 # 100MB
MAX_FILE_SIZE_DEFAULT = 10 * 1024 * 1024  # 10MB
```

### Settings Configuration

```python
# config/settings.py
MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16MB request limit
MAX_FILE_SIZE_FORM: int = 10 * 1024 * 1024  # 10MB form uploads
MAX_FILE_SIZE_EXPORT: int = 50 * 1024 * 1024 # 50MB exports
RATE_LIMIT_FILE_UPLOAD: str = "10 per minute"
```

---

## References

- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [CWE-434: Unrestricted Upload of File with Dangerous Type](https://cwe.mitre.org/data/definitions/434.html)
- [NIST SP 800-53: SI-10 Information Input Validation](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)
