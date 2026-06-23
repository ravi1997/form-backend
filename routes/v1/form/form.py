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
from utils.response_helper import (
    success_response,
    error_response,
    BaseSerializer,
    FormSerializer,
)
from utils.security_helpers import (
    get_current_user,
    require_permission,
    require_org_match,
)
from utils.idempotency import require_idempotency
from models import Section
from tasks.form_tasks import async_clone_form, async_publish_form
from services.form_service import (
    AdvancedSettingsSchema,
    FormService,
    FormCreateSchema,
    FormUpdateSchema,
    ProjectService,
)
from routes.v1.form.helper import (
    has_form_permission,
    apply_translations,
    resolve_translation_language,
)
from models.system import AuditLog
from models.form import Form, Project, FormVersion, Version
from models.base import (
    ACCESS_LEVEL_CHOICES,
    COMPARISON_TYPE_CHOICES,
    CONDITION_OPERATOR_CHOICES,
    CONDITION_SOURCE_TYPE_CHOICES,
    FIELD_API_CALL_CHOICES,
    FIELD_TYPE_CHOICES,
    LOGICAL_OPERATOR_CHOICES,
    PERMISSION_CHOICES,
    ROLE_CHOICES,
    TRIGGER_ACTION_CHOICES,
    TRIGGER_EVENT_CHOICES,
    UI_TYPE_CHOICES,
)
from services.access_control_service import AccessControlService
from engines.form_engine import FormEngine

form_service = FormService()
project_service = ProjectService()
form_engine = FormEngine()


# ───────────────────────────────────────────────────────────────────────────────
# Form CRUD
# ───────────────────────────────────────────────────────────────────────────────


@form_bp.route("/", methods=["POST"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {
            "200": {
                "description": "Create a new form. Sets the current user as creator and editor."
            }
        },
        "parameters": [
            {
                "name": "body",
                "in": "body",
                "schema": {"$ref": "#/definitions/FormCreateSchema"},
            }
        ],
    }
)
@jwt_required()
def create_form():
    """Create a new form inside the current project context."""
    app_logger.info("Entering create_form")
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    try:
        project_id = getattr(g, "project_id", None)
        if not project_id:
            return error_response(
                message="Project context missing from route", status_code=400
            )
        if not current_user:
            app_logger.warning("User not found in create_form")
            return error_response(message="User not found", status_code=401)
        if not current_user.organization_id:
            app_logger.warning(
                f"User {current_user.id} has no organization_id; form creation requires tenant context"
            )
            return error_response(
                message="Current user has no organization_id; form creation requires tenant context",
                status_code=400,
            )

        project = Project.objects.get(
            id=project_id,
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        if not AccessControlService.check_project_permission(
            current_user, project, "edit"
        ):
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
@swag_from(
    {
        "tags": ["Form"],
        "responses": {
            "200": {
                "description": "List forms belonging to the current user's organization."
            }
        },
    }
)
@jwt_required()
def list_forms():
    """List forms belonging to the current project."""
    app_logger.info("Entering list_forms")
    current_user = get_current_user()
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 50, type=int)
    is_template = request.args.get("is_template", "false").lower() == "true"
    project_id = getattr(g, "project_id", None)

    filters = {"organization_id": current_user.organization_id, "is_deleted": False}
    if project_id:
        filters["project"] = project_id
    if is_template:
        filters["is_template"] = True

    result = form_service.list_paginated(page=page, page_size=page_size, **filters)

    # Sanitize output
    data = result.to_dict()
    data["items"] = [FormSerializer.serialize(i) for i in data.get("items", [])]

    app_logger.info(
        f"Listed forms for user {current_user.id} in organization {current_user.organization_id}"
    )
    return success_response(data=data)


