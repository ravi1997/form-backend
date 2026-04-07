from flask import Blueprint, render_template, request, jsonify
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt_identity
from routes.v1.form.helper import apply_translations, get_current_user
from models import Form
from mongoengine import DoesNotExist
from logger.unified_logger import app_logger, error_logger

view_bp = Blueprint("view_bp", __name__)


# -------------------- index --------------------
@view_bp.route("/", methods=["GET"])
@swag_from({"tags": ["View"], "responses": {"200": {"description": "Success"}}})
def index():
    app_logger.info("View Index accessed")
    try:
        return render_template("login.html")
    except Exception as e:
        error_logger.error(f"Error rendering login template: {str(e)}")
        return "Login page not found", 404


@view_bp.route("/<form_id>", methods=["GET"])
@swag_from(
    {
        "tags": ["View"],
        "responses": {
            "200": {"description": "Success"},
            "403": {"description": "Form is private or requires authentication"},
            "404": {"description": "Form not found"},
        },
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
def view_form(form_id):
    """
    View a form. Supports both public and authenticated access.
    Public forms are accessible without authentication.
    Private forms require authentication and organization match.
    """
    app_logger.info(f"Viewing form {form_id}")
    try:
        form = Form.objects.get(id=form_id, is_deleted=False)

        # Check if form is public
        if getattr(form, "is_public", False):
            app_logger.info(f"Public form {form_id} accessed without auth")
        else:
            # Private forms require authentication and organization match
            current_user = get_current_user()
            if not current_user:
                app_logger.warning(
                    f"Unauthorized access attempt to private form {form_id}"
                )
                return jsonify(
                    {"error": "Authentication required for private forms"}
                ), 401

            # Check organization match for private forms
            if current_user.organization_id != form.organization_id:
                app_logger.warning(
                    f"Cross-tenant access attempt: User {current_user.id} (org: {current_user.organization_id}) "
                    f"attempting to access form {form_id} (org: {form.organization_id})"
                )
                return jsonify(
                    {"error": "Form is not accessible to your organization"}
                ), 403

        lang = request.args.get("lang")
        form_dict = form.to_mongo().to_dict()
        if "_id" in form_dict:
            form_dict["id"] = str(form_dict.pop("_id"))
        if lang:
            app_logger.info(
                f"Applying translations for language: {lang} on form {form_id}"
            )
            form_dict = apply_translations(form_dict, lang)
        return render_template("view.html", form=form_dict)
    except DoesNotExist:
        app_logger.warning(f"Form view failed: ID {form_id} not found")
        return "Form not found", 404
    except Exception as e:
        error_logger.error(f"Error viewing form {form_id}: {str(e)}")
        return "Internal server error", 500


@view_bp.route("/<form_id>/info", methods=["GET"])
@swag_from(
    {
        "tags": ["View"],
        "responses": {
            "200": {"description": "Success"},
            "403": {"description": "Form is private or requires authentication"},
        },
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
def get_form_info(form_id):
    """
    Get form metadata without authentication for public forms.
    Used for initial form discovery.
    """
    app_logger.info(f"Getting form info for {form_id}")
    try:
        form = Form.objects.get(id=form_id, is_deleted=False)

        # Only public forms are accessible without authentication
        if not getattr(form, "is_public", False):
            app_logger.warning(
                f"Attempt to access private form info {form_id} without auth"
            )
            return jsonify({"error": "Authentication required"}), 401

        form_info = {
            "id": str(form.id),
            "title": form.title,
            "description": form.description,
            "is_public": form.is_public,
            "status": form.status,
            "default_language": getattr(form, "default_language", "en"),
            "supported_languages": getattr(form, "supported_languages", ["en"]),
        }

        app_logger.info(f"Successfully retrieved form info for {form_id}")
        return jsonify(form_info), 200
    except DoesNotExist:
        app_logger.warning(f"Form info failed: ID {form_id} not found")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(f"Error getting form info for {form_id}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
