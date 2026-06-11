"""
utils/file_validator.py
Comprehensive file upload security validation.
Implements OWASP recommendations for file upload security.
"""

import os
import uuid

# Try to import magic, but make it optional
try:
    import magic
    HAS_MAGIC = True
except (ImportError, OSError):
    # libmagic not available, we'll use fallback methods
    HAS_MAGIC = False
from typing import Optional, Tuple, List
from werkzeug.datastructures import FileStorage
from flask import current_app
from logger.unified_logger import app_logger, error_logger

# Allowed file extensions for file uploads (WHITELIST approach)
ALLOWED_EXTENSIONS = {
    # Images
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".webp",
    ".svg",
    ".ico",
    # Documents
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".odt",
    ".ods",
    ".odp",
    ".txt",
    ".rtf",
    ".csv",
    # Archives
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
}

# MIME types that are allowed for each extension
ALLOWED_MIME_TYPES = {
    # Images
    ".jpg": ["image/jpeg"],
    ".jpeg": ["image/jpeg"],
    ".png": ["image/png"],
    ".gif": ["image/gif"],
    ".bmp": ["image/bmp"],
    ".webp": ["image/webp"],
    ".svg": ["image/svg+xml"],
    ".ico": ["image/x-icon", "image/vnd.microsoft.icon"],
    # Documents
    ".pdf": ["application/pdf"],
    ".doc": ["application/msword"],
    ".docx": [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ],
    ".xls": ["application/vnd.ms-excel"],
    ".xlsx": ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
    ".ppt": ["application/vnd.ms-powerpoint"],
    ".pptx": [
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ],
    ".odt": ["application/vnd.oasis.opendocument.text"],
    ".ods": ["application/vnd.oasis.opendocument.spreadsheet"],
    ".odp": ["application/vnd.oasis.opendocument.presentation"],
    ".txt": ["text/plain"],
    ".rtf": ["application/rtf", "text/rtf"],
    ".csv": ["text/csv", "application/csv"],
    # Archives
    ".zip": ["application/zip", "application/x-zip-compressed"],
    ".rar": ["application/vnd.rar", "application/x-rar-compressed"],
    ".7z": ["application/x-7z-compressed"],
    ".tar": ["application/x-tar"],
    ".gz": ["application/gzip", "application/x-gzip"],
}

# Dangerous file extensions that should NEVER be allowed
BLOCKED_EXTENSIONS = {
    ".php",
    ".php3",
    ".php4",
    ".php5",
    ".phtml",
    ".jsp",
    ".jspx",
    ".jsw",
    ".jsv",
    ".jspf",
    ".asp",
    ".aspx",
    ".asa",
    ".asax",
    ".ascx",
    ".ashx",
    ".asmx",
    ".cer",
    ".a_sp",
    ".a_sp_x",
    ".cdx",
    ".rem",
    ".resx",
    ".shtm",
    ".shtml",
    ".stm",
    ".exe",
    ".bat",
    ".cmd",
    ".com",
    ".scr",
    ".pif",
    ".vbs",
    ".js",
    ".jar",
    ".sh",
    ".ps1",
    ".ps2",
    ".ps1xml",
    ".ps2xml",
    ".psc1",
    ".psc2",
    ".msi",
    ".msp",
    ".mst",
    ".cpl",
    ".msc",
    ".appx",
    ".appbundle",
    ".deb",
    ".rpm",
    ".dmg",
    ".pkg",
    ".elf",
}

# Maximum file sizes (in bytes)
MAX_FILE_SIZE_IMAGE = 5 * 1024 * 1024  # 5MB
MAX_FILE_SIZE_DOCUMENT = 25 * 1024 * 1024  # 25MB
MAX_FILE_SIZE_ARCHIVE = 100 * 1024 * 1024  # 100MB
MAX_FILE_SIZE_DEFAULT = 10 * 1024 * 1024  # 10MB

