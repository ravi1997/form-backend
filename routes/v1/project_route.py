from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from flasgger import swag_from

from logger.unified_logger import app_logger, audit_logger
from utils.response_helper import success_response, error_response
from routes.v1.form.helper import get_current_user
from services.form_service import (
    ProjectService,
    ProjectCreateSchema,
    ProjectUpdateSchema,
)
from services.access_control_service import AccessControlService
from models.Form import Project

project_bp = Blueprint("project_bp", __name__)
project_service = ProjectService()


@project_bp.route("/", methods=["POST"])
@swag_from(
    {
        "tags": ["Project"],
        "parameters": [
            {
                "name": "body",
                "in": "body",
                "schema": {"$ref": "#/definitions/ProjectSchema"},
            }
        ],
        "responses": {"201": {"description": "Project created"}},
    }
)
@jwt_required()
def create_project():
    """Create a new project for the current organization."""
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    data["organization_id"] = current_user.organization_id
    schema = ProjectCreateSchema(**data)
    project = project_service.create(schema)
    audit_logger.info(
        f"AUDIT: Project created with ID {project.id} by user {current_user.id}"
    )
    return success_response(
        data=project.model_dump(by_alias=True), message="Project created", status_code=201
    )


@project_bp.route("/", methods=["GET"])
@jwt_required()
def list_projects():
    """List all projects for the current organization."""
    current_user = get_current_user()
    result = project_service.list_paginated(
        organization_id=current_user.organization_id
    )
    return success_response(data=result.to_dict())


@project_bp.route("/<project_id>", methods=["GET"])
@jwt_required()
def get_project(project_id):
    """Get a project by ID."""
    current_user = get_current_user()
    project = project_service.get_by_id(
        project_id, organization_id=current_user.organization_id
    )
    return success_response(data=project.model_dump(by_alias=True))


@project_bp.route("/<project_id>", methods=["PUT"])
@jwt_required()
def update_project(project_id):
    """Update a project by ID."""
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    schema = ProjectUpdateSchema(**data)
    project = project_service.update(
        project_id, schema, organization_id=current_user.organization_id
    )
    audit_logger.info(
        f"AUDIT: Project updated with ID {project_id} by user {current_user.id}"
    )
    return success_response(
        data=project.model_dump(by_alias=True), message="Project updated"
    )


@project_bp.route("/<project_id>", methods=["DELETE"])
@jwt_required()
def delete_project(project_id):
    """Soft-delete a project by ID."""
    current_user = get_current_user()
    project_service.delete(project_id, organization_id=current_user.organization_id)
    audit_logger.info(
        f"AUDIT: Project deleted with ID {project_id} by user {current_user.id}"
    )
    return success_response(message="Project deleted")


@project_bp.route("/<project_id>/forms", methods=["POST"])
@jwt_required()
def create_form_in_project(project_id):
    """Create a form scoped to a specific project."""
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}

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
            message="Unauthorized to manage this project", status_code=403
        )

    form = project_service.create_form_in_project(
        project_id, data, current_user.organization_id, current_user
    )
    audit_logger.info(
        f"AUDIT: Form {form.id} created in project {project_id} by user {current_user.id}"
    )
    return success_response(
        data=form.model_dump(by_alias=True), message="Form created in project", status_code=201
    )


@project_bp.route("/<project_id>/forms", methods=["GET"])
@jwt_required()
def list_forms_in_project(project_id):
    """List all forms within a specific project."""
    current_user = get_current_user()
    result = project_service.list_forms_in_project(
        project_id, organization_id=current_user.organization_id
    )
    return success_response(data=result)
