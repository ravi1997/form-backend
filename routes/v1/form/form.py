from . import form_bp
from flasgger import swag_from
"""
Core Form CRUD Routes
Delegates all business logic to FormService.
"""

import traceback
import re
from datetime import datetime, timezone
from flask import current_app, request, jsonify
from flask_jwt_extended import jwt_required
from mongoengine import DoesNotExist

from logger.unified_logger import app_logger, error_logger, audit_logger
from utils.response_helper import success_response, error_response
from utils.security_helpers import get_current_user, require_permission, require_org_match
from tasks.form_tasks import async_clone_form, async_publish_form
from services.form_service import FormService, FormCreateSchema, FormUpdateSchema
from routes.v1.form.helper import has_form_permission, apply_translations
from models.Form import Form

form_service = FormService()


# ───────────────────────────────────────────────────────────────────────────────
# Form CRUD
# ───────────────────────────────────────────────────────────────────────────────


@form_bp.route("/", methods=["POST"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Create a new form. Sets the current user as creator and editor."
        }
    },
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "schema": {
                "$ref": "#/definitions/FormCreateSchema"
            }
        }
    ]
})
@jwt_required()
def create_form():
    """Create a new form. Sets the current user as creator and editor."""
    app_logger.info("Entering create_form")
    data = request.get_json(silent=True) or {}
    current_user = get_current_user()
    try:
        if not current_user:
            app_logger.warning("User not found in create_form")
            return error_response(message="User not found", status_code=401)

        if not current_user.organization_id:
            app_logger.warning(f"User {current_user.id} has no organization_id; form creation requires tenant context")
            return error_response(
                message="Current user has no organization_id; form creation requires tenant context",
                status_code=400,
            )

        data.setdefault("created_by", str(current_user.id))
        data.setdefault("editors", [str(current_user.id)])
        data.setdefault("organization_id", current_user.organization_id)
        if not data.get("slug") and data.get("title"):
            slug = re.sub(r"[^a-z0-9]+", "-", data["title"].strip().lower()).strip("-")
            data["slug"] = slug or f"form-{str(current_user.id)[:8]}"
        schema = FormCreateSchema(**data)
        form = form_service.create(schema)
        audit_logger.info(f"Form created with ID {form.id} by user {current_user.id}")
        app_logger.info(f"Form created by user {current_user.id}")
        return jsonify({"message": "Form created", "form_id": str(form.id)}), 201
    except Exception as e:
        error_logger.error(f"Create form error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 400


@form_bp.route("/", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "List forms belonging to the current user's organization."
        }
    }
})
@jwt_required()
def list_forms():
    """List forms belonging to the current user's organization."""
    app_logger.info("Entering list_forms")
    current_user = get_current_user()
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 50, type=int)
    is_template = request.args.get("is_template", "false").lower() == "true"
    
    filters = {
        "organization_id": current_user.organization_id,
        "is_deleted": False
    }
    if is_template:
        filters["is_template"] = True

    result = form_service.list_paginated(
        page=page,
        page_size=page_size,
        **filters
    )
    app_logger.info(f"Listed forms for user {current_user.id} in organization {current_user.organization_id}")
    return success_response(data=result.to_dict())


