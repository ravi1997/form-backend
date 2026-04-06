"""
utils/file_handler.py
Handles file storage with security validation.
"""

import os
import uuid
from werkzeug.datastructures import FileStorage
from flask import current_app
from logger.unified_logger import app_logger, error_logger
from utils.file_validator import validate_upload, generate_secure_filename


def save_uploaded_file(
    file: FileStorage, form_id: str, field_id: str, max_size: int = None
) -> dict:
    """
    Save uploaded file with security validation.

    Args:
        file: FileStorage object from Flask request
        form_id: Form ID for organizing uploads
        field_id: Question/Field ID for organizing uploads
        max_size: Optional custom maximum file size in bytes

    Returns:
        Dictionary with file info:
        {
            "filename": "secure_filename.ext",
            "filepath": "/full/path/to/file.ext",
            "size": 12345
        }

    Raises:
        FileUploadError: If validation fails
        Exception: If save fails
    """
    try:
        # Validate the file upload
        is_valid, error_msg = validate_upload(file, max_size=max_size)
        if not is_valid:
            app_logger.warning(f"File upload validation failed: {error_msg}")
            raise ValueError(error_msg)

        # Generate secure filename
        secure_filename = generate_secure_filename(file.filename)

        # Determine upload directory
        upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
        form_dir = os.path.join(upload_folder, str(form_id), str(field_id))

        # Create directory if it doesn't exist
        os.makedirs(form_dir, exist_ok=True)

        # Save the file
        filepath = os.path.join(form_dir, secure_filename)
        file.save(filepath)

        # Get file size
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
        # Re-raise validation errors
        raise
    except Exception as e:
        error_logger.error(
            f"Error saving file {file.filename}: {str(e)}", exc_info=True
        )
        raise


def save_signature(signature_b64: str, form_id: str) -> dict:
    """
    Save signature from base64 string.

    Args:
        signature_b64: Base64-encoded signature data
        form_id: Form ID for organizing signatures

    Returns:
        Dictionary with file info:
        {
            "filename": "sig_uuid.png",
            "filepath": "/full/path/to/sig_uuid.png"
        }
    """
    import base64

    try:
        # Remove header if present
        if "," in signature_b64:
            signature_b64 = signature_b64.split(",")[1]

        # Decode base64
        file_data = base64.b64decode(signature_b64)

        # Generate filename
        filename = f"sig_{uuid.uuid4().hex}.png"

        # Determine upload directory
        upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
        save_path = os.path.join(upload_folder, str(form_id), "signatures")
        os.makedirs(save_path, exist_ok=True)

        # Save the file
        filepath = os.path.join(save_path, filename)
        with open(filepath, "wb") as f:
            f.write(file_data)

        app_logger.info(f"Signature saved successfully: {filename} for form {form_id}")

        return {
            "filename": filename,
            "filepath": filepath,
        }

    except Exception as e:
        error_logger.error(
            f"Error saving signature for form {form_id}: {str(e)}", exc_info=True
        )
        raise


def delete_file(filepath: str) -> bool:
    """
    Safely delete a file.

    Args:
        filepath: Full path to file

    Returns:
        True if successful, False otherwise
    """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            app_logger.info(f"File deleted: {filepath}")
            return True
        return False
    except Exception as e:
        error_logger.error(f"Error deleting file {filepath}: {str(e)}", exc_info=True)
        return False
