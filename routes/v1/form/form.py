from . import form_bp
from flasgger import swag_from
"""
Core Form CRUD Routes
Delegates all business logic to FormService.
"""

import traceback
import re
from datetime import datetime, timezone
from typing import Any
from flask import current_app, request, jsonify, g
from flask_jwt_extended import jwt_required
from mongoengine import DoesNotExist

from logger.unified_logger import app_logger, error_logger, audit_logger
from utils.response_helper import success_response, error_response, BaseSerializer, FormSerializer
from utils.security_helpers import get_current_user, require_permission, require_org_match
from models import Section
from tasks.form_tasks import async_clone_form, async_publish_form
from services.form_service import (
    FormService,
    FormCreateSchema,
    FormUpdateSchema,
    ProjectService,
)
from routes.v1.form.helper import has_form_permission, apply_translations
from models.Form import Form, Project, FormVersion, Version
from services.access_control_service import AccessControlService

form_service = FormService()
project_service = ProjectService()


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
    """Create a new form inside the current project context."""
    app_logger.info("Entering create_form")
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    try:
        project_id = getattr(g, "project_id", None)
        if not project_id:
            return error_response(message="Project context missing from route", status_code=400)
        if not current_user:
            app_logger.warning("User not found in create_form")
            return error_response(message="User not found", status_code=401)
        if not current_user.organization_id:
            app_logger.warning(f"User {current_user.id} has no organization_id; form creation requires tenant context")
            return error_response(
                message="Current user has no organization_id; form creation requires tenant context",
                status_code=400,
            )

        project = Project.objects.get(
            id=project_id,
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        if not AccessControlService.check_project_permission(current_user, project, "edit"):
            audit_logger.info(
                f"AUDIT: Unauthorized form creation attempt in project {project_id} by user {current_user.id}"
            )
            return error_response(
                message="Unauthorized to manage this project",
                status_code=403,
            )

        data["project"] = project_id
        data.setdefault("created_by", str(current_user.id))
        data.setdefault("editors", [str(current_user.id)])
        data.setdefault("organization_id", current_user.organization_id)
        if not data.get("slug") and data.get("title"):
            slug = re.sub(r"[^a-z0-9]+", "-", data["title"].strip().lower()).strip("-")
            data["slug"] = slug or f"form-{str(current_user.id)[:8]}"

        form = project_service.create_form_in_project(
            project_id, data, current_user.organization_id, current_user
        )
        if data.get("sections") or data.get("versions"):
            form = form_service.sync_form_canvas(
                str(form.id),
                current_user.organization_id,
                data,
            )
        audit_logger.info(
            f"AUDIT: Form {form.id} created in project {project_id} by user {current_user.id}"
        )
        return success_response(
            data={"form_id": str(form.id)},
            message="Form created",
            status_code=201,
        )
    except DoesNotExist:
        return error_response(message="Project not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Create form error: {e}\n{traceback.format_exc()}")
        return error_response(message=str(e), status_code=400)



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
    """List forms belonging to the current project."""
    app_logger.info("Entering list_forms")
    current_user = get_current_user()
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 50, type=int)
    is_template = request.args.get("is_template", "false").lower() == "true"
    project_id = getattr(g, "project_id", None)
    
    filters = {
        "organization_id": current_user.organization_id,
        "is_deleted": False
    }
    if project_id:
        filters["project"] = project_id
    if is_template:
        filters["is_template"] = True

    result = form_service.list_paginated(
        page=page,
        page_size=page_size,
        **filters
    )
    
    # Sanitize output
    data = result.to_dict()
    data["items"] = [FormSerializer.serialize(i) for i in data.get("items", [])]
    
    app_logger.info(f"Listed forms for user {current_user.id} in organization {current_user.organization_id}")
    return success_response(data=data)


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
        
        lang = request.args.get("lang")
        if lang:
            app_logger.info(f"Applying translation '{lang}' for form {form_id}")
            form_dict = apply_translations(form_dict, lang)

        # Ensure nested section trees are available to the frontend builder
        # through the active version snapshot, not just as flat section refs.
        try:
            latest_version = form.versions.order_by("-created_at").first()
            if latest_version:
                resolved_snapshot = (
                    latest_version.resolved_snapshot
                    if hasattr(latest_version, "resolved_snapshot")
                    else {}
                ) or {}
                if resolved_snapshot.get("sections"):
                    versions = form_dict.get("versions") or []
                    if versions:
                        versions[-1]["sections"] = resolved_snapshot["sections"]
                        form_dict["versions"] = versions
                    else:
                        form_dict["versions"] = [
                            {
                                "version": getattr(
                                    latest_version.version,
                                    "version_string",
                                    "1.0.0",
                                ),
                                "sections": resolved_snapshot["sections"],
                                "created_at": getattr(
                                    latest_version, "created_at", None
                                ),
                            }
                        ]
        except Exception:
            app_logger.warning(
                f"Unable to inject resolved nested sections for form {form_id}",
                exc_info=True,
            )

        # Sanitize after translation
        sanitized_form = FormSerializer.serialize(form_dict)

        app_logger.info(f"Successfully retrieved form {form_id}")
        return success_response(data=sanitized_form)
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
        canvas_keys = (
            "sections",
            "versions",
            "active_version",
            "workflows",
            "metadata",
            "access_policy",
            "accessPolicy",
            "style",
            "ui_type",
            "description",
            "help_text",
        )
        has_canvas_payload = any(key in data for key in canvas_keys)
        if has_canvas_payload:
            updated = form_service.sync_form_canvas(
                str(search_id),
                current_user.organization_id,
                merged_data,
            )
        else:
            updated = form_service.update(
                str(search_id), schema, organization_id=current_user.organization_id
            )
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
    return success_response(data=result)


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
        form = Form.objects.get(id=template_id, organization_id=current_user.organization_id, is_template=True)
        if not has_form_permission(current_user, form, "view"):
            app_logger.warning(f"User {current_user.id} unauthorized to view template {template_id}")
            return error_response(message="Unauthorized", status_code=403)
        item = form.to_mongo().to_dict()
        item["id"] = str(item.pop("_id"))
        return success_response(data=item)
    except DoesNotExist:
        app_logger.warning(f"Template {template_id} not found")
        return error_response(message="Template not found", status_code=404)