@form_bp.route("/<form_id>", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Retrieve a single form, applying optional language filters."
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
@require_permission("form", "view")
def get_form(form_id):
    """Retrieve a single form, applying optional language filters."""
    app_logger.info(f"Entering get_form for ID {form_id}")
    try:
        from uuid import UUID
        current_user = get_current_user()
        
        # Ensure form_id is a UUID
        try:
            search_id = UUID(form_id) if isinstance(form_id, str) else form_id
        except ValueError:
            app_logger.warning(f"Invalid form ID format: {form_id}")
            return error_response(message="Invalid form ID format", status_code=400)

        form = Form.objects.get(id=search_id, organization_id=current_user.organization_id, is_deleted=False)

        now = datetime.now(timezone.utc)
        if (
            form.publish_at
            and now < form.publish_at.replace(tzinfo=timezone.utc)
            and not has_form_permission(current_user, form, "edit")
        ):
            app_logger.warning(f"User {current_user.id} attempted to access unpublished form {form_id}")
            return error_response(message="Form is not yet available", status_code=403)

        form_dict = form.to_mongo().to_dict()
        form_dict["id"] = str(form_dict.pop("_id"))

        lang = request.args.get("lang")
        if lang:
            app_logger.info(f"Applying translation '{lang}' for form {form_id}")
            form_dict = apply_translations(form_dict, lang)

        app_logger.info(f"Successfully retrieved form {form_id}")
        return success_response(data=form_dict)
    except DoesNotExist:
        app_logger.warning(f"Form {form_id} not found for user {current_user.id}")
        return error_response(message="Form not found", status_code=404)


@form_bp.route("/<form_id>", methods=["PUT"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Update an existing form."
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": True
        },
        {
            "name": "body",
            "in": "body",
            "schema": {
                "$ref": "#/definitions/FormUpdateSchema"
            }
        }
    ]
})
@jwt_required()
@require_permission("form", "edit")
def update_form(form_id):
    """Update an existing form."""
    app_logger.info(f"Entering update_form for ID {form_id}")
    data = request.get_json(silent=True) or {}
    current_user = get_current_user()
    try:
        from uuid import UUID
        try:
            search_id = UUID(form_id) if isinstance(form_id, str) else form_id
        except ValueError:
            app_logger.warning(f"Invalid form ID format for update: {form_id}")
            return error_response(message="Invalid form ID format", status_code=400)

        existing_form = form_service.get_by_id(str(search_id), organization_id=current_user.organization_id)
        merged_data = existing_form.model_dump()
        merged_data.update(data)
        schema = FormUpdateSchema(**merged_data)
        updated = form_service.update(str(search_id), schema, organization_id=current_user.organization_id)
        audit_logger.info(f"Form {form_id} updated by user {current_user.id}")
        return success_response(data={"form_id": str(updated.id)}, message="Form updated")
    except Exception as e:
        error_logger.error(f"Update form error for {form_id}: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>", methods=["DELETE"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Soft delete a form."
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
@require_permission("form", "delete_form")
def delete_form(form_id):
    """Soft delete a form."""
    app_logger.info(f"Entering delete_form for ID {form_id}")
    try:
        from uuid import UUID
        current_user = get_current_user()
        try:
            search_id = UUID(form_id) if isinstance(form_id, str) else form_id
        except ValueError:
            app_logger.warning(f"Invalid form ID format for deletion: {form_id}")
            return error_response(message="Invalid form ID format", status_code=400)

        form_service.delete(str(search_id), organization_id=current_user.organization_id)
        audit_logger.info(f"Form {form_id} deleted by user {current_user.id}")
        return success_response(message="Form deleted")
    except Exception as e:
         error_logger.error(f"Delete form error for {form_id}: {e}")
         return error_response(message=str(e), status_code=400)


# ───────────────────────────────────────────────────────────────────────────────
# Publish
# ───────────────────────────────────────────────────────────────────────────────


@form_bp.route("/<form_id>/publish", methods=["POST"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Publish a form asynchronously."
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
@require_permission("form", "edit")
def publish_form(form_id):
    """Publish a form asynchronously."""
    app_logger.info(f"Entering publish_form for ID {form_id}")
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    major_bump = data.get("major", False)
    minor_bump = data.get("minor", True)
    
    # Offload to Celery
    task = async_publish_form.delay(
        form_id=form_id,
        organization_id=current_user.organization_id,
        major_bump=major_bump,
        minor_bump=minor_bump
    )
    audit_logger.info(f"Form {form_id} publish initiated by user {current_user.id} (Task: {task.id})")
    
    return success_response(
        data={"task_id": task.id},
        message="Form publishing initiated in background",
        status_code=202
    )


# ───────────────────────────────────────────────────────────────────────────────
# Clone
# ───────────────────────────────────────────────────────────────────────────────


@form_bp.route("/<form_id>/clone", methods=["POST"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Clone a form asynchronously."
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
@require_permission("form", "view")
def clone_form(form_id):
    """Clone a form asynchronously."""
    app_logger.info(f"Entering clone_form for ID {form_id}")
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    new_slug = data.get("slug")
    new_title = data.get("title")
    
    # Offload to Celery
    task = async_clone_form.delay(
        form_id=form_id,
        user_id=str(current_user.id),
        organization_id=current_user.organization_id,
        new_title=new_title,
        new_slug=new_slug
    )
    audit_logger.info(f"Form {form_id} clone initiated by user {current_user.id} (Task: {task.id})")
    
    return success_response(
        data={"task_id": task.id},
        message="Form cloning initiated in background",
        status_code=202
    )


# ───────────────────────────────────────────────────────────────────────────────
# Templates
# ───────────────────────────────────────────────────────────────────────────────


@form_bp.route("/templates", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "List templates accessible to the current user."
        }
    }
})
@jwt_required()
def list_form_templates():
    """List templates accessible to the current user."""
    app_logger.info("Entering list_form_templates")
    current_user = get_current_user()
    query = {
        "is_template": True,
        "$or": [
            {"created_by": str(current_user.id)},
            {"editors": str(current_user.id)},
        ],
    }
    forms = Form.objects(__raw__=query)
    result = []
    for f in forms:
        item = f.to_mongo().to_dict()
        item["id"] = str(item.pop("_id"))
        result.append(item)
    app_logger.info(f"Listed {len(result)} templates for user {current_user.id}")
    return jsonify(result), 200


@form_bp.route("/templates/<template_id>", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Retrieve a single template."
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
def get_form_template_endpoint(template_id):
    """Retrieve a single template."""
    app_logger.info(f"Entering get_form_template_endpoint for ID {template_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=template_id, is_template=True)
        if not has_form_permission(current_user, form, "view"):
            app_logger.warning(f"User {current_user.id} unauthorized to view template {template_id}")
            return jsonify({"error": "Unauthorized"}), 403
        item = form.to_mongo().to_dict()
        item["id"] = str(item.pop("_id"))
        return jsonify(item), 200
    except DoesNotExist:
        app_logger.warning(f"Template {template_id} not found")
        return jsonify({"error": "Template not found"}), 404


# ───────────────────────────────────────────────────────────────────────────────
# Translations
# ───────────────────────────────────────────────────────────────────────────────


@form_bp.route("/<form_id>/translations", methods=["POST"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Update translation strings for a given language code."
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
def update_form_translations(form_id):
    """Update translation strings for a given language code."""
    app_logger.info(f"Entering update_form_translations for ID {form_id}")
    try:
        form = Form.objects.get(id=form_id)
        current_user = get_current_user()
        if not has_form_permission(current_user, form, "edit"):
            app_logger.warning(f"User {current_user.id} unauthorized to update translations for form {form_id}")
            return jsonify({"error": "Unauthorized"}), 403

        data = request.get_json(silent=True) or {}
        lang_code = data.get("lang_code")
        if not lang_code:
            return jsonify({"error": "lang_code is required"}), 400

        if lang_code not in (form.supported_languages or []):
            form.supported_languages = (form.supported_languages or []) + [lang_code]
        form.save()
        audit_logger.info(f"Translations for '{lang_code}' updated for form {form_id} by user {current_user.id}")
        return jsonify({"message": f"Translations for '{lang_code}' updated"}), 200
    except DoesNotExist:
        app_logger.warning(f"Form {form_id} not found for translation update")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(f"Update form translations error for {form_id}: {e}")
        return jsonify({"error": str(e)}), 400
