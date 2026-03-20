from . import form_bp
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import CustomFieldTemplate, Question, Form
from routes.v1.form.helper import get_current_user, has_form_permission
import traceback

library_bp = Blueprint("library", __name__)


@library_bp.route("/", methods=["GET"])
@jwt_required()
def list_field_templates():
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

        if "templates" in request.path:
            return jsonify({"templates": result}), 200
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.error(f"Error listing field templates: {str(e)}")
        return jsonify({"error": str(e)}), 400


@library_bp.route("/", methods=["POST"])
@jwt_required()
def save_field_template():
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
            return jsonify({"error": "Missing name"}), 400

        # If formId is provided, we are creating a template from an existing form
        if form_id:
            try:
                form = Form.objects.get(id=form_id)
                if not has_form_permission(current_user, form, "view"):
                    return jsonify({"error": "Unauthorized to access form"}), 403

                # Use form data as template data
                # We want to store the version data if available, or the whole form
                template_data = form.to_mongo().to_dict()
                template_type = "form"
            except Form.DoesNotExist:
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
        current_app.logger.error(
            f"Error saving field template: {str(e)}\n{traceback.format_exc()}"
        )
        return jsonify({"error": str(e)}), 400


@library_bp.route("/<template_id>", methods=["GET"])
@jwt_required()
def get_field_template(template_id):
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
        return jsonify({"error": str(e)}), 400


@library_bp.route("/<template_id>", methods=["DELETE"])
@jwt_required()
def delete_field_template(template_id):
    try:
        current_user_id = get_jwt_identity()
        template = CustomFieldTemplate.objects.get(
            id=template_id, user_id=str(current_user_id)
        )
        template.delete()
        return jsonify({"message": "Field template deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400
