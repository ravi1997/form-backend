from . import form_bp
from flasgger import swag_from
from routes.v1.form import form_bp
from flask import request, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required
from mongoengine import DoesNotExist
from models import Form, FormResponse
from models.User import Role
from utils.security import require_roles
from logger.unified_logger import app_logger, error_logger, audit_logger

# -------------------- Additional Functional Routes --------------------


from utils.response_helper import success_response, error_response

@form_bp.route("/slug-available", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Check if a form slug is already taken."
        }
    }
})
@jwt_required()
def check_slug():
    """Check if a form slug is already taken."""
    slug = request.args.get("slug")
    app_logger.info(f"Checking slug availability for: {slug}")
    if not slug:
        return error_response(message="slug parameter is required", status_code=400)
    
    # Slugs are globally unique in this system, but we check within org context for clarity
    exists = Form.objects(slug=slug).first() is not None
    app_logger.info(f"Slug availability for {slug}: {not exists}")
    return success_response(data={"available": not exists})


@form_bp.route("/<form_id>/share", methods=["POST"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Admin only: Grant editor/viewer/submitter permissions for a form."
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
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def share_form(form_id):
    """Admin only: Grant editor/viewer/submitter permissions for a form."""
    app_logger.info(f"Entering share_form for form_id: {form_id}")
    data = request.get_json(silent=True) or {}
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)
        form.update(
            add_to_set__editors=data.get("editors", []),
            add_to_set__viewers=data.get("viewers", []),
            add_to_set__submitters=data.get("submitters", []),
        )
        audit_logger.info(
            f"User {get_jwt_identity()} updated permissions for form {form_id}. Editors added: {data.get('editors')}, Viewers added: {data.get('viewers')}, Submitters added: {data.get('submitters')}"
        )
        app_logger.info(f"Permissions updated for form {form_id}")
        return success_response(message="Permissions updated")
    except DoesNotExist:
        error_logger.warning(f"Form not found during share_form: {form_id}")
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Error in share_form for form {form_id}: {str(e)}")
        return error_response(message="Internal server error", status_code=500)


@form_bp.route("/<form_id>/archive", methods=["PATCH"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Admin only: Change form status to 'archived'."
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
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def archive_form(form_id):
    """Admin only: Change form status to 'archived'."""
    app_logger.info(f"Archiving form {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)
        form.update(set__status="archived")
        audit_logger.info(f"User {get_jwt_identity()} archived form {form_id}")
        return success_response(message="Form archived")
    except DoesNotExist:
        error_logger.warning(f"Form not found for archiving: {form_id}")
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Error archiving form {form_id}: {str(e)}")
        return error_response(message="Internal server error", status_code=500)


@form_bp.route("/<form_id>/restore", methods=["PATCH"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Admin only: Change form status from 'archived' back to 'draft'."
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
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def restore_form(form_id):
    """Admin only: Change form status from 'archived' back to 'draft'."""
    app_logger.info(f"Restoring form {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id, organization_id=current_user.organization_id, status="archived")
        form.update(set__status="draft")
        audit_logger.info(f"User {get_jwt_identity()} restored form {form_id}")
        return success_response(message="Form restored")
    except DoesNotExist:
        error_logger.warning(f"Archived form not found for restoration: {form_id}")
        return error_response(message="Archived form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Error restoring form {form_id}: {str(e)}")
        return error_response(message="Internal server error", status_code=500)


# -------------------- Delete All Responses --------------------
@form_bp.route("/<form_id>/responses", methods=["DELETE"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Admin only: Purge all collected responses for a specific form."
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
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def delete_all_responses(form_id):
    """Admin only: Purge all collected responses for a specific form."""
    app_logger.info(f"Purging all responses for form {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)
        deleted_count = FormResponse.objects(form=form.id).delete()
        audit_logger.info(
            f"User {get_jwt_identity()} deleted all responses for form {form_id}. Count: {deleted_count}"
        )
        return success_response(message=f"Deleted {deleted_count} responses")
    except DoesNotExist:
        error_logger.warning(
            f"Form not found during response purge for form_id: {form_id}"
        )
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Error purging responses for form {form_id}: {str(e)}")
        return error_response(message="Internal server error", status_code=500)


# -------------------- Toggle Public Access --------------------
@form_bp.route("/<form_id>/toggle-public", methods=["PATCH"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Admin only: Toggle between private and public access for a form."
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
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def toggle_form_public(form_id):
    """Admin only: Toggle between private and public access for a form."""
    app_logger.info(f"Toggling public access for form {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)
        form.is_public = not form.is_public
        form.save()
        audit_logger.info(
            f"User {get_jwt_identity()} toggled public access for form {form_id} to {form.is_public}"
        )
        return success_response(
            data={"is_public": form.is_public},
            message="Form public access toggled"
        )
    except DoesNotExist:
        error_logger.warning(
            f"Form not found during public toggle for form_id: {form_id}"
        )
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(
            f"Error toggling public access for form {form_id}: {str(e)}"
        )
        return error_response(message="Internal server error", status_code=500)


# -------------------- Count Responses for Form --------------------
@form_bp.route("/<form_id>/responses/count", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Get total submission count for a form."
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
def count_responses(form_id):
    """Get total submission count for a form."""
    app_logger.info(f"Counting responses for form {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)
        count = FormResponse.objects(form=form.id).count()
        app_logger.info(f"Response count for form {form_id}: {count}")
        return success_response(data={"form_id": form_id, "response_count": count})
    except DoesNotExist:
        error_logger.warning(
            f"Form not found during response count for form_id: {form_id}"
        )
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Error counting responses for form {form_id}: {str(e)}")
        return error_response(message="Internal server error", status_code=500)


# -------------------- Get Last Submission --------------------
@form_bp.route("/<form_id>/responses/last", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Fetch the most recent response record for a form."
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
def last_response(form_id):
    """Fetch the most recent response record for a form."""
    app_logger.info(f"Fetching last response for form {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)
        response = FormResponse.objects(form=form.id).order_by("-submitted_at").first()
        if response:
            d = response.to_mongo().to_dict()
            d["id"] = str(d.pop("_id"))
            app_logger.info(f"Last response fetched for form {form_id}")
            return success_response(data=d)
        app_logger.info(f"No responses found for form {form_id}")
        return error_response(message="No responses found", status_code=404)
    except DoesNotExist:
        error_logger.warning(
            f"Form not found during last response fetch for form_id: {form_id}"
        )
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(
            f"Error fetching last response for form {form_id}: {str(e)}"
        )
        return error_response(message="Internal server error", status_code=500)


# -------------------- Duplicate Check for Response --------------------
@form_bp.route("/<form_id>/check-duplicate", methods=["POST"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Check if the current user has already submitted this exact data."
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
def check_duplicate_submission(form_id):
    """Check if the current user has already submitted this exact data."""
    app_logger.info(f"Checking duplicate submission for form {form_id}")
    data = request.get_json(silent=True) or {}
    submitted_by = str(get_jwt_identity())
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)
        exists = FormResponse.objects(
            form=form.id, submitted_by=submitted_by, data=data.get("data")
        ).first()
        app_logger.info(
            f"Duplicate check for form {form_id} by user {submitted_by}: {exists is not None}"
        )
        return success_response(data={"duplicate": exists is not None})
    except DoesNotExist:
        error_logger.warning(
            f"Form not found during duplicate check for form_id: {form_id}"
        )
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(
            f"Error checking duplicate submission for form {form_id}: {str(e)}"
        )
        return error_response(message="Internal server error", status_code=500)
