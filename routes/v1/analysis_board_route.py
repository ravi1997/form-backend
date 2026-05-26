from flask import Blueprint, request
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from models.Form import Project
from services.analysis_board_service import AnalysisBoardService
from schemas.analysis_board import (
    AnalysisBoardCreateSchema,
    AnalysisBoardUpdateSchema,
)
from utils.response_helper import success_response, error_response
from utils.security_helpers import require_permission
from utils.exceptions import NotFoundError, ValidationError, ForbiddenError
from logger.unified_logger import app_logger, error_logger, audit_logger

analysis_board_bp = Blueprint("analysis_board", __name__)
analysis_board_service = AnalysisBoardService()


@analysis_board_bp.route("/", methods=["POST"])
@swag_from({
    "tags": ["Analysis Board"],
    "summary": "Create a new Analysis Board in a Project",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the parent Project"
        },
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "$ref": "#/definitions/AnalysisBoardCreateSchema"
            }
        }
    ],
    "responses": {
        "201": {
            "description": "Analysis Board created successfully"
        },
        "400": {
            "description": "Invalid input data"
        },
        "404": {
            "description": "Project not found"
        }
    }
})
@jwt_required()
@require_permission("project", "edit")
def create_board(project_id):
    """Create a new Analysis Board in a Project."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(f"User {user_id} creating Analysis Board in project {project_id} for org {org_id}")

    try:
        # Verify Project exists and belongs to organization
        project = Project.objects(id=project_id, organization_id=org_id, is_deleted=False).first()
        if not project:
            raise NotFoundError(f"Project {project_id} not found")

        data = request.get_json() or {}
        data["project_id"] = project_id
        data["organization_id"] = org_id
        data["created_by"] = user_id

        schema = AnalysisBoardCreateSchema(**data)
        result = analysis_board_service.create(schema)

        audit_logger.info(
            f"Analysis Board created: ID={result.id}, Title='{result.title}', ProjectID={project_id}, OrgID={org_id}"
        )
        return success_response(data=result.model_dump(), message="Analysis Board created", status_code=201)
    except Exception as e:
        error_logger.error(f"Create Analysis Board error: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@analysis_board_bp.route("/", methods=["GET"])
@swag_from({
    "tags": ["Analysis Board"],
    "summary": "List all active Analysis Boards in a Project",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the parent Project"
        },
        {
            "name": "page",
            "in": "query",
            "type": "integer",
            "default": 1
        },
        {
            "name": "page_size",
            "in": "query",
            "type": "integer",
            "default": 50
        }
    ],
    "responses": {
        "200": {
            "description": "List of active Analysis Boards"
        }
    }
})
@jwt_required()
@require_permission("project", "view")
def list_boards(project_id):
    """List all active Analysis Boards in a Project."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))
    app_logger.info(f"User {user_id} listing Analysis Boards in project {project_id} for org {org_id}")

    try:
        result = analysis_board_service.list_paginated(
            page=page,
            page_size=page_size,
            project_id=project_id,
            organization_id=org_id,
            is_deleted=False
        )
        return success_response(data=result.to_dict())
    except Exception as e:
        error_logger.error(f"List Analysis Boards error: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@analysis_board_bp.route("/<board_id>", methods=["GET"])
@swag_from({
    "tags": ["Analysis Board"],
    "summary": "Retrieve an Analysis Board by ID",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True
        },
        {
            "name": "board_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ],
    "responses": {
        "200": {
            "description": "Analysis Board details"
        },
        "404": {
            "description": "Analysis Board not found"
        }
    }
})
@jwt_required()
@require_permission("project", "view")
def get_board(project_id, board_id):
    """Retrieve an Analysis Board by ID."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(f"User {user_id} retrieving Analysis Board {board_id}")

    try:
        result = analysis_board_service.get_by_id(board_id, organization_id=org_id)
        if result.project_id != project_id:
            raise NotFoundError("Analysis Board not found in this project")
        return success_response(data=result.model_dump())
    except Exception as e:
        error_logger.error(f"Get Analysis Board error: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=404)


@analysis_board_bp.route("/<board_id>", methods=["PUT"])
@swag_from({
    "tags": ["Analysis Board"],
    "summary": "Update an Analysis Board",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True
        },
        {
            "name": "board_id",
            "in": "path",
            "type": "string",
            "required": True
        },
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "$ref": "#/definitions/AnalysisBoardUpdateSchema"
            }
        }
    ],
    "responses": {
        "200": {
            "description": "Analysis Board updated successfully"
        },
        "404": {
            "description": "Analysis Board not found"
        }
    }
})
@jwt_required()
@require_permission("project", "edit")
def update_board(project_id, board_id):
    """Update an Analysis Board."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(f"User {user_id} updating Analysis Board {board_id}")

    try:
        board = analysis_board_service.get_by_id(board_id, organization_id=org_id)
        if board.project_id != project_id:
            raise NotFoundError("Analysis Board not found in this project")

        data = request.get_json() or {}
        schema = AnalysisBoardUpdateSchema(**data)
        result = analysis_board_service.update(board_id, schema, organization_id=org_id)

        audit_logger.info(
            f"Analysis Board updated: ID={board_id}, Title='{result.title}', ProjectID={project_id}, OrgID={org_id}"
        )
        return success_response(data=result.model_dump(), message="Analysis Board updated")
    except Exception as e:
        error_logger.error(f"Update Analysis Board error: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@analysis_board_bp.route("/<board_id>", methods=["DELETE"])
@swag_from({
    "tags": ["Analysis Board"],
    "summary": "Delete an Analysis Board",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True
        },
        {
            "name": "board_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ],
    "responses": {
        "200": {
            "description": "Analysis Board deleted successfully"
        },
        "404": {
            "description": "Analysis Board not found"
        }
    }
})
@jwt_required()
@require_permission("project", "edit")
def delete_board(project_id, board_id):
    """Delete an Analysis Board."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(f"User {user_id} deleting Analysis Board {board_id}")

    try:
        board = analysis_board_service.get_by_id(board_id, organization_id=org_id)
        if board.project_id != project_id:
            raise NotFoundError("Analysis Board not found in this project")

        analysis_board_service.delete(board_id, organization_id=org_id)
        audit_logger.info(
            f"Analysis Board deleted: ID={board_id}, ProjectID={project_id}, OrgID={org_id}"
        )
        return success_response(message="Analysis Board deleted")
    except Exception as e:
        error_logger.error(f"Delete Analysis Board error: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@analysis_board_bp.route("/<board_id>/execute", methods=["GET"])
@swag_from({
    "tags": ["Analysis Board"],
    "summary": "Execute calculations on an Analysis Board",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True
        },
        {
            "name": "board_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ],
    "responses": {
        "200": {
            "description": "Calculations executed successfully, returning resolved node value map"
        },
        "404": {
            "description": "Analysis Board not found"
        }
    }
})
@jwt_required()
@require_permission("project", "view")
def execute_board(project_id, board_id):
    """Execute calculations on an Analysis Board."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(f"User {user_id} executing Analysis Board {board_id}")

    try:
        # Verify board exists in project & org
        board = analysis_board_service.get_by_id(board_id, organization_id=org_id)
        if board.project_id != project_id:
            raise NotFoundError("Analysis Board not found in this project")

        results = analysis_board_service.execute_board(board_id, org_id)
        return success_response(data=results, message="Calculations executed successfully")
    except Exception as e:
        error_logger.error(f"Execute Analysis Board error: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)
