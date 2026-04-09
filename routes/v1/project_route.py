from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from flasgger import swag_from
from mongoengine import DoesNotExist

from logger.unified_logger import app_logger, error_logger, audit_logger
from utils.response_helper import success_response, error_response
from routes.v1.form.helper import get_current_user
from services.form_service import ProjectService, ProjectCreateSchema, ProjectUpdateSchema
from services.access_control_service import AccessControlService
from models.Form import Project

project_bp = Blueprint("project_bp", __name__)
project_service = ProjectService()


@project_bp.route("/", methods=["POST"])
@swag_from({
    "tags": ["Project"],
    "parameters": [{"name": "body", "in": "body", "schema": {"$ref": "#/definitions/ProjectSchema"}}],
    "responses": {"201": {"description": "Project created"}},
})
@jwt_required()
def create_project():
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    try:
        data["organization_id"] = current_user.organization_id
        schema = ProjectCreateSchema(**data)
        project = project_service.create(schema)
        audit_logger.info(f"AUDIT: Project created with ID {project.id} by user {current_user.id}")
        return success_response(data=project.model_dump(), message="Project created", status_code=201)
    except Exception as e:
        error_logger.error(f"Create project error: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@project_bp.route("/", methods=["GET"])
@jwt_required()
def list_projects():
    current_user = get_current_user()
    try:
        result = project_service.list_paginated(organization_id=current_user.organization_id)
        return success_response(data=result.to_dict())
    except Exception as e:
        error_logger.error(f"List projects error: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@project_bp.route("/<project_id>", methods=["GET"])
@jwt_required()
def get_project(project_id):
    current_user = get_current_user()
    try:
        project = project_service.get_by_id(project_id, organization_id=current_user.organization_id)
        return success_response(data=project.model_dump())
    except Exception as e:
        error_logger.error(f"Get project error: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@project_bp.route("/<project_id>", methods=["PUT"])
@jwt_required()
def update_project(project_id):
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    try:
        schema = ProjectUpdateSchema(**data)
        project = project_service.update(project_id, schema, organization_id=current_user.organization_id)
        audit_logger.info(f"AUDIT: Project updated with ID {project_id} by user {current_user.id}")
        return success_response(data=project.model_dump(), message="Project updated")
    except Exception as e:
        error_logger.error(f"Update project error: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@project_bp.route("/<project_id>", methods=["DELETE"])
@jwt_required()
def delete_project(project_id):
    current_user = get_current_user()
    try:
        project_service.delete(project_id, organization_id=current_user.organization_id)
        audit_logger.info(f"AUDIT: Project deleted with ID {project_id} by user {current_user.id}")
        return success_response(message="Project deleted")
    except Exception as e:
        error_logger.error(f"Delete project error: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@project_bp.route("/<project_id>/forms", methods=["POST"])
@jwt_required()
def create_form_in_project(project_id):
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    try:
        project = Project.objects.get(
            id=project_id,
            organization_id=current_user.organization_id,
            is_deleted=False,
        )
        if not AccessControlService.check_project_permission(current_user, project, "edit"):
            audit_logger.info(
                f"AUDIT: Unauthorized form creation attempt in project {project_id} by user {current_user.id}"
            )
            return error_response(message="Unauthorized to manage this project", status_code=403)
        form = project_service.create_form_in_project(
            project_id, data, current_user.organization_id, current_user
        )
        audit_logger.info(f"AUDIT: Form {form.id} created in project {project_id} by user {current_user.id}")
        return success_response(data=form.model_dump(), message="Form created in project", status_code=201)
    except DoesNotExist:
        return error_response(message="Project not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Create form in project error: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@project_bp.route("/<project_id>/forms", methods=["GET"])
@jwt_required()
def list_forms_in_project(project_id):
    current_user = get_current_user()
    try:
        result = project_service.list_forms_in_project(project_id, organization_id=current_user.organization_id)
        return success_response(data=[item.model_dump() for item in result])
    except Exception as e:
        error_logger.error(f"List forms in project error: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)
