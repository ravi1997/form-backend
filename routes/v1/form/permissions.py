from . import form_bp
from flasgger import swag_from
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import Form
from routes.v1.form.helper import get_current_user, has_form_permission
from mongoengine import DoesNotExist

permissions_bp = Blueprint("permissions", __name__)


@permissions_bp.route("/<form_id>/permissions", methods=["GET"])
@swag_from({
    "tags": [
        "Permissions"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def get_form_permissions(form_id):
    try:
        form = Form.objects.get(id=form_id)
        current_user = get_current_user()
        if not has_form_permission(current_user, form, "edit"):
            return jsonify({"error": "Unauthorized"}), 403

        return (
            jsonify(
                {
                    "editors": form.editors,
                    "viewers": form.viewers,
                    "submitters": form.submitters,
                }
            ),
            200,
        )
    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404


@permissions_bp.route("/<form_id>/permissions", methods=["POST"])
@swag_from({
    "tags": [
        "Permissions"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def update_form_permissions(form_id):
    try:
        form = Form.objects.get(id=form_id)
        current_user = get_current_user()
        if not has_form_permission(current_user, form, "edit"):
            return jsonify({"error": "Unauthorized"}), 403

        data = request.get_json()

        # We allow partial updates
        if "editors" in data:
            form.editors = data["editors"]
        if "viewers" in data:
            form.viewers = data["viewers"]
        if "submitters" in data:
            form.submitters = data["submitters"]

        form.save()
        return jsonify({"message": "Permissions updated"}), 200
    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400
