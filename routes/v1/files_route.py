from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from utils.response_helper import success_response, error_response
from logger.unified_logger import app_logger, error_logger

files_bp = Blueprint("files_bp", __name__)


@files_bp.route("/upload", methods=["POST"])
@jwt_required()
def upload_file_generic():
    """Handles standalone generic file uploads."""
    app_logger.info("Entering generic file upload route")
    try:
        if "file" not in request.files:
            return error_response(message="No file part in request", status_code=400)
        file = request.files["file"]
        if file.filename == "":
            return error_response(message="No selected file", status_code=400)

        # Standard lightweight save/mock return
        # In actual system, this leverages a cloud storage or local volume service
        from services.file_storage_service import FileStorageService

        storage_service = FileStorageService()
        file_url = storage_service.save_file(file)

        return success_response(
            data={"file_url": file_url},
            message="File uploaded successfully",
            status_code=201,
        )
    except Exception as e:
        error_logger.error(f"Error in upload_file_generic: {e}", exc_info=True)
        return error_response(message=str(e), status_code=500)


@files_bp.route("/signatures", methods=["POST"])
@jwt_required()
def upload_signature_generic():
    """Handles generic signature image uploads."""
    app_logger.info("Entering generic signature upload route")
    try:
        data = request.get_json() or {}
        signature_data = data.get("signature")  # Base64 representation expected
        if not signature_data:
            return error_response(message="Missing signature data", status_code=400)

        from services.file_storage_service import FileStorageService

        storage_service = FileStorageService()
        file_url = storage_service.save_base64_signature(signature_data)

        return success_response(
            data={"signature_url": file_url},
            message="Signature uploaded successfully",
            status_code=201,
        )
    except Exception as e:
        error_logger.error(f"Error in upload_signature_generic: {e}", exc_info=True)
        return error_response(message=str(e), status_code=500)
