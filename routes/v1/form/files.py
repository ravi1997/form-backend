from . import form_bp
from flasgger import swag_from
from routes.v1.form.helper import get_current_user, has_form_permission
from routes.v1.form import form_bp
from flask import current_app, request, jsonify, send_file
from flask_jwt_extended import verify_jwt_in_request, jwt_required
from mongoengine import DoesNotExist
from models import Form
import os
from logger.unified_logger import app_logger, error_logger, audit_logger
from extensions import limiter
from utils.file_handler import save_uploaded_file, save_signature
from utils.sensitive_data_redaction import safe_log_info, safe_log_error
from config.settings import settings


@form_bp.route("/<form_id>/files/<question_id>/<filename>", methods=["GET"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {
            "200": {
                "description": "Serve uploaded files. Can be accessed by users with view permissions or for public forms"
            }
        },
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True},
            {"name": "question_id", "in": "path", "type": "string", "required": True},
            {"name": "filename", "in": "path", "type": "string", "required": True},
        ],
    }
)
def get_file(form_id, question_id, filename):
    """Serve uploaded files. Can be accessed by users with view permissions or for public forms"""
    app_logger.info(
        f"Entering get_file for form_id: {form_id}, question_id: {question_id}, filename: {filename}"
    )
    try:
        # Check if the request has JWT token, if yes verify permissions
        try:
            verify_jwt_in_request()
            current_user = get_current_user()
            form = Form.objects.get(
                id=form_id, organization_id=current_user.organization_id
            )

            # User has JWT token, check permissions
            if not has_form_permission(current_user, form, "view"):
                app_logger.warning(
                    f"Unauthorized file access attempt for form_id: {form_id} by user: {getattr(current_user, 'id', 'unknown')}"
                )
                return jsonify({"error": "Unauthorized to access this form"}), 403
        except Exception:
            # No JWT token provided, check if form is public
            form = Form.objects.get(id=form_id, is_deleted=False)
            if not form.is_public:
                app_logger.warning(
                    f"Unauthorized public file access attempt for non-public form_id: {form_id}"
                )
                return jsonify({"error": "Unauthorized - form not public"}), 403

                # Check if the question is of file_upload type
                app_logger.warning(
                    f"Unauthorized public file access attempt for non-public form_id: {form_id}"
                )
                return jsonify({"error": "Unauthorized - form not public"}), 403

        # Check if the question is of file_upload type
        question_found = False
        for section in form.versions[-1].sections:
            for question in section.questions:
                if (
                    str(question.id) == str(question_id)
                    and question.field_type == "file_upload"
                ):
                    question_found = True
                    break
            if question_found:
                break

        if not question_found:
            app_logger.warning(
                f"File access denied: question {question_id} in form {form_id} is not a file upload field"
            )
            return jsonify({"error": "File access denied"}), 403

        # Build file path and verify it exists
        file_path = os.path.join(
            current_app.config.get("UPLOAD_FOLDER", "uploads"),
            str(form_id),
            str(question_id),
            filename,
        )

        if not os.path.exists(file_path):
            app_logger.warning(f"File not found on disk: {file_path}")
            return jsonify({"error": "File not found"}), 404

        app_logger.info(f"Successfully serving file: {filename} for form_id: {form_id}")
        return send_file(file_path)
    except DoesNotExist:
        app_logger.warning(f"Form not found for file access: {form_id}")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(
            f"Error serving file {filename} for form_id {form_id}: {str(e)}"
        )
        return jsonify({"error": "Error serving file"}), 500


@form_bp.route("/upload", methods=["POST"])
@swag_from({"tags": ["Form"], "responses": {"200": {"description": "Success"}}})
@jwt_required()
@limiter.limit(settings.RATE_LIMIT_FILE_UPLOAD)
def upload_file_endpoint():
    app_logger.info("Entering upload_file_endpoint")
    try:
        current_user = get_current_user()
        if "file" not in request.files:
            app_logger.warning("File upload failed: No file part in request")
            return jsonify({"error": "No file part"}), 400
        file = request.files["file"]
        if file.filename == "":
            app_logger.warning("File upload failed: No selected file")
            return jsonify({"error": "No selected file"}), 400

        # Use existing helper or save logic
        form_id = request.form.get("form_id", "common")
        field_id = request.form.get("field_id", "general")

        # Save file with validation
        file_info = save_uploaded_file(
            file, form_id, field_id, max_size=settings.MAX_FILE_SIZE_FORM
        )

        if file_info:
            safe_log_info(
                audit_logger,
                "File uploaded: %s for form_id: %s, field_id: %s by user: %s",
                filename=file_info["filename"],
                form_id=form_id,
                field_id=field_id,
                user_id=str(getattr(current_user, "id", "unknown")),
            )
            safe_log_info(
                app_logger,
                "Successfully uploaded file: %s for form_id: %s",
                file_info["filename"],
                form_id=form_id,
            )
            return (
                jsonify(
                    {
                        "url": f"/form/api/v1/forms/{form_id}/files/{field_id}/{file_info['filename']}",  # URL construction?
                        "filename": file_info["filename"],
                        "filepath": file_info["filepath"],
                        "size": file_info["size"],
                    }
                ),
                201,
            )
        else:
            safe_log_error(
                app_logger,
                "File upload failed for form_id: %s, field_id: %s",
                form_id=form_id,
                field_id=field_id,
                exc_info=True,
            )
            return jsonify({"error": "File upload failed"}), 500

    except Exception as e:
        safe_log_error(app_logger, "Upload error: %s", error=str(e), exc_info=True)
        return jsonify({"error": str(e)}), 500


@form_bp.route("/signatures", methods=["POST"])
@swag_from({"tags": ["Form"], "responses": {"200": {"description": "Success"}}})
@jwt_required()
@limiter.limit(settings.RATE_LIMIT_FILE_UPLOAD)
def upload_signature_endpoint():
    app_logger.info("Entering upload_signature_endpoint")
    try:
        current_user = get_current_user()
        data = request.get_json()
        signature_b64 = data.get("signature")
        form_id = data.get("form_id")

        if not signature_b64 or not form_id:
            app_logger.warning(
                "Signature upload failed: signature and form_id required"
            )
            return jsonify({"error": "signature and form_id required"}), 400

        # Save signature with validation
        file_info = save_signature(signature_b64, form_id)

        url = f"/form/api/v1/forms/{form_id}/files/signatures/{file_info['filename']}"

        safe_log_info(
            audit_logger,
            "Signature uploaded for form_id: %s by user: %s. Filename: %s",
            form_id=form_id,
            user_id=str(getattr(current_user, "id", "unknown")),
            filename=file_info["filename"],
        )
        safe_log_info(
            app_logger,
            "Successfully uploaded signature for form_id: %s",
            form_id=form_id,
        )
        return jsonify({"url": url, "signature_id": file_info["filename"]}), 201

    except Exception as e:
        safe_log_error(
            app_logger, "Signature upload error: %s", error=str(e), exc_info=True
        )
        return jsonify({"error": str(e)}), 500
