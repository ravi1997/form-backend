# File Handling Security

**Purpose:** Documentation for secure file storage, organization, and cleanup procedures.

**Scope:** File storage architecture, directory structure, security validation, cleanup policies, and upload workflow.

---

## Overview

The file handling system provides secure storage for user-uploaded files including documents, images, and signatures. Files are organized by form and field IDs for easy isolation and cleanup, with comprehensive security validation before storage.

**Key Components:**
- `utils/file_handler.py` - Secure file storage handler (153 lines)
- `utils/file_validator.py` - File validation (420 lines)
- Integrated storage with MongoDB document references

---

## File Storage Architecture

### Directory Structure

```
uploads/
├── form_id_1/                    # Tenant + form isolation
│   ├── field_id_1/              # Field-level organization
│   │   ├── file_abc123.pdf
│   │   ├── file_def456.jpg
│   │   └── file_ghi789.png
│   ├── field_id_2/
│   │   ├── file_jkl012.docx
│   │   └── file_mno345.xlsx
│   └── signatures/               # Separate signature storage
│       ├── sig_pqr678.png
│       └── sig_stu901.png
├── form_id_2/
│   └── ...
└── exports/                      # Temporary export files
    ├── export_123.csv
    └── export_456.json
```

### Isolation Benefits

1. **Tenant Isolation:** Files organized by form_id (organization-scoped)
2. **Field Organization:** Easy to find files for specific questions
3. **Cleanup Efficiency:** Delete entire form directory when form is deleted
4. **Access Control:** Verify form_id before serving files

---

## Upload Workflow

### Complete Flow

```
1. User uploads file via POST /forms/upload
   ↓
2. Flask validates MAX_CONTENT_LENGTH
   ↓
3. file_validator.validate_upload() checks:
   - Filename validation (path traversal, null bytes)
   - Extension whitelist/blocklist
   - MIME type detection (python-magic)
   - File size limits
   ↓
4. generate_secure_filename() creates safe filename
   ↓
5. save_uploaded_file() saves to organized directory:
   - Create directory structure if needed
   - Save file with secure filename
   - Return file metadata
   ↓
6. Store file reference in MongoDB
   ↓
7. Return file info to client
```

### Implementation

```python
from utils.file_handler import save_uploaded_file
from utils.file_validator import validate_upload, FileUploadError

@bp.route("/upload", methods=["POST"])
@jwt_required()
def upload_file():
    try:
        # 1. Get file from request
        file = request.files.get("file")
        form_id = request.json.get("form_id")
        field_id = request.json.get("field_id")

        # 2. Validate file upload
        is_valid, error = validate_upload(file, max_size=10*1024*1024)
        if not is_valid:
            return error_response(message=error, status_code=400)

        # 3. Save file securely
        file_info = save_uploaded_file(file, form_id, field_id)

        # 4. Store reference in database
        file_reference = {
            "form_id": form_id,
            "field_id": field_id,
            "filename": file_info["filename"],
            "filepath": file_info["filepath"],
            "size": file_info["size"],
            "uploaded_at": datetime.utcnow(),
            "uploaded_by": get_current_user().id
        }

        # Save to appropriate collection

        return success_response(data=file_info)

    except FileUploadError as e:
        audit_logger.warning(f"File upload failed: {e.error_code}")
        return error_response(message=str(e), status_code=400)
```

---

## File Validation Integration

### Pre-Storage Validation

```python
def save_uploaded_file(
    file: FileStorage,
    form_id: str,
    field_id: str,
    max_size: int = None
) -> dict:
    """Save uploaded file with security validation."""
    try:
        # 1. Validate file upload
        is_valid, error_msg = validate_upload(file, max_size=max_size)
        if not is_valid:
            raise ValueError(error_msg)

        # 2. Generate secure filename
        secure_filename = generate_secure_filename(file.filename)

        # 3. Determine upload directory
        upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
        form_dir = os.path.join(upload_folder, str(form_id), str(field_id))

        # 4. Create directory if it doesn't exist
        os.makedirs(form_dir, exist_ok=True)

        # 5. Save file
        filepath = os.path.join(form_dir, secure_filename)
        file.save(filepath)

        # 6. Get file size
        file_size = os.path.getsize(filepath)

        app_logger.info(
            f"File saved successfully: {secure_filename} ({file_size} bytes) "
            f"for form {form_id}, field {field_id}"
        )

        return {
            "filename": secure_filename,
            "filepath": filepath,
            "size": file_size,
        }

    except ValueError as e:
        raise
    except Exception as e:
        error_logger.error(
            f"Error saving file {file.filename}: {str(e)}", exc_info=True
        )
        raise
```

---

## Signature Handling

### Signature Upload

