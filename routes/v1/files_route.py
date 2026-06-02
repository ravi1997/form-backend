from flask import Blueprint, request, send_file
from flask_jwt_extended import jwt_required, current_user
from utils.response_helper import success_response, error_response
from logger.unified_logger import app_logger, error_logger
import os

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

        from services.file_storage_service import FileStorageService

        storage_service = FileStorageService()
        file_url = storage_service.save_file(
            file=file,
            organization_id=current_user.organization_id,
            form_id=request.form.get("form_id", "generic"),
            question_id=request.form.get("question_id", "generic")
        )

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
        file_url = storage_service.save_base64_signature(
            signature_data=signature_data,
            organization_id=current_user.organization_id,
            form_id=data.get("form_id", "generic")
        )

        return success_response(
            data={"signature_url": file_url},
            message="Signature uploaded successfully",
            status_code=201,
        )
    except Exception as e:
        error_logger.error(f"Error in upload_signature_generic: {e}", exc_info=True)
        return error_response(message=str(e), status_code=500)


@files_bp.route("/download", methods=["GET"])
def download_file_signed():
    """Serves files using secure HMAC signed tokens."""
    token = request.args.get("token")
    if not token:
        return error_response(message="Missing download token", status_code=400)

    try:
        from services.file_storage_service import FileStorageService

        storage_service = FileStorageService()
        payload = storage_service.verify_signed_url(token)

        org_id = payload["org"]
        form_id = payload["form"]
        question_id = payload["q"]
        filename = payload["file"]

        # Prevent directory traversal
        if any(part in {"..", "/", "\\"} or not part for part in [org_id, form_id, question_id, filename]):
            return error_response(message="Invalid path components", status_code=400)

        file_path = os.path.join(
            storage_service.upload_folder,
            org_id,
            form_id,
            question_id,
            filename
        )

        if not os.path.exists(file_path):
            return error_response(message="File not found", status_code=404)

        return send_file(file_path)
    except ValueError as val_err:
        return error_response(message=str(val_err), status_code=403)
    except Exception as e:
        error_logger.error(f"Error in download_file_signed: {e}", exc_info=True)
        return error_response(message="Internal server error serving file", status_code=500)
