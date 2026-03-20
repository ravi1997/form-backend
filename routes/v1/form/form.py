from . import form_bp
from flasgger import swag_from
"""
Core Form CRUD Routes
Delegates all business logic to FormService.
"""

import traceback
from flask import current_app, request, jsonify
from flask_jwt_extended import jwt_required
from mongoengine import DoesNotExist

from utils.response_helper import success_response, error_response
from utils.security_helpers import get_current_user, require_permission, require_org_match
from tasks.form_tasks import async_clone_form, async_publish_form
from services.form_service import FormService

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
    data = request.get_json(silent=True) or {}
    current_user = get_current_user()
    try:
        data.setdefault("created_by", str(current_user.id))
        data.setdefault("editors", [str(current_user.id)])
        schema = FormCreateSchema(**data)
        form = form_service.create(schema)
        current_app.logger.info(f"Form created by user {current_user.id}")
        return jsonify({"message": "Form created", "form_id": str(form.id)}), 201
    except Exception as e:
        current_app.logger.error(f"Create form error: {e}\n{traceback.format_exc()}")
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
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id, organization_id=current_user.organization_id, is_deleted=False)

        now = datetime.now(timezone.utc)
        if (
            form.publish_at
            and now < form.publish_at.replace(tzinfo=timezone.utc)
            and not has_form_permission(current_user, form, "edit")
        ):
            return error_response(message="Form is not yet available", status_code=403)

        form_dict = form.to_mongo().to_dict()
        form_dict["id"] = str(form_dict.pop("_id"))

        lang = request.args.get("lang")
        if lang:
            form_dict = apply_translations(form_dict, lang)

        return success_response(data=form_dict)
    except DoesNotExist:
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
    data = request.get_json(silent=True) or {}
    current_user = get_current_user()
    try:
        schema = FormUpdateSchema(**data)
        updated = form_service.update(form_id, schema, organization_id=current_user.organization_id)
        return success_response(data={"form_id": str(updated.id)}, message="Form updated")
    except Exception as e:
        current_app.logger.error(f"Update form error for {form_id}: {e}", exc_info=True)
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
    try:
        current_user = get_current_user()
        form_service.delete(form_id, organization_id=current_user.organization_id)
        return success_response(message="Form deleted")
    except Exception as e:
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
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=template_id, is_template=True)
        if not has_form_permission(current_user, form, "view"):
            return jsonify({"error": "Unauthorized"}), 403
        item = form.to_mongo().to_dict()
        item["id"] = str(item.pop("_id"))
        return jsonify(item), 200
    except DoesNotExist:
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
    try:
        form = Form.objects.get(id=form_id)
        current_user = get_current_user()
        if not has_form_permission(current_user, form, "edit"):
            return jsonify({"error": "Unauthorized"}), 403

        data = request.get_json(silent=True) or {}
        lang_code = data.get("lang_code")
        if not lang_code:
            return jsonify({"error": "lang_code is required"}), 400

        if lang_code not in (form.supported_languages or []):
            form.supported_languages = (form.supported_languages or []) + [lang_code]
        form.save()
        return jsonify({"message": f"Translations for '{lang_code}' updated"}), 200
    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400