@form_bp.route("/<form_id>", methods=["GET"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {
            "200": {
                "description": "Retrieve a single form, applying optional language filters."
            }
        },
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
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

        form = Form.objects.get(
            id=search_id, organization_id=current_user.organization_id, is_deleted=False
        )

        now = datetime.now(timezone.utc)
        if (
            form.publish_at
            and now < form.publish_at.replace(tzinfo=timezone.utc)
            and not has_form_permission(current_user, form, "edit")
        ):
            app_logger.warning(
                f"User {current_user.id} attempted to access unpublished form {form_id}"
            )
            return error_response(message="Form is not yet available", status_code=403)

        form_dict = form.to_mongo().to_dict()

        requested_lang = request.args.get("lang")
        if requested_lang:
            app_logger.info(
                f"Applying translation '{requested_lang}' for form {form_id}"
            )
            advanced_settings = form_dict.get("advanced_settings") or {}
            resolved_lang = resolve_translation_language(
                form_dict.get("translations") or {},
                requested_lang=requested_lang,
                fallback_lang=advanced_settings.get("fallback_language")
                or advanced_settings.get("locale_default")
                or form_dict.get("default_language"),
                default_lang=advanced_settings.get("locale_default")
                or form_dict.get("default_language"),
            )
            if resolved_lang:
                form_dict = apply_translations(form_dict, resolved_lang)

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
                versions = form_dict.get("versions") or []
                resolved_submission_settings = resolved_snapshot.get(
                    "submission_settings"
                )
                resolved_quick_responses = resolved_snapshot.get("quick_responses")
                resolved_data_export_settings = resolved_snapshot.get(
                    "data_export_settings"
                )
                resolved_advanced_settings = resolved_snapshot.get("advanced_settings")
                if versions:
                    if resolved_snapshot.get("sections"):
                        versions[-1]["sections"] = resolved_snapshot["sections"]
                    if resolved_submission_settings is not None:
                        versions[-1]["submission_settings"] = (
                            resolved_submission_settings
                        )
                    if resolved_quick_responses is not None:
                        versions[-1]["quick_responses"] = resolved_quick_responses
                    if resolved_data_export_settings is not None:
                        versions[-1]["data_export_settings"] = (
                            resolved_data_export_settings
                        )
                    if resolved_advanced_settings is not None:
                        versions[-1]["advanced_settings"] = resolved_advanced_settings
                    form_dict["versions"] = versions
                elif resolved_snapshot.get("sections") or (
                    resolved_submission_settings is not None
                    or resolved_quick_responses is not None
                    or resolved_data_export_settings is not None
                    or resolved_advanced_settings is not None
                ):
                    form_dict["versions"] = [
                        {
                            "version": getattr(
                                latest_version.version,
                                "version_string",
                                "1.0.0",
                            ),
                            "sections": resolved_snapshot.get("sections", []),
                            "submission_settings": (
                                resolved_submission_settings or {}
                            ),
                            "quick_responses": (resolved_quick_responses or []),
                            "data_export_settings": (
                                resolved_data_export_settings or {}
                            ),
                            "advanced_settings": (
                                resolved_advanced_settings or {}
                            ),
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
@swag_from(
    {
        "tags": ["Form"],
        "responses": {"200": {"description": "Update an existing form."}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True},
            {
                "name": "body",
                "in": "body",
                "schema": {"$ref": "#/definitions/FormUpdateSchema"},
            },
        ],
    }
)
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

        existing_form = form_service.get_by_id(
            str(search_id), organization_id=current_user.organization_id
        )
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
            "submission_settings",
            "submissionSettings",
            "quick_responses",
            "quickResponses",
            "data_export_settings",
            "dataExportSettings",
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
        return success_response(
            data={"form_id": str(updated.id)}, message="Form updated"
        )
    except Exception as e:
        error_logger.error(f"Update form error for {form_id}: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>", methods=["DELETE"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {"200": {"description": "Soft delete a form."}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
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

        form_service.delete(
            str(search_id), organization_id=current_user.organization_id
        )
        audit_logger.info(f"Form {form_id} deleted by user {current_user.id}")
        return success_response(message="Form deleted")
    except Exception as e:
        error_logger.error(f"Delete form error for {form_id}: {e}")
        return error_response(message=str(e), status_code=400)


# ───────────────────────────────────────────────────────────────────────────────
# Publish
# ───────────────────────────────────────────────────────────────────────────────


@form_bp.route("/<form_id>/publish", methods=["POST"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {"200": {"description": "Publish a form asynchronously."}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
@require_permission("form", "edit")
@require_idempotency()
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
        minor_bump=minor_bump,
    )
    audit_logger.info(
        f"Form {form_id} publish initiated by user {current_user.id} (Task: {task.id})"
    )

    return success_response(
        data={"task_id": task.id},
        message="Form publishing initiated in background",
        status_code=202,
    )


# ───────────────────────────────────────────────────────────────────────────────
# Clone
# ───────────────────────────────────────────────────────────────────────────────


@form_bp.route("/<form_id>/clone", methods=["POST"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {"200": {"description": "Clone a form asynchronously."}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
@require_permission("form", "view")
@require_idempotency()
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
        new_slug=new_slug,
    )
    audit_logger.info(
        f"Form {form_id} clone initiated by user {current_user.id} (Task: {task.id})"
    )

    return success_response(
        data={"task_id": task.id},
        message="Form cloning initiated in background",
        status_code=202,
    )


from services.section_service import SectionService

section_service = SectionService()


@form_bp.route("/import", methods=["POST"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {"201": {"description": "Form imported successfully"}},
    }
)
@jwt_required()
def import_form():
    """Import a full form structure from JSON."""
    app_logger.info("Entering import_form")
    current_user = get_current_user()
    data = request.get_json() or {}

    try:
        advanced_payload = data.get("advanced_settings", data.get("advancedSettings"))
        if isinstance(advanced_payload, dict):
            normalized_advanced = AdvancedSettingsSchema.model_validate(
                advanced_payload
            ).model_dump(exclude_unset=True, exclude_none=True)
            data["advanced_settings"] = normalized_advanced
            data["advancedSettings"] = normalized_advanced
            if normalized_advanced.get("slug"):
                data["slug"] = normalized_advanced.get("slug")
            if normalized_advanced.get("locale_default"):
                data["default_language"] = normalized_advanced.get("locale_default")

        # Basic validation of import payload
        title = data.get("title")
        slug = data.get("slug")
        if not title or not slug:
            return error_response(
                message="Title and slug are required for import", status_code=400
            )

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
            translations=data.get("translations", {}),
            advanced_settings=data.get("advanced_settings", {}),
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
                    organization_id=current_user.organization_id,
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
        return success_response(
            data=FormSerializer.serialize(form.to_mongo().to_dict()), status_code=201
        )

    except Exception as e:
        error_logger.error(f"Import form error: {e}")
        return error_response(message=str(e), status_code=400)


# ───────────────────────────────────────────────────────────────────────────────
# Sections CRUD
# ───────────────────────────────────────────────────────────────────────────────


@form_bp.route("/<form_id>/sections", methods=["POST"])
@swag_from(
    {
        "tags": ["Section"],
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
        "responses": {"201": {"description": "Section created"}},
    }
)
@jwt_required()
def create_form_section(form_id):
    """Add a new section to a form."""
    current_user = get_current_user()
    data: Any = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return error_response(
            message="Request body must be a JSON object", status_code=400
        )
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
        from models.form import FormVersion, Version

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
            section.to_dict()
            if hasattr(section, "to_dict")
            else section.to_mongo().to_dict()
        )
        return success_response(
            data={
                "section": BaseSerializer.clean_dict(
                    section_payload, preserve_fields=("meta_data",)
                ),
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
        return success_response(
            data={
                "section": BaseSerializer.clean_dict(
                    section.to_dict(), preserve_fields=("meta_data",)
                )
            },
            status_code=201,
        )
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/sections", methods=["GET"])
@jwt_required()
def list_form_sections(form_id):
    """List all sections for a form."""
    current_user = get_current_user()
    try:
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id
        )
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
                        (
                            section_doc.to_dict()
                            if hasattr(section_doc, "to_dict")
                            else section_doc.to_mongo().to_dict()
                        ),
                        preserve_fields=("meta_data",),
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
            payload = BaseSerializer.clean_dict(
                section.to_dict(), preserve_fields=("meta_data",)
            )
        elif hasattr(section, "to_mongo"):
            payload = BaseSerializer.clean_dict(
                section.to_mongo().to_dict(), preserve_fields=("meta_data",)
            )
        elif hasattr(section, "model_dump"):
            payload = BaseSerializer.clean_dict(
                section.model_dump(), preserve_fields=("meta_data",)
            )
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
        section_service.delete_section(
            form_id, section_id, current_user.organization_id
        )
        return success_response(message="Section deleted")
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/sections/reorder", methods=["PUT"])
@jwt_required()
def reorder_form_sections(form_id):
    """Update section order."""
    current_user = get_current_user()
    data = request.get_json()  # Expects { "section_ids": ["id1", "id2", ...] }
    try:
        section_service.update_section_order(
            form_id, data.get("section_ids", []), current_user.organization_id
        )
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
    try:
        form_ref = form_version.to_mongo().get("form")
    except Exception:
        form_ref = getattr(form_version, "form", None)

    return BaseSerializer.clean_dict(
        {
            "id": str(form_version.id),
            "form_id": str(getattr(form_ref, "id", form_ref)),
            "version": getattr(version_doc, "version_string", None),
            "major": getattr(version_doc, "major", None),
            "minor": getattr(version_doc, "minor", None),
            "patch": getattr(version_doc, "patch", None),
            "status": form_version.status,
            "created_at": getattr(form_version, "created_at", None),
            "sections": snapshot.get("sections", []),
            "translations": getattr(form_version, "translations", {}) or {},
            "submission_settings": snapshot.get(
                "submission_settings",
                getattr(form_version, "submission_settings", {}) or {},
            ),
            "quick_responses": snapshot.get(
                "quick_responses",
                [
                    item.to_mongo().to_dict()
                    if hasattr(item, "to_mongo")
                    else item
                    for item in (getattr(form_version, "quick_responses", []) or [])
                ],
            ),
            "data_export_settings": snapshot.get(
                "data_export_settings",
                getattr(form_version, "data_export_settings", {}) or {},
            ),
            "advanced_settings": snapshot.get(
                "advanced_settings",
                getattr(form_version, "advanced_settings", {}) or {},
            ),
        },
        preserve_fields=("meta_data",),
    )


def _find_form_version(form, version):
    try:
        form_version = FormVersion.objects(form=form.id, id=version).first()
    except Exception:
        form_version = None
    if form_version:
        return form_version

    version_doc = None
    parts = str(version).split(".")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        version_doc = Version.objects(
            form=form.id,
            major=int(parts[0]),
            minor=int(parts[1]),
            patch=int(parts[2]),
        ).first()
    if not version_doc:
        try:
            version_doc = Version.objects(form=form.id, id=version).first()
        except Exception:
            version_doc = None
    if not version_doc:
        return None
    return FormVersion.objects(form=form.id, version=version_doc).first()


def _serialize_audit_log(item):
    return BaseSerializer.clean_dict(
        {
            "id": str(item.id),
            "organization_id": item.organization_id,
            "actor_id": item.actor_id,
            "action": item.action,
            "resource_type": item.resource_type,
            "resource_id": item.resource_id,
            "previous_state": item.previous_state,
            "new_state": item.new_state,
            "timestamp": item.timestamp,
            "ip_address": item.ip_address,
            "metadata": item.metadata,
        },
        preserve_fields=("metadata",),
    )


@form_bp.route("/<form_id>/draft", methods=["PUT"])
@jwt_required()
def save_form_draft(form_id):
    """Save a full builder canvas draft and refresh its draft snapshot."""
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    try:
        from uuid import UUID

        try:
            search_id = UUID(form_id) if isinstance(form_id, str) else form_id
        except ValueError:
            return error_response(message="Invalid form ID format", status_code=400)

        form = Form.objects.get(
            id=search_id,
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        project_id = getattr(g, "project_id", None)
        if project_id:
            form_project_ref = form.to_mongo().get("project")
            form_project_id = getattr(form_project_ref, "id", form_project_ref)
            if str(form_project_id) != str(project_id):
                raise DoesNotExist()
        if not has_form_permission(current_user, form, "edit"):
            return error_response(message="Unauthorized", status_code=403)
        form_service.sync_form_canvas(str(form.id), current_user.organization_id, data)
        form_version = form_service.sync_draft_version(
            str(form.id), current_user.organization_id
        )
        version_str = "0.1.0"
        try:
            v_doc = form_version.version
            if v_doc:
                version_str = getattr(v_doc, "version_string", version_str)
        except Exception:
            pass

        return success_response(
            data={
                "form_id": form_id,
                "version_id": str(getattr(form_version, "id", "")),
                "version": version_str,
            },
            message="Draft saved",
        )
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(
            f"Failed to save draft for form {form_id}: {e}", exc_info=True
        )
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/schema", methods=["GET"])
@jwt_required()
def export_form_schema(form_id):
    """Export the current form schema for import, backup, or migration."""
    current_user = get_current_user()
    try:
        form = Form.objects.get(
            id=form_id,
            project=getattr(g, "project_id", None),
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        if not has_form_permission(current_user, form, "view"):
            return error_response(message="Unauthorized", status_code=403)
        latest = FormVersion.objects(form=form.id).order_by("-created_at").first()
        snapshot = latest.resolved_snapshot if latest else {"sections": []}
        form_dict = FormSerializer.serialize(form.to_dict())
        form_dict["sections"] = snapshot.get("sections", [])
        form_dict["translations"] = snapshot.get(
            "translations", form.translations or {}
        )
        audit_logger.info(f"Form schema {form_id} exported by user {current_user.id}")
        return success_response(data=form_dict)
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(
            f"Failed to export schema for form {form_id}: {e}", exc_info=True
        )
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/audit", methods=["GET"])
@jwt_required()
def list_form_audit(form_id):
    current_user = get_current_user()
    try:
        form = Form.objects.get(
            id=form_id,
            project=getattr(g, "project_id", None),
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        if not has_form_permission(current_user, form, "view_audit"):
            return error_response(message="Unauthorized", status_code=403)

        page = max(int(request.args.get("page", 1)), 1)
        page_size = min(max(int(request.args.get("page_size", 25)), 1), 100)
        query = {
            "organization_id": current_user.organization_id,
            "resource_id": form_id,
            "is_deleted": False,
        }
        if request.args.get("action"):
            query["action"] = request.args["action"]
        if request.args.get("actor_id"):
            query["actor_id"] = request.args["actor_id"]

        total = AuditLog.objects(**query).count()
        items = (
            AuditLog.objects(**query)
            .order_by("-timestamp")
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return success_response(
            data={
                "items": [_serialize_audit_log(item) for item in items],
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size,
            }
        )
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(
            f"Failed to list audit for form {form_id}: {e}", exc_info=True
        )
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/theme", methods=["POST"])
@jwt_required()
def apply_form_theme(form_id):
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    try:
        form = Form.objects.get(
            id=form_id,
            project=getattr(g, "project_id", None),
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        if not has_form_permission(current_user, form, "edit_design"):
            return error_response(message="Unauthorized", status_code=403)
        style = form.style or {}
        if "theme_id" in data:
            style["theme_id"] = data["theme_id"]
        if "tokens" in data:
            style["tokens"] = data["tokens"]
        if "branding" in data:
            style["branding"] = data["branding"]
        form.style = style
        form.save()
        form_service.sync_draft_version(str(form.id), current_user.organization_id)
        audit_logger.info(f"Theme applied to form {form_id} by user {current_user.id}")
        return success_response(
            data={"form_id": form_id, "style": style}, message="Theme applied"
        )
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(
            f"Failed to apply theme to form {form_id}: {e}", exc_info=True
        )
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/versions", methods=["GET"])
@jwt_required()
def list_project_form_versions(form_id):
    current_user = get_current_user()
    try:
        form = Form.objects.get(
            id=form_id,
            project=getattr(g, "project_id", None),
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
def get_project_form_version(form_id, version):
    current_user = get_current_user()
    try:
        form = Form.objects.get(
            id=form_id,
            project=getattr(g, "project_id", None),
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        version_doc = (
            Version.objects(form=form.id).order_by("-major", "-minor", "-patch").first()
        )
        if not version_doc:
            return error_response(message="Version not found", status_code=404)
        if version and version != getattr(version_doc, "version_string", None):
            try:
                major, minor, patch = (int(part) for part in version.split("."))
            except (ValueError, TypeError):
                return error_response(message="Version not found", status_code=404)
            matching = Version.objects(
                form=form.id,
                major=major,
                minor=minor,
                patch=patch,
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


@form_bp.route("/<form_id>/versions/<version>/restore", methods=["POST"])
@jwt_required()
def restore_project_form_version(form_id, version):
    current_user = get_current_user()
    try:
        form = Form.objects.get(
            id=form_id,
            project=getattr(g, "project_id", None),
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        if not has_form_permission(current_user, form, "edit"):
            return error_response(message="Unauthorized", status_code=403)
        form_version = _find_form_version(form, version)
        if not form_version:
            return error_response(message="Version not found", status_code=404)

        snapshot = form_version.resolved_snapshot or {}
        canvas = FormSerializer.serialize(form.to_dict())
        canvas["sections"] = snapshot.get("sections", [])
        if snapshot.get("translations") is not None:
            canvas["translations"] = snapshot["translations"]
        if snapshot.get("quick_responses") is not None:
            canvas["quick_responses"] = snapshot["quick_responses"]
        form_service.sync_form_canvas(
            str(form.id), current_user.organization_id, canvas
        )
        restored = form_service.sync_draft_version(
            str(form.id), current_user.organization_id
        )
        audit_logger.info(
            f"Form {form_id} restored to version {version} by user {current_user.id}"
        )
        return success_response(
            data=_serialize_form_version(restored),
            message="Form version restored",
        )
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(
            f"Failed to restore version {version} for form {form_id}: {e}",
            exc_info=True,
        )
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/versions", methods=["POST"])
@jwt_required()
def create_project_form_version(form_id):
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    try:
        form = Form.objects.get(
            id=form_id,
            project=getattr(g, "project_id", None),
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        if any(
            key in data
            for key in ("sections", "versions", "quick_responses", "quickResponses")
        ):
            form_service.sync_form_canvas(
                str(form.id), current_user.organization_id, data
            )
        form_version = form_service.sync_draft_version(
            str(form.id), current_user.organization_id
        )
        audit_logger.info(
            f"AUDIT: Form version created for form {form_id} by user {current_user.id}"
        )
        return success_response(
            data=_serialize_form_version(form_version), status_code=201
        )
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/versions/<version>", methods=["PUT"])
@jwt_required()
def update_project_form_version(form_id, version):
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    try:
        form = Form.objects.get(
            id=form_id,
            project=getattr(g, "project_id", None),
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        form_version = _find_form_version(form, version)
        if not form_version:
            return error_response(message="Version not found", status_code=404)
        if any(
            key in data
            for key in ("sections", "versions", "quick_responses", "quickResponses")
        ):
            form_service.sync_form_canvas(
                str(form.id), current_user.organization_id, data
            )
        form_version = form_service.sync_draft_version(
            str(form.id), current_user.organization_id
        )
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
@swag_from(
    {
        "tags": ["Form"],
        "responses": {
            "200": {
                "description": "Update translation strings for a given language code."
            }
        },
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
def update_form_translations(form_id):
    """Update translation strings for a given language code."""
    app_logger.info(f"Entering update_form_translations for ID {form_id}")
    try:
        current_user = get_current_user()
        # Strictly enforce organization_id in lookup
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id
        )

        if not has_form_permission(current_user, form, "edit"):
            app_logger.warning(
                f"User {current_user.id} unauthorized to update translations for form {form_id}"
            )
            return error_response(message="Unauthorized", status_code=403)

        data = request.get_json(silent=True) or {}
        lang_code = data.get("lang_code")
        translations = data.get(
            "translations"
        )  # Expecting { questions: {}, sections: {}, title: "", description: "" }

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
        audit_logger.info(
            f"Translations for '{lang_code}' updated for form {form_id} by user {current_user.id}"
        )
        return success_response(message=f"Translations for '{lang_code}' updated")
    except DoesNotExist:
        app_logger.warning(f"Form {form_id} not found for translation update")
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Update form translations error for {form_id}: {e}")
        return error_response(message=str(e), status_code=400)


# ───────────────────────────────────────────────────────────────────────────────
# Form Versioning (Git-like)
# ───────────────────────────────────────────────────────────────────────────────


@form_bp.route("/<form_id>/commits", methods=["GET"])
@jwt_required()
@require_permission("form", "view")
def get_form_commits(form_id):
    """Get commit history for a form."""
    app_logger.info(f"Entering get_form_commits for form {form_id}")
    try:
        current_user = get_current_user()
        branch = request.args.get("branch")
        
        # Verify form exists and user has permission
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id, is_deleted=False
        )
        
        if not has_form_permission(current_user, form, "view"):
            return error_response(message="Unauthorized", status_code=403)
        
        commits = form_engine.get_commit_history(
            form_id=form_id,
            organization_id=current_user.organization_id,
            branch=branch
        )
        
        audit_logger.info(
            f"AUDIT: Form commits viewed for form {form_id} by user {current_user.id}"
        )
        return success_response(data=commits)
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Get form commits error for {form_id}: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/commits", methods=["POST"])
@jwt_required()
@require_permission("form", "edit")
def create_form_commit(form_id):
    """Create a new commit for the form."""
    app_logger.info(f"Entering create_form_commit for form {form_id}")
    try:
        current_user = get_current_user()
        data = request.get_json(silent=True) or {}
        
        # Verify form exists and user has permission
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id, is_deleted=False
        )
        
        if not has_form_permission(current_user, form, "edit"):
            return error_response(message="Unauthorized", status_code=403)
        
        content = data.get("content", {})
        message = data.get("message", "Updated form")
        branch = data.get("branch", "main")
        
        commit = form_service.create_form_commit(
            form_id=form_id,
            organization_id=current_user.organization_id,
            content=content,
            message=message,
            branch=branch,
            author_id=str(current_user.id)
        )
        
        audit_logger.info(
            f"AUDIT: Form commit created for form {form_id} by user {current_user.id}"
        )
        return success_response(data=commit, message="Commit created", status_code=201)
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Create form commit error for {form_id}: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/branches", methods=["POST"])
@jwt_required()
@require_permission("form", "edit")
def create_form_branch(form_id):
    """Create a new branch for the form."""
    app_logger.info(f"Entering create_form_branch for form {form_id}")
    try:
        current_user = get_current_user()
        data = request.get_json(silent=True) or {}
        
        # Verify form exists and user has permission
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id, is_deleted=False
        )
        
        if not has_form_permission(current_user, form, "edit"):
            return error_response(message="Unauthorized", status_code=403)
        
        branch_name = data.get("branch_name")
        from_commit_id = data.get("from_commit_id")
        
        if not branch_name:
            return error_response(message="Branch name is required", status_code=400)
        
        branch = form_service.create_form_branch(
            form_id=form_id,
            organization_id=current_user.organization_id,
            branch_name=branch_name,
            from_commit_id=from_commit_id,
            author_id=str(current_user.id)
        )
        
        audit_logger.info(
            f"AUDIT: Form branch '{branch_name}' created for form {form_id} by user {current_user.id}"
        )
        return success_response(data=branch, message="Branch created", status_code=201)
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Create form branch error for {form_id}: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/branches", methods=["GET"])
@jwt_required()
@require_permission("form", "view")
def get_form_branches(form_id):
    """Get all branches for a form."""
    app_logger.info(f"Entering get_form_branches for form {form_id}")
    try:
        current_user = get_current_user()
        
        # Verify form exists and user has permission
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id, is_deleted=False
        )
        
        if not has_form_permission(current_user, form, "view"):
            return error_response(message="Unauthorized", status_code=403)
        
        branches = form_service.get_form_branches(
            form_id=form_id,
            organization_id=current_user.organization_id
        )
        
        audit_logger.info(
            f"AUDIT: Form branches viewed for form {form_id} by user {current_user.id}"
        )
        return success_response(data=branches)
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Get form branches error for {form_id}: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/merge", methods=["POST"])
@jwt_required()
@require_permission("form", "edit")
def merge_form_branch(form_id):
    """Merge source branch into target branch."""
    app_logger.info(f"Entering merge_form_branch for form {form_id}")
    try:
        current_user = get_current_user()
        data = request.get_json(silent=True) or {}
        
        # Verify form exists and user has permission
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id, is_deleted=False
        )
        
        if not has_form_permission(current_user, form, "edit"):
            return error_response(message="Unauthorized", status_code=403)
        
        source_branch = data.get("source_branch")
        target_branch = data.get("target_branch", "main")
        message = data.get("message")
        
        theirs_commit_id = data.get("theirs_commit_id")
        mine_commit_id = data.get("mine_commit_id")
        resolutions = data.get("resolutions")
        
        if not source_branch and not mine_commit_id:
            return error_response(message="Source branch or mine_commit_id is required", status_code=400)
        
        result = form_service.merge_form_branch(
            form_id=form_id,
            organization_id=current_user.organization_id,
            source_branch=source_branch,
            target_branch=target_branch,
            author_id=str(current_user.id),
            message=message,
            source_commit_id=mine_commit_id,
            target_commit_id=theirs_commit_id,
            resolutions=resolutions
        )
        
        audit_logger.info(
            f"AUDIT: Form branch merged for form {form_id} by user {current_user.id}"
        )
        return success_response(data=result, message="Merge status updated")
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Merge form branch error for {form_id}: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/branches/<branch_name>/set-production", methods=["POST"])
@jwt_required()
@require_permission("form", "edit")
def set_form_production_branch(form_id, branch_name):
    """Set a branch as the production branch."""
    app_logger.info(f"Entering set_form_production_branch for form {form_id}")
    try:
        current_user = get_current_user()
        
        # Verify form exists and user has permission
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id, is_deleted=False
        )
        
        if not has_form_permission(current_user, form, "edit"):
            return error_response(message="Unauthorized", status_code=403)
        
        result = form_service.set_production_branch(
            form_id=form_id,
            organization_id=current_user.organization_id,
            branch_name=branch_name
        )
        
        audit_logger.info(
            f"AUDIT: Form production branch set to '{branch_name}' for form {form_id} by user {current_user.id}"
        )
        return success_response(data=result, message="Production branch updated")
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Set form production branch error for {form_id}: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<form_id>/commits/<commit_id>", methods=["GET"])
@jwt_required()
@require_permission("form", "view")
def get_form_commit(form_id, commit_id):
    """Get form schema at a specific commit."""
    app_logger.info(f"Entering get_form_commit for form {form_id}, commit {commit_id}")
    try:
        current_user = get_current_user()
        
        # Verify form exists and user has permission
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id, is_deleted=False
        )
        
        if not has_form_permission(current_user, form, "view"):
            return error_response(message="Unauthorized", status_code=403)
        
        form_schema = form_service.get_form_at_commit(
            form_id=form_id,
            commit_id=commit_id,
            organization_id=current_user.organization_id
        )
        
        audit_logger.info(
            f"AUDIT: Form commit viewed for form {form_id}, commit {commit_id} by user {current_user.id}"
        )
        return success_response(data=form_schema)
    except DoesNotExist:
        return error_response(message="Form or commit not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Get form commit error for {form_id}: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)
