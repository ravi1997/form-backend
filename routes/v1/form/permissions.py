from . import form_bp
from flasgger import swag_from
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import Form
from routes.v1.form.helper import get_current_user, has_form_permission
from mongoengine import DoesNotExist
from logger.unified_logger import app_logger, error_logger, audit_logger

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
    app_logger.info(f"Entering get_form_permissions for form_id: {form_id}")
    try:
        form = Form.objects.get(id=form_id)
        current_user = get_current_user()
        if not has_form_permission(current_user, form, "edit"):
            app_logger.warning(f"Unauthorized access attempt to permissions for form {form_id} by user {current_user.id}")
            return jsonify({"error": "Unauthorized"}), 403

        app_logger.info(f"Exiting get_form_permissions for form_id: {form_id}")
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
        app_logger.warning(f"Form not found: {form_id}")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(f"Error in get_form_permissions for form {form_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


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
    app_logger.info(f"Entering update_form_permissions for form_id: {form_id}")
    try:
        form = Form.objects.get(id=form_id)
        current_user = get_current_user()
        if not has_form_permission(current_user, form, "edit"):
            app_logger.warning(f"Unauthorized attempt to update permissions for form {form_id} by user {current_user.id}")
            return jsonify({"error": "Unauthorized"}), 403

        data = request.get_json()

        # We allow partial updates
        old_permissions = {
            "editors": form.editors,
            "viewers": form.viewers,
            "submitters": form.submitters
        }
        
        if "editors" in data:
            form.editors = data["editors"]
        if "viewers" in data:
            form.viewers = data["viewers"]
        if "submitters" in data:
            form.submitters = data["submitters"]

        form.save()
        
        audit_logger.info(f"User {current_user.id} updated permissions for form {form_id}", extra={
            "user_id": str(current_user.id),
            "form_id": form_id,
            "old_permissions": old_permissions,
            "new_permissions": {
                "editors": form.editors,
                "viewers": form.viewers,
                "submitters": form.submitters
            },
            "action": "update_form_permissions"
        })

        app_logger.info(f"Exiting update_form_permissions for form_id: {form_id}")
        return jsonify({"message": "Permissions updated"}), 200
    except DoesNotExist:
        app_logger.warning(f"Form not found: {form_id}")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(f"Error in update_form_permissions for form {form_id}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 400
