from . import form_bp
from flasgger import swag_from
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import CustomFieldTemplate, Question, Form
from routes.v1.form.helper import get_current_user, has_form_permission
from logger.unified_logger import app_logger, error_logger, audit_logger
import traceback

library_bp = Blueprint("library", __name__)


@library_bp.route("/", methods=["GET"])
@swag_from({
    "tags": [
        "Library"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
def list_field_templates():
    app_logger.info("Entering list_field_templates")
    try:
        current_user_id = get_jwt_identity()
        category = request.args.get("category")

        query = {"user_id": str(current_user_id)}
        if category:
            query["category"] = category

        templates = CustomFieldTemplate.objects(**query)
        result = []
        for t in templates:
            data = (
                dict(t.data)
                if hasattr(t, "data") and t.data
                else (
                    t.question_data.to_mongo().to_dict()
                    if hasattr(t, "question_data") and t.question_data
                    else {}
                )
            )

            description = data.get("description", "")
            tags = data.get("tags", [])

            result.append(
                {
                    "id": str(t.id),
                    "name": t.name,
                    "description": description,
                    "category": t.category,
                    "tags": tags,
                    "template_type": getattr(t, "template_type", "question"),
                    "data": data,
                    "form": data,  # Alias for frontend FormTemplate
                    "created_at": t.created_at.isoformat(),
                }
            )

        app_logger.info(f"Listed {len(result)} field templates for user {current_user_id}")
        if "templates" in request.path:
            return jsonify({"templates": result}), 200
        return jsonify(result), 200
    except Exception as e:
        error_logger.error(f"Error listing field templates: {str(e)}")
        return jsonify({"error": str(e)}), 400


@library_bp.route("/", methods=["POST"])
@swag_from({
    "tags": [
        "Library"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
def save_field_template():
    app_logger.info("Entering save_field_template")
    try:
        current_user_id = get_jwt_identity()
        current_user = get_current_user()
        data = request.get_json()

        name = data.get("name")
        description = data.get("description", "")
        category = data.get("category")
        tags = data.get("tags", [])
        template_type = data.get("template_type", "question")
        template_data = data.get("data")
        question_data_raw = data.get("question_data")
        form_id = data.get("formId")

        if not name:
            app_logger.warning("Missing name in save_field_template")
            return jsonify({"error": "Missing name"}), 400

        # If formId is provided, we are creating a template from an existing form
        if form_id:
            try:
                form = Form.objects.get(id=form_id)
                if not has_form_permission(current_user, form, "view"):
                    app_logger.warning(f"User {current_user.id} unauthorized to access form {form_id} for template creation")
                    return jsonify({"error": "Unauthorized to access form"}), 403

                # Use form data as template data
                # We want to store the version data if available, or the whole form
                template_data = form.to_mongo().to_dict()
                template_type = "form"
            except Form.DoesNotExist:
                app_logger.warning(f"Form {form_id} not found for template creation")
                return jsonify({"error": f"Form {form_id} not found"}), 404

        template = CustomFieldTemplate(
            user_id=str(current_user_id),
            name=name,
            category=category,
            template_type=template_type,
            data=(
                template_data
                if template_data
                else (question_data_raw if template_type == "question" else {})
            ),
        )

        # Add metadata-like fields if they exist in schema (they don't yet, so we use DictField data)
        if description or tags:
            if not template.data:
                template.data = {}
            template.data["description"] = description
            template.data["tags"] = tags

        # Legacy support
        if question_data_raw and template_type == "question":
            template.question_data = Question(**question_data_raw)

        template.save()
        audit_logger.info(f"Field template '{name}' (ID: {template.id}) saved by user {current_user_id}")

        # Align response with frontend FormTemplate
        return (
            jsonify(
                {
                    "id": str(template.id),
                    "name": template.name,
                    "description": description,
                    "category": template.category,
                    "form": template.data,  # Frontend expects 'form' for FormTemplate
                    "tags": tags,
                    "created_at": template.created_at.isoformat(),
                }
            ),
            201,
        )
    except Exception as e:
        error_logger.error(
            f"Error saving field template: {str(e)}\n{traceback.format_exc()}"
        )
        return jsonify({"error": str(e)}), 400


@library_bp.route("/<template_id>", methods=["GET"])
@swag_from({
    "tags": [
        "Library"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "template_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def get_field_template(template_id):
    app_logger.info(f"Entering get_field_template for ID {template_id}")
    try:
        current_user_id = get_jwt_identity()
        t = CustomFieldTemplate.objects.get(
            id=template_id, user_id=str(current_user_id)
        )

        data = (
            dict(t.data)
            if hasattr(t, "data") and t.data
            else (
                t.question_data.to_mongo().to_dict()
                if hasattr(t, "question_data") and t.question_data
                else {}
            )
        )

        description = data.get("description", "")
        tags = data.get("tags", [])

        return (
            jsonify(
                {
                    "id": str(t.id),
                    "name": t.name,
                    "description": description,
                    "category": t.category,
                    "tags": tags,
                    "template_type": getattr(t, "template_type", "question"),
                    "data": data,
                    "form": data,
                    "created_at": t.created_at.isoformat(),
                }
            ),
            200,
        )
    except Exception as e:
        error_logger.error(f"Error retrieving field template {template_id}: {e}")
        return jsonify({"error": str(e)}), 400


@library_bp.route("/<template_id>", methods=["DELETE"])
@swag_from({
    "tags": [
        "Library"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "template_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def delete_field_template(template_id):
    app_logger.info(f"Entering delete_field_template for ID {template_id}")
    try:
        current_user_id = get_jwt_identity()
        template = CustomFieldTemplate.objects.get(
            id=template_id, user_id=str(current_user_id)
        )
        template.delete()
        audit_logger.info(f"Field template {template_id} deleted by user {current_user_id}")
        return jsonify({"message": "Field template deleted"}), 200
    except Exception as e:
        error_logger.error(f"Error deleting field template {template_id}: {e}")
        return jsonify({"error": str(e)}), 400