from services.section_service import SectionService
section_service = SectionService()

@form_bp.route("/import", methods=["POST"])
@swag_from({
    "tags": ["Form"],
    "responses": {"201": {"description": "Form imported successfully"}}
})
@jwt_required()
def import_form():
    """Import a full form structure from JSON."""
    app_logger.info("Entering import_form")
    current_user = get_current_user()
    data = request.get_json()
    
    try:
        # Basic validation of import payload
        title = data.get("title")
        slug = data.get("slug")
        if not title or not slug:
            return error_response(message="Title and slug are required for import", status_code=400)
            
        # Create form doc
        form = Form(
            title=title,
            slug=slug,
            description=data.get("description"),
            help_text=data.get("help_text"),
            ui_type=data.get("ui_type", data.get("uiType", "flex")),
            organization_id=current_user.organization_id,
            created_by=str(current_user.id),
            status="draft",
            supported_languages=data.get("supported_languages", ["en"]),
            default_language=data.get("default_language", "en"),
            style=data.get("style", {}),
            translations=data.get("translations", {})
        )
        
        # Import sections recursively if provided
        sections_data = data.get("sections", [])
        new_sections = []
        
        def import_sections(secs):
            imported = []
            for s_data in secs:
                normalized = section_service.normalize_section_tree(s_data)
                s = Section(
                    title=normalized.get("title"),
                    description=normalized.get("description"),
                    help_text=normalized.get("help_text"),
                    order=normalized.get("order", 0),
                    layout=normalized.get("layout", "standard"),
                    grid_columns=normalized.get("grid_columns", 2),
                    is_hidden=normalized.get("is_hidden", False),
                    is_repeatable=normalized.get("is_repeatable", False),
                    repeat_min=normalized.get("repeat_min"),
                    repeat_max=normalized.get("repeat_max"),
                    conditional_logic=normalized.get("conditional_logic", {}),
                    style=normalized.get("style", {}),
                    logic=normalized.get("logic", {}),
                    ui=normalized.get("ui", {}),
                    questions=normalized.get("questions", []),
                    response_templates=normalized.get("response_templates", []),
                    tags=normalized.get("tags", []),
                    meta_data=normalized.get("meta_data", {}),
                    organization_id=current_user.organization_id
                )
                if normalized.get("sections"):
                    s.sections = import_sections(normalized["sections"])
                s.save()
                imported.append(s)
            return imported

        if sections_data:
            form.sections = import_sections(sections_data)
            
        form.save()
        audit_logger.info(f"Form {form.id} imported by user {current_user.id}")
        return success_response(data=FormSerializer.serialize(form.to_mongo().to_dict()), status_code=201)
        
    except Exception as e:
        error_logger.error(f"Import form error: {e}")
        return error_response(message=str(e), status_code=400)

