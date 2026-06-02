import os
import uuid
import base64
from werkzeug.datastructures import FileStorage
from flask import current_app
from logger.unified_logger import app_logger, error_logger
from utils.file_validator import validate_upload, generate_secure_filename
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from config.settings import settings

class FileStorageService:
    """
    Secure file storage service providing tenant isolation, filename validation,
    and HMAC-based temporary signed URL generation/verification.
    """

    def __init__(self, upload_folder: str = None):
        self.upload_folder = upload_folder or current_app.config.get("UPLOAD_FOLDER", "uploads")
        self.serializer = URLSafeTimedSerializer(
            settings.JWT_SECRET_KEY,
            salt="file-download-salt"
        )

    def _get_tenant_path(self, organization_id: str, form_id: str = "generic", question_id: str = "generic") -> str:
        """Determines the tenant-isolated directory path."""
        # Clean paths to prevent traversal
        safe_org = generate_secure_filename(organization_id)
        safe_form = generate_secure_filename(form_id)
        safe_question = generate_secure_filename(question_id)
        
        path = os.path.join(self.upload_folder, safe_org, safe_form, safe_question)
        os.makedirs(path, exist_ok=True)
        return path

    def save_file(self, file: FileStorage, organization_id: str, form_id: str = "generic", question_id: str = "generic") -> str:
        """Validates and saves an uploaded file in a tenant-isolated path."""
        is_valid, error_msg = validate_upload(file)
        if not is_valid:
            app_logger.warning(f"File upload validation failed: {error_msg}")
            raise ValueError(error_msg)

        secure_filename = generate_secure_filename(file.filename)
        # Prevent collisions by appending a unique UUID segment
        name_parts = os.path.splitext(secure_filename)
        unique_filename = f"{name_parts[0]}_{uuid.uuid4().hex}{name_parts[1]}"

        tenant_dir = self._get_tenant_path(organization_id, form_id, question_id)
        filepath = os.path.join(tenant_dir, unique_filename)
        file.save(filepath)

        app_logger.info(
            f"File saved successfully: {unique_filename} for organization {organization_id}"
        )
        return self.generate_signed_url(organization_id, form_id, question_id, unique_filename)

    def save_base64_signature(self, signature_data: str, organization_id: str, form_id: str = "generic") -> str:
        """Decodes and saves a base64 encoded signature image."""
        try:
            if "," in signature_data:
                signature_data = signature_data.split(",")[1]

            file_data = base64.b64decode(signature_data)
            filename = f"sig_{uuid.uuid4().hex}.png"

            tenant_dir = self._get_tenant_path(organization_id, form_id, "signatures")
            filepath = os.path.join(tenant_dir, filename)
            with open(filepath, "wb") as f:
                f.write(file_data)

            app_logger.info(f"Signature saved successfully: {filename} for organization {organization_id}")
            return self.generate_signed_url(organization_id, form_id, "signatures", filename)
        except Exception as e:
            error_logger.error(f"Error saving signature: {str(e)}", exc_info=True)
            raise

    def generate_signed_url(self, organization_id: str, form_id: str, question_id: str, filename: str, expires_in: int = 3600) -> str:
        """Generates a secure timed signed URL for downloading files."""
        token_payload = {
            "org": organization_id,
            "form": form_id,
            "q": question_id,
            "file": filename
        }
        token = self.serializer.dumps(token_payload)
        
        # Build API endpoint url matching our route structure
        api_prefix = "/mahasangraha/api/v1"
        return f"{api_prefix}/files/download?token={token}"

    def verify_signed_url(self, token: str) -> dict:
        """
        Verifies a signed token and returns the payload containing file identifiers.
        Raises ValueError if signature is invalid or expired.
        """
        try:
            # Token expires after 1 hour (3600s) by default
            payload = self.serializer.loads(token, max_age=3600)
            return payload
        except SignatureExpired:
            app_logger.warning("File download token has expired")
            raise ValueError("Token has expired")
        except BadSignature:
            app_logger.warning("Invalid file download token signature")
            raise ValueError("Invalid signature")