# Dangerous file signatures (magic bytes)
DANGEROUS_SIGNATURES = [
    b"MZ",  # Windows executable
    b"\x7fELF",  # Linux/Unix executable
    b"PK\x03\x04",  # ZIP (already allowed but check content)
    b"\xca\xfe\xba\xbe",  # Mach-O (macOS)
]


class FileUploadError(Exception):
    """Custom exception for file upload validation errors."""

    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code


def get_file_extension(filename: str) -> str:
    """Get lowercase file extension from filename."""
    _, ext = os.path.splitext(filename.lower())
    return ext


def is_extension_blocked(filename: str) -> bool:
    """Check if file extension is in blocked list."""
    ext = get_file_extension(filename)
    return ext in BLOCKED_EXTENSIONS


def is_extension_allowed(filename: str) -> bool:
    """Check if file extension is in allowed whitelist."""
    ext = get_file_extension(filename)
    return ext in ALLOWED_EXTENSIONS


def validate_mime_type(file: FileStorage) -> Tuple[bool, Optional[str]]:
    """
    Validate file MIME type against declared content type.
    Returns (is_valid, error_message).
    """
    if not file or not file.filename:
        return False, "No file provided"

    ext = get_file_extension(file.filename)
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"File extension {ext} is not allowed"

    try:
        # Read first few bytes to detect actual MIME type
        file_content = file.read(2048)
        file.seek(0)  # Reset file pointer

        # Use python-magic to detect actual MIME type
        if HAS_MAGIC:
            detected_mime = magic.from_buffer(file_content, mime=True)
        else:
            # Fallback: use extension-based MIME type
            detected_mime = ALLOWED_MIME_TYPES.get(ext, ['application/octet-stream'])[0]

        # Check if detected MIME is allowed for this extension
        allowed_mimes = ALLOWED_MIME_TYPES.get(ext, [])

        if detected_mime not in allowed_mimes:
            error_logger.warning(
                f"MIME type mismatch for {file.filename}: "
                f"declared={file.content_type}, detected={detected_mime}, allowed={allowed_mimes}"
            )
            return False, (
                f"File content type {detected_mime} does not match "
                f"allowed types for {ext}: {', '.join(allowed_mimes)}"
            )

        return True, None

    except Exception as e:
        error_logger.error(
            f"Error validating MIME type for {file.filename}: {str(e)}", exc_info=True
        )
        return False, "Error validating file type"


