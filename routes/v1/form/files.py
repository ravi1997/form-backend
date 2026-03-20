from . import form_bp
from flasgger import swag_from
from routes.v1.form.helper import get_current_user, has_form_permission
from routes.v1.form import form_bp
from flask import current_app, request, jsonify, send_file
from flask_jwt_extended import verify_jwt_in_request, jwt_required
from mongoengine import DoesNotExist
from models import Form
import os


@form_bp.route("/<form_id>/files/<question_id>/<filename>", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Serve uploaded files. Can be accessed by users with view permissions or for public forms"
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": true
        },
        {
            "name": "question_id",
            "in": "path",
            "type": "string",
            "required": true
        },
        {
            "name": "filename",
            "in": "path",
            "type": "string",
            "required": true
        }
    ]
})
def get_file(form_id, question_id, filename):
    """Serve uploaded files. Can be accessed by users with view permissions or for public forms"""
    try:
        # Check if the request has JWT token, if yes verify permissions
        try:
            verify_jwt_in_request()
            current_user = get_current_user()
            form = Form.objects.get(id=form_id)

            # User has JWT token, check permissions
            if not has_form_permission(current_user, form, "view"):
                return jsonify({"error": "Unauthorized to access this form"}), 403
        except Exception:
            # No JWT token provided, check if form is public
            form = Form.objects.get(id=form_id)
            if not form.is_public:
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
            return jsonify({"error": "File access denied"}), 403

        # Build file path and verify it exists
        file_path = os.path.join(
            current_app.config.get("UPLOAD_FOLDER", "uploads"),
            str(form_id),
            str(question_id),
            filename,
        )

        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404

        return send_file(file_path)
    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        current_app.logger.error(f"Error serving file: {str(e)}")
        return jsonify({"error": "Error serving file"}), 500


@jwt_required()
@form_bp.route("/upload", methods=["POST"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
def upload_file_endpoint():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file part"}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400

        # Use existing helper or save logic
        # We need form_id to organize files, usually passed in form data?
        # Or generic upload?
        # api_endpoints.dart says: Body: FormData with file
        # Doesn't explicitly say form_id is required, but usually is for organization.
        # If not provided, maybe a temp folder?
        form_id = request.form.get("form_id", "common")
        field_id = request.form.get("field_id", "general")

        # We need to import save_uploaded_file from somewhere.
        # It's used in responses.py. imported from utils.file_handler
        from utils.file_handler import save_uploaded_file

        file_info = save_uploaded_file(file, form_id, field_id)

        if file_info:
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
            return jsonify({"error": "File upload failed"}), 500

    except Exception as e:
        current_app.logger.error(f"Upload error: {str(e)}")
        return jsonify({"error": str(e)}), 500


@form_bp.route("/signatures", methods=["POST"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
def upload_signature_endpoint():
    try:
        data = request.get_json()
        signature_b64 = data.get("signature")
        form_id = data.get("form_id")

        if not signature_b64 or not form_id:
            return jsonify({"error": "signature and form_id required"}), 400

        # Decode and save
        import base64
        import uuid
        import os

        # Remove header if present
        if "," in signature_b64:
            signature_b64 = signature_b64.split(",")[1]

        file_data = base64.b64decode(signature_b64)
        filename = f"sig_{uuid.uuid4().hex}.png"

        upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
        save_path = os.path.join(upload_folder, str(form_id), "signatures")
        os.makedirs(save_path, exist_ok=True)

        filepath = os.path.join(save_path, filename)
        with open(filepath, "wb") as f:
            f.write(file_data)

        url = f"/form/api/v1/forms/{form_id}/files/signatures/{filename}"  # Check consistency

        return jsonify({"url": url, "signature_id": filename}), 201

    except Exception as e:
        current_app.logger.error(f"Signature upload error: {str(e)}")
        return jsonify({"error": str(e)}), 500