```python
def save_signature(signature_b64: str, form_id: str) -> dict:
    """Save signature from base64 string."""
    import base64

    try:
        # 1. Remove header if present
        if "," in signature_b64:
            signature_b64 = signature_b64.split(",")[1]

        # 2. Decode base64
        file_data = base64.b64decode(signature_b64)

        # 3. Generate filename
        filename = f"sig_{uuid.uuid4().hex}.png"

        # 4. Determine upload directory
        upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
        save_path = os.path.join(upload_folder, str(form_id), "signatures")
        os.makedirs(save_path, exist_ok=True)

        # 5. Save file
        filepath = os.path.join(save_path, filename)
        with open(filepath, "wb") as f:
            f.write(file_data)

        app_logger.info(f"Signature saved: {filename} for form {form_id}")

        return {
            "filename": filename,
            "filepath": filepath,
        }

    except Exception as e:
        error_logger.error(
            f"Error saving signature for form {form_id}: {str(e)}", exc_info=True
        )
        raise
```

### Usage

```python
@bp.route("/signatures", methods=["POST"])
@jwt_required()
def upload_signature():
    signature_data = request.json.get("signature")
    form_id = request.json.get("form_id")

    # Save signature
    signature_info = save_signature(signature_data, form_id)

    return success_response(data=signature_info)
```

---

## File Deletion

### Safe File Deletion

```python
def delete_file(filepath: str) -> bool:
    """Safely delete a file."""
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            app_logger.info(f"File deleted: {filepath}")
            return True
        return False
    except Exception as e:
        error_logger.error(
            f"Error deleting file {filepath}: {str(e)}", exc_info=True
        )
        return False
```

### Form-Level Cleanup

```python
def delete_form_files(form_id: str):
    """Delete all files for a form."""
    try:
        upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
        form_dir = os.path.join(upload_folder, str(form_id))

        if os.path.exists(form_dir):
            shutil.rmtree(form_dir)
            app_logger.info(f"Deleted all files for form {form_id}")
            return True

        return False

    except Exception as e:
        error_logger.error(
            f"Error deleting form files {form_id}: {str(e)}", exc_info=True
        )
        return False
```

### Field-Level Cleanup

```python
def delete_field_files(form_id: str, field_id: str):
    """Delete all files for a specific field."""
    try:
        upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
        field_dir = os.path.join(upload_folder, str(form_id), str(field_id))

        if os.path.exists(field_dir):
            shutil.rmtree(field_dir)
            app_logger.info(
                f"Deleted field files for form {form_id}, field {field_id}"
            )
            return True

        return False

    except Exception as e:
        error_logger.error(
            f"Error deleting field files {form_id}/{field_id}: {str(e)}",
            exc_info=True
        )
        return False
```

---

## File Serving

### Secure File Serving

```python
@bp.route("/<form_id>/files/<field_id>/<filename>", methods=["GET"])
def serve_file(form_id, field_id, filename):
    """Serve file with access control."""
    try:
        # 1. Verify user has permission to access form
        user = get_current_user()
        form = Form.objects.get(
            id=form_id,
            organization_id=user.organization_id,
            is_deleted=False
        )

        # 2. Verify file exists
        upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
        filepath = os.path.join(
            upload_folder,
            str(form_id),
            str(field_id),
            filename
        )

        if not os.path.exists(filepath):
            return error_response(message="File not found", status_code=404)

        # 3. Send file with proper headers
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename
        )

    except Form.DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(
            f"Error serving file {filename}: {str(e)}", exc_info=True
        )
        return error_response(message="Error serving file", status_code=500)
```

---

## Storage Configuration

### Upload Folder Configuration

```python
# config/settings.py
UPLOAD_FOLDER: str = os.environ.get("UPLOAD_FOLDER", "uploads")

# app.py
app.config["UPLOAD_FOLDER"] = settings.UPLOAD_FOLDER
```

### File Size Limits

```python
# config/settings.py
MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16MB request limit
MAX_FILE_SIZE_FORM: int = 10 * 1024 * 1024  # 10MB form uploads
MAX_FILE_SIZE_EXPORT: int = 50 * 1024 * 1024 # 50MB exports
```

---

## Best Practices

### 1. Always Validate Before Saving

```python
# CORRECT
is_valid, error = validate_upload(file)
if not is_valid:
    return error_response(message=error, status_code=400)
save_uploaded_file(file, form_id, field_id)

# WRONG
save_uploaded_file(file, form_id, field_id)  # No validation
```

### 2. Use Organized Directory Structure

```python
# CORRECT - Organized by form and field
filepath = os.path.join(upload_dir, str(form_id), str(field_id), filename)

# WRONG - Flat structure (hard to manage)
filepath = os.path.join(upload_dir, filename)
```

### 3. Generate Secure Filenames