# ───────────────────────────────────────────────────────────────────────────────
# Sections CRUD
# ───────────────────────────────────────────────────────────────────────────────

@form_bp.route("/<form_id>/sections", methods=["POST"])
@swag_from({
    "tags": ["Section"],
    "parameters": [{"name": "form_id", "in": "path", "type": "string", "required": True}],
    "responses": {"201": {"description": "Section created"}}
})
@jwt_required()
def create_form_section(form_id):
    """Add a new section to a form."""
    current_user = get_current_user()
    data: Any = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return error_response(message="Request body must be a JSON object", status_code=400)
    try:
        parent_section_id_raw = data.get("parent_section_id")
        parent_section_id = (
            str(parent_section_id_raw) if parent_section_id_raw is not None else None
        )
        section = section_service.create_section(
            form_id,
            data,
            current_user.organization_id,
            parent_section_id=parent_section_id,
        )
        from models.Form import FormVersion, Version

        form_version = (
            FormVersion.objects(form=form_id, status="draft")
            .order_by("-created_at")
            .first()
        )
        version_string = None
        if form_version and form_version.version:
            version_doc = Version.objects(
                id=getattr(form_version.version, "id", form_version.version)
            ).first()
            if version_doc:
                version_string = version_doc.version_string
        section_payload = (
            section.to_dict() if hasattr(section, "to_dict") else section.to_mongo().to_dict()
        )
        return success_response(
            data={
                "section": BaseSerializer.clean_dict(section_payload, preserve_fields=("meta_data",)),
                "version": version_string,
                "form_version_id": str(form_version.id) if form_version else None,
            },
            status_code=201,
        )
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@form_bp.route("/forms/<form_id>/sections", methods=["POST"])
@jwt_required()
def create_project_form_section(project_id, form_id):
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    try:
        form = Form.objects.get(
            id=form_id,
            project=project_id,
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        parent_section_id = data.get("parent_section_id")
        section = section_service.create_section(
            str(form.id),
            data,
            current_user.organization_id,
            parent_section_id=parent_section_id,
        )
        return success_response(data={"section": BaseSerializer.clean_dict(section.to_dict(), preserve_fields=("meta_data",))}, status_code=201)
    except Exception as e:
        return error_response(message=str(e), status_code=400)

@form_bp.route("/<form_id>/sections", methods=["GET"])
@jwt_required()
def list_form_sections(form_id):
    """List all sections for a form."""
    current_user = get_current_user()
    try:
        form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)
        serialized_sections = []
        for section_ref in form.sections or []:
            section_doc = None

            # Already dereferenced MongoEngine document.
            if hasattr(section_ref, "to_mongo"):
                section_doc = section_ref
            # bson.dbref.DBRef or similar reference object.
            elif hasattr(section_ref, "id"):
                section_doc = Section.objects(
                    id=section_ref.id,
                    organization_id=current_user.organization_id,
                    is_deleted=False,
                ).first()
            # Raw UUID/string fallback.
            else:
                section_doc = Section.objects(
                    id=section_ref,
                    organization_id=current_user.organization_id,
                    is_deleted=False,
                ).first()

            if section_doc:
                serialized_sections.append(
                    BaseSerializer.clean_dict(
                        section_doc.to_dict()
                        if hasattr(section_doc, "to_dict")
                        else section_doc.to_mongo().to_dict(),
                        preserve_fields=("meta_data",)
                    )
                )

        return success_response(data=serialized_sections)
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/sections/<section_id>", methods=["PUT"])
@jwt_required()
def update_form_section(form_id, section_id):
    """Update a specific section."""
    current_user = get_current_user()
    data = request.get_json()
    try:
        # Verify form exists and belongs to org
        Form.objects.get(id=form_id, organization_id=current_user.organization_id)
        normalized_data = section_service.normalize_section_tree(data)
        section = section_service.update(
            section_id,
            normalized_data,
            organization_id=current_user.organization_id,
        )
        if hasattr(section, "to_dict"):
            payload = BaseSerializer.clean_dict(section.to_dict(), preserve_fields=("meta_data",))
        elif hasattr(section, "to_mongo"):
            payload = BaseSerializer.clean_dict(section.to_mongo().to_dict(), preserve_fields=("meta_data",))
        elif hasattr(section, "model_dump"):
            payload = BaseSerializer.clean_dict(section.model_dump(), preserve_fields=("meta_data",))
        else:
            payload = BaseSerializer.clean_dict(section, preserve_fields=("meta_data",))
        return success_response(data=payload)
    except Exception as e:
        app_logger.error(f"Error updating section: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)

@form_bp.route("/<form_id>/sections/<section_id>", methods=["DELETE"])
@jwt_required()
def delete_form_section(form_id, section_id):
    """Remove a section from a form."""
    current_user = get_current_user()
    try:
        section_service.delete_section(form_id, section_id, current_user.organization_id)
        return success_response(message="Section deleted")
    except Exception as e:
        return error_response(message=str(e), status_code=400)

@form_bp.route("/<form_id>/sections/reorder", methods=["PUT"])
@jwt_required()
def reorder_form_sections(form_id):
    """Update section order."""
    current_user = get_current_user()
    data = request.get_json() # Expects { "section_ids": ["id1", "id2", ...] }
    try:
        section_service.update_section_order(form_id, data.get("section_ids", []), current_user.organization_id)
        return success_response(message="Sections reordered")
    except Exception as e:
        return error_response(message=str(e), status_code=400)

# ───────────────────────────────────────────────────────────────────────────────
# Versions
# ───────────────────────────────────────────────────────────────────────────────

def _serialize_form_version(form_version):
    version_doc = getattr(form_version, "version", None)
    try:
        snapshot = form_version.resolved_snapshot or {}
    except Exception:
        snapshot = {}

    return BaseSerializer.clean_dict(
        {
            "id": str(form_version.id),
            "form_id": str(getattr(form_version.form, "id", form_version.form)),
            "version": getattr(version_doc, "version_string", None),
            "major": getattr(version_doc, "major", None),
            "minor": getattr(version_doc, "minor", None),
            "patch": getattr(version_doc, "patch", None),
            "status": form_version.status,
            "created_at": getattr(form_version, "created_at", None),
            "sections": snapshot.get("sections", []),
            "translations": getattr(form_version, "translations", {}) or {},
        },
        preserve_fields=("meta_data",)
    )


@form_bp.route("/<form_id>/versions", methods=["GET"])
@jwt_required()
def list_project_form_versions(project_id, form_id):
    current_user = get_current_user()
    try:
        form = Form.objects.get(
            id=form_id,
            project=project_id,
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        versions = [
            _serialize_form_version(item)
            for item in FormVersion.objects(form=form.id).order_by("-created_at")
        ]
        audit_logger.info(
            f"AUDIT: Form versions listed for form {form_id} by user {current_user.id}"
        )
        return success_response(data=versions)
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/versions/<version>", methods=["GET"])
@jwt_required()
def get_project_form_version(project_id, form_id, version):
    current_user = get_current_user()
    try:
        form = Form.objects.get(
            id=form_id,
            project=project_id,
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        version_doc = Version.objects(form=form.id).order_by("-major", "-minor", "-patch").first()
        if not version_doc:
            return error_response(message="Version not found", status_code=404)
        if version and version != getattr(version_doc, "version_string", None):
            matching = Version.objects(
                form=form.id,
                major=int(version.split(".")[0]),
                minor=int(version.split(".")[1]),
                patch=int(version.split(".")[2]),
            ).first()
            if matching:
                version_doc = matching
        form_version = FormVersion.objects(form=form.id, version=version_doc).first()
        if not form_version:
            return error_response(message="Version snapshot not found", status_code=404)
        audit_logger.info(
            f"AUDIT: Form version {version} viewed for form {form_id} by user {current_user.id}"
        )
        return success_response(data=_serialize_form_version(form_version))
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/versions", methods=["POST"])
@jwt_required()
def create_project_form_version(project_id, form_id):
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    try:
        form = Form.objects.get(
            id=form_id,
            project=project_id,
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        if data.get("sections") or data.get("versions"):
            form_service.sync_form_canvas(str(form.id), current_user.organization_id, data)
        form_version = form_service.sync_draft_version(str(form.id), current_user.organization_id)
        audit_logger.info(
            f"AUDIT: Form version created for form {form_id} by user {current_user.id}"
        )
        return success_response(data=_serialize_form_version(form_version), status_code=201)
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/versions/<version>", methods=["PUT"])
@jwt_required()
def update_project_form_version(project_id, form_id, version):
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    try:
        form = Form.objects.get(
            id=form_id,
            project=project_id,
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        if data.get("sections") or data.get("versions"):
            form_service.sync_form_canvas(str(form.id), current_user.organization_id, data)
        form_version = form_service.sync_draft_version(str(form.id), current_user.organization_id)
        audit_logger.info(
            f"AUDIT: Form version {version} updated for form {form_id} by user {current_user.id}"
        )
        return success_response(data=_serialize_form_version(form_version))
    except Exception as e:
        return error_response(message=str(e), status_code=400)

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
        current_user = get_current_user()
        # Strictly enforce organization_id in lookup
        form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)
        
        if not has_form_permission(current_user, form, "edit"):
            app_logger.warning(f"User {current_user.id} unauthorized to update translations for form {form_id}")
            return error_response(message="Unauthorized", status_code=403)

        data = request.get_json(silent=True) or {}
        lang_code = data.get("lang_code")
        translations = data.get("translations") # Expecting { questions: {}, sections: {}, title: "", description: "" }
        
        if not lang_code:
            return error_response(message="lang_code is required", status_code=400)

        if lang_code not in (form.supported_languages or []):
            form.supported_languages = (form.supported_languages or []) + [lang_code]
        
        if translations:
            # Add to translations dict without wiping others
            if not form.translations:
                form.translations = {}
            form.translations[lang_code] = translations
            
        form.save()
        audit_logger.info(f"Translations for '{lang_code}' updated for form {form_id} by user {current_user.id}")
        return success_response(message=f"Translations for '{lang_code}' updated")
    except DoesNotExist:
        app_logger.warning(f"Form {form_id} not found for translation update")
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Update form translations error for {form_id}: {e}")
        return error_response(message=str(e), status_code=400)