def validate_file_size(
    file: FileStorage, max_size: Optional[int] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate file size against limits.
    Returns (is_valid, error_message).
    """
    if not file:
        return False, "No file provided"

    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)  # Reset file pointer

    # Determine max size based on file type
    if max_size:
        if file_size > max_size:
            max_mb = max_size / (1024 * 1024)
            file_mb = file_size / (1024 * 1024)
            return (
                False,
                f"File size ({file_mb:.2f}MB) exceeds maximum allowed ({max_mb:.2f}MB)",
            )
    else:
        ext = get_file_extension(file.filename)
        if ext in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico"}:
            max_allowed = MAX_FILE_SIZE_IMAGE
        elif ext in {".zip", ".rar", ".7z", ".tar", ".gz"}:
            max_allowed = MAX_FILE_SIZE_ARCHIVE
        else:
            max_allowed = MAX_FILE_SIZE_DOCUMENT

        if file_size > max_allowed:
            max_mb = max_allowed / (1024 * 1024)
            file_mb = file_size / (1024 * 1024)
            return (
                False,
                f"File size ({file_mb:.2f}MB) exceeds maximum allowed ({max_mb:.2f}MB)",
            )

    return True, None


def validate_filename(filename: str) -> Tuple[bool, Optional[str]]:
    """
    Validate filename for security issues.
    Returns (is_valid, error_message).
    """
    if not filename:
        return False, "No filename provided"

    # Check for path traversal
    if ".." in filename or filename.startswith("/"):
        return False, "Invalid filename: path traversal detected"

    # Check for null bytes
    if "\x00" in filename:
        return False, "Invalid filename: null bytes detected"

    # Check length
    if len(filename) > 255:
        return False, "Filename too long (max 255 characters)"

    # Check for suspicious patterns
    dangerous_patterns = [
        "con",
        "prn",
        "aux",
        "nul",
        "com1",
        "com2",
        "com3",
        "com4",
        "com5",
        "com6",
        "com7",
        "com8",
        "com9",
        "lpt1",
        "lpt2",
        "lpt3",
        "lpt4",
        "lpt5",
        "lpt6",
        "lpt7",
        "lpt8",
        "lpt9",
    ]
    lower_name = filename.lower()
    for pattern in dangerous_patterns:
        if pattern in lower_name.split(".")[0]:
            return False, f"Invalid filename: '{pattern}' is a reserved name"

    return True, None


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing/replacing dangerous characters.
    Keeps the extension but cleans the name part.
    """
    if not filename:
        return f"unnamed_{uuid.uuid4().hex[:8]}"

    name, ext = os.path.splitext(filename)

    # Remove or replace dangerous characters
    name = "".join(c for c in name if c.isalnum() or c in "._- ")
    name = name.strip(" ._")

    # If empty after sanitization, generate a random name
    if not name:
        name = uuid.uuid4().hex[:8]

    return f"{name}{ext}"


def validate_upload(
    file: FileStorage,
    max_size: Optional[int] = None,
    allowed_extensions: Optional[List[str]] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Comprehensive file upload validation.
    Performs all security checks in sequence.

    Args:
        file: FileStorage object from Flask request
        max_size: Optional custom maximum file size in bytes
        allowed_extensions: Optional custom list of allowed extensions

    Returns:
        Tuple of (is_valid, error_message)

    Raises:
        FileUploadError: If validation fails (with error_code)
    """
    if not file or not file.filename:
        raise FileUploadError("No file provided", "NO_FILE")

    # 1. Validate filename
    filename_valid, filename_error = validate_filename(file.filename)
    if not filename_valid:
        raise FileUploadError(filename_error, "INVALID_FILENAME")

    # 2. Check extension is not blocked
    if is_extension_blocked(file.filename):
        raise FileUploadError(
            f"File type {get_file_extension(file.filename)} is not allowed",
            "BLOCKED_EXTENSION",
        )

    # 3. Check extension is allowed (whitelist)
    if allowed_extensions:
        ext = get_file_extension(file.filename)
        if ext not in allowed_extensions:
            raise FileUploadError(
                f"Only {', '.join(allowed_extensions)} files are allowed",
                "EXTENSION_NOT_ALLOWED",
            )
    elif not is_extension_allowed(file.filename):
        raise FileUploadError(
            f"File type {get_file_extension(file.filename)} is not allowed",
            "EXTENSION_NOT_ALLOWED",
        )

    # 4. Validate MIME type (content-type spoofing protection)
    mime_valid, mime_error = validate_mime_type(file)
    if not mime_valid:
        raise FileUploadError(mime_error, "INVALID_MIME_TYPE")

    # 5. Validate file size
    size_valid, size_error = validate_file_size(file, max_size)
    if not size_valid:
        raise FileUploadError(size_error, "FILE_TOO_LARGE")

    app_logger.info(f"File {file.filename} passed all security validations")
    return True, None


def generate_secure_filename(filename: str) -> str:
    """
    Generate a secure filename by sanitizing and adding UUID.
    Preserves the original extension.
    """
    # First sanitize the filename
    sanitized = sanitize_filename(filename)

    # Get the extension
    name, ext = os.path.splitext(sanitized)

    # Add UUID to prevent filename collisions
    uuid_suffix = uuid.uuid4().hex[:12]

    return f"{name}_{uuid_suffix}{ext}"