```python
# CORRECT - UUID suffix prevents collisions
secure_filename = generate_secure_filename(file.filename)

# WRONG - Original filename (collision risk)
filepath = os.path.join(upload_dir, file.filename)
```

### 4. Delete Files When Deleting Resources

```python
# CORRECT - Delete files when form is deleted
@bp.route("/<form_id>", methods=["DELETE"])
def delete_form(form_id):
    # Delete database record
    form.update(set__is_deleted=True)

    # Delete associated files
    delete_form_files(form_id)

    return success_response(message="Form deleted")

# WRONG - Leaves orphaned files
@bp.route("/<form_id>", methods=["DELETE"])
def delete_form(form_id):
    form.update(set__is_deleted=True)
    return success_response(message="Form deleted")
```

### 5. Log File Operations

```python
# CORRECT - Log file operations
app_logger.info(f"File uploaded: {filename} ({size} bytes)")
app_logger.info(f"File deleted: {filepath}")

# WRONG - No logging (audit trail missing)
file.save(filepath)
```

---

## Security Considerations

### 1. Path Traversal Prevention

**Attack:** `../../../../etc/passwd`

**Defense:**
```python
# Use os.path.join() for safe path construction
filepath = os.path.join(upload_dir, str(form_id), str(field_id), filename)

# Filename validation in file_validator.py prevents ".." and leading "/"
```

### 2. File Size DoS Prevention

**Attack:** Upload extremely large files to exhaust disk space

**Defense:**
- Flask `MAX_CONTENT_LENGTH` limit
- Per-file-type size limits
- Early validation before file read

### 3. MIME Type Spoofing Prevention

**Attack:** Rename `malicious.php` to `image.jpg`

**Defense:**
```python
# Detect actual MIME type using python-magic
detected_mime = magic.from_buffer(file_content, mime=True)

# Validate against allowed types for extension
if detected_mime not in allowed_mimes:
    raise FileUploadError("MIME type mismatch")
```

### 4. File Access Control

**Attack:** Access files for other users' forms

**Defense:**
```python
# Verify form ownership before serving
form = Form.objects.get(
    id=form_id,
    organization_id=user.organization_id
)
```

---

## Cleanup Policies

### Automated Cleanup (Future)

```python
# TODO: Implement background task for cleanup
def cleanup_old_files():
    """Delete files older than retention period."""
    retention_days = 30

    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    # Find deleted forms
    deleted_forms = Form.objects(
        is_deleted=True,
        deleted_at__lt=cutoff_date
    )

    # Delete their files
    for form in deleted_forms:
        delete_form_files(str(form.id))

    app_logger.info(f"Cleanup complete: {len(deleted_forms)} forms")
```

### Export File Cleanup

```python
# TODO: Implement cleanup for temporary export files
def cleanup_export_files():
    """Delete export files older than 24 hours."""
    export_dir = os.path.join(settings.UPLOAD_FOLDER, "exports")
    cutoff_time = time.time() - (24 * 3600)

    for filename in os.listdir(export_dir):
        filepath = os.path.join(export_dir, filename)
        if os.path.getmtime(filepath) < cutoff_time:
            os.remove(filepath)
            app_logger.info(f"Deleted old export: {filename}")
```

---

## Testing

### Unit Tests

```python
def test_file_upload():
    from utils.file_handler import save_uploaded_file
    from io import BytesIO

    # Create test file
    test_file = FileStorage(
        stream=BytesIO(b"test content"),
        filename="test.pdf",
        content_type="application/pdf"
    )

    # Save file
    file_info = save_uploaded_file(test_file, "form123", "field456")

    assert file_info["filename"].endswith(".pdf")
    assert os.path.exists(file_info["filepath"])
    assert file_info["size"] > 0

def test_signature_upload():
    from utils.file_handler import save_signature

    # Create signature data
    import base64
    signature_b64 = "data:image/png;base64,iVBORw0KGgoAAAANS..."

    # Save signature
    signature_info = save_signature(signature_b64, "form123")

    assert signature_info["filename"].startswith("sig_")
    assert signature_info["filename"].endswith(".png")
    assert os.path.exists(signature_info["filepath"])
```

---

## Configuration Reference

### File Handler Configuration

```python
# config/settings.py
UPLOAD_FOLDER: str = os.environ.get("UPLOAD_FOLDER", "uploads")
MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024
MAX_FILE_SIZE_FORM: int = 10 * 1024 * 1024
MAX_FILE_SIZE_EXPORT: int = 50 * 1024 * 1024
```

---

## References

- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [NIST SP 800-53: SI-10 Information Input Validation](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)
- [CWE-434: Unrestricted Upload of File with Dangerous Type](https://cwe.mitre.org/data/definitions/434.html)
- [Python pathlib Documentation](https://docs.python.org/3/library/pathlib.html)
