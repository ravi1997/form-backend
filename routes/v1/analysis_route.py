"""
routes/v1/analysis_route.py
API routes for analysis operations.
"""

import os
from flask import Blueprint, request, send_file
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from models.project import Project
from services.analysis_service import analysis_service
from services.export_service import export_service
from schemas.analysis import (
    AnalysisCreateSchema, 
    AnalysisUpdateSchema,
    AnalysisResponseSchema,
    AnalysisRunResponseSchema,
    AnalysisResultSchema,
    AnalysisExportSchema
)
from utils.response_helper import success_response, error_response
from utils.security_helpers import require_permission
from utils.exceptions import NotFoundError, ValidationError, StateTransitionError
from logger.unified_logger import app_logger, error_logger, audit_logger
from tasks.analysis_tasks import execute_analysis

analysis_bp = Blueprint("analysis", __name__)


@analysis_bp.route("/projects/<project_id>/analyses", methods=["POST"])
@swag_from({
    "tags": ["Analysis"],
    "summary": "Create a new analysis",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the parent project"
        },
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {"$ref": "#/definitions/AnalysisCreateSchema"}
        }
    ],
    "responses": {
        "201": {"description": "Analysis created successfully"},
        "400": {"description": "Invalid input data"},
        "404": {"description": "Project not found"}
    }
})
@jwt_required()
@require_permission("project", "edit")
def create_analysis(project_id):
    """Create a new analysis."""
    try:
        user_id = get_jwt_identity()
        org_id = get_jwt().get("org_id")
        
        # Verify project exists and belongs to organization
        project = Project.objects(
            id=project_id, 
            organization_id=org_id, 
            is_deleted=False
        ).first()
        
        if not project:
            return error_response("Project not found", 404)
        
        # Validate and parse request data
        data = request.get_json()
        if not data:
            return error_response("No data provided", 400)
        
        # Add project_id to data
        data["project_id"] = project_id
        
        # Create analysis
        schema = AnalysisCreateSchema(**data)
        analysis = analysis_service.create_analysis(
            schema=schema,
            organization_id=org_id,
            created_by=user_id
        )
        
        audit_logger.info(
            f"Analysis created: ID={analysis.id}, Name='{analysis.name}', "
            f"ProjectID={project_id}, OrgID={org_id}"
        )
        
        return success_response(
            data=analysis.to_dict(),
            message="Analysis created successfully",
            status_code=201
        )
        
    except ValidationError as e:
        return error_response(str(e), 400)
    except Exception as e:
        error_logger.error(f"Create analysis error: {str(e)}", exc_info=True)
        return error_response("Internal server error", 500)


@analysis_bp.route("/projects/<project_id>/analyses", methods=["GET"])
@swag_from({
    "tags": ["Analysis"],
    "summary": "List analyses for a project",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the project"
        },
        {"name": "page", "in": "query", "type": "integer", "default": 1},
        {"name": "page_size", "in": "query", "type": "integer", "default": 50}
    ],
    "responses": {
        "200": {"description": "List of analyses"}
    }
})
@jwt_required()
@require_permission("project", "view")
def list_analyses(project_id):
    """List analyses for a project."""
    try:
        user_id = get_jwt_identity()
        org_id = get_jwt().get("org_id")
        
        # Verify project exists
        project = Project.objects(
            id=project_id, 
            organization_id=org_id, 
            is_deleted=False
        ).first()
        
        if not project:
            return error_response("Project not found", 404)
        
        # Get pagination parameters
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 50))
        
        # List analyses
        analyses, total = analysis_service.list_analyses(
            organization_id=org_id,
            project_id=project_id,
            page=page,
            page_size=page_size
        )
        
        # Convert to response format
        analysis_data = [analysis.to_dict() for analysis in analyses]
        
        return success_response(data={
            "items": analysis_data,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size
        })
        
    except Exception as e:
        error_logger.error(f"List analyses error: {str(e)}", exc_info=True)
        return error_response("Internal server error", 500)


@analysis_bp.route("/projects/<project_id>/analyses/<analysis_id>", methods=["GET"])
@swag_from({
    "tags": ["Analysis"],
    "summary": "Get analysis details",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the project"
        },
        {
            "name": "analysis_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the analysis"
        }
    ],
    "responses": {
        "200": {"description": "Analysis details"},
        "404": {"description": "Analysis not found"}
    }
})
@jwt_required()
@require_permission("project", "view")
def get_analysis(project_id, analysis_id):
    """Get analysis details."""
    try:
        user_id = get_jwt_identity()
        org_id = get_jwt().get("org_id")
        
        # Verify project exists
        project = Project.objects(
            id=project_id, 
            organization_id=org_id, 
            is_deleted=False
        ).first()
        
        if not project:
            return error_response("Project not found", 404)
        
        # Get analysis
        analysis = analysis_service.get_analysis(analysis_id, org_id)
        
        # Verify analysis belongs to project
        if str(analysis.project_id) != project_id:
            return error_response("Analysis not found in this project", 404)
        
        return success_response(data=analysis.to_dict())
        
    except NotFoundError as e:
        return error_response(str(e), 404)
    except Exception as e:
        error_logger.error(f"Get analysis error: {str(e)}", exc_info=True)
        return error_response("Internal server error", 500)


@analysis_bp.route("/projects/<project_id>/analyses/<analysis_id>", methods=["PUT"])
@swag_from({
    "tags": ["Analysis"],
    "summary": "Update analysis",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the project"
        },
        {
            "name": "analysis_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the analysis"
        },
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {"$ref": "#/definitions/AnalysisUpdateSchema"}
        }
    ],
    "responses": {
        "200": {"description": "Analysis updated successfully"},
        "400": {"description": "Invalid input data"},
        "404": {"description": "Analysis not found"}
    }
})
@jwt_required()
@require_permission("project", "edit")
def update_analysis(project_id, analysis_id):
    """Update analysis."""
    try:
        user_id = get_jwt_identity()
        org_id = get_jwt().get("org_id")
        
        # Verify project exists
        project = Project.objects(
            id=project_id, 
            organization_id=org_id, 
            is_deleted=False
        ).first()
        
        if not project:
            return error_response("Project not found", 404)
        
        # Get analysis
        analysis = analysis_service.get_analysis(analysis_id, org_id)
        
        # Verify analysis belongs to project
        if str(analysis.project_id) != project_id:
            return error_response("Analysis not found in this project", 404)
        
        # Validate and parse request data
        data = request.get_json()
        if not data:
            return error_response("No data provided", 400)
        
        # Update analysis
        schema = AnalysisUpdateSchema(**data)
        updated_analysis = analysis_service.update_analysis(
            analysis_id=analysis_id,
            schema=schema,
            organization_id=org_id
        )
        
        return success_response(
            data=updated_analysis.to_dict(),
            message="Analysis updated successfully"
        )
        
    except ValidationError as e:
        return error_response(str(e), 400)
    except NotFoundError as e:
        return error_response(str(e), 404)
    except Exception as e:
        error_logger.error(f"Update analysis error: {str(e)}", exc_info=True)
        return error_response("Internal server error", 500)


@analysis_bp.route("/projects/<project_id>/analyses/<analysis_id>", methods=["DELETE"])
@swag_from({
    "tags": ["Analysis"],
    "summary": "Delete analysis",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the project"
        },
        {
            "name": "analysis_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the analysis"
        }
    ],
    "responses": {
        "200": {"description": "Analysis deleted successfully"},
        "404": {"description": "Analysis not found"}
    }
})
@jwt_required()
@require_permission("project", "edit")
def delete_analysis(project_id, analysis_id):
    """Delete analysis."""
    try:
        user_id = get_jwt_identity()
        org_id = get_jwt().get("org_id")
        
        # Verify project exists
        project = Project.objects(
            id=project_id, 
            organization_id=org_id, 
            is_deleted=False
        ).first()
        
        if not project:
            return error_response("Project not found", 404)
        
        # Get analysis
        analysis = analysis_service.get_analysis(analysis_id, org_id)
        
        # Verify analysis belongs to project
        if str(analysis.project_id) != project_id:
            return error_response("Analysis not found in this project", 404)
        
        # Delete analysis
        analysis_service.delete_analysis(analysis_id, org_id)
        
        return success_response(message="Analysis deleted successfully")
        
    except NotFoundError as e:
        return error_response(str(e), 404)
    except Exception as e:
        error_logger.error(f"Delete analysis error: {str(e)}", exc_info=True)
        return error_response("Internal server error", 500)


@analysis_bp.route("/projects/<project_id>/analyses/<analysis_id>/execute", methods=["POST"])
@swag_from({
    "tags": ["Analysis"],
    "summary": "Execute analysis",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the project"
        },
        {
            "name": "analysis_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the analysis"
        }
    ],
    "responses": {
        "200": {"description": "Analysis execution started"},
        "404": {"description": "Analysis not found"}
    }
})
@jwt_required()
@require_permission("project", "view")
def execute_analysis_endpoint(project_id, analysis_id):
    """Execute analysis."""
    try:
        user_id = get_jwt_identity()
        org_id = get_jwt().get("org_id")
        
        # Verify project exists
        project = Project.objects(
            id=project_id, 
            organization_id=org_id, 
            is_deleted=False
        ).first()
        
        if not project:
            return error_response("Project not found", 404)
        
        # Get analysis
        analysis = analysis_service.get_analysis(analysis_id, org_id)
        
        # Verify analysis belongs to project
        if str(analysis.project_id) != project_id:
            return error_response("Analysis not found in this project", 404)
        
        # Execute analysis asynchronously
        task = execute_analysis.delay(
            analysis_id=analysis_id,
            organization_id=org_id,
            trigger="manual",
            triggered_by=user_id
        )
        
        return success_response(
            data={
                "task_id": task.id,
                "analysis_id": analysis_id,
                "status": "queued"
            },
            message="Analysis execution started"
        )
        
    except NotFoundError as e:
        return error_response(str(e), 404)
    except Exception as e:
        error_logger.error(f"Execute analysis error: {str(e)}", exc_info=True)
        return error_response("Internal server error", 500)


@analysis_bp.route("/projects/<project_id>/analyses/<analysis_id>/runs", methods=["GET"])
@swag_from({
    "tags": ["Analysis"],
    "summary": "List analysis runs",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the project"
        },
        {
            "name": "analysis_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the analysis"
        },
        {"name": "page", "in": "query", "type": "integer", "default": 1},
        {"name": "page_size", "in": "query", "type": "integer", "default": 50}
    ],
    "responses": {
        "200": {"description": "List of analysis runs"}
    }
})
@jwt_required()
@require_permission("project", "view")
def list_analysis_runs(project_id, analysis_id):
    """List analysis runs."""
    try:
        user_id = get_jwt_identity()
        org_id = get_jwt().get("org_id")
        
        # Verify project exists
        project = Project.objects(
            id=project_id, 
            organization_id=org_id, 
            is_deleted=False
        ).first()
        
        if not project:
            return error_response("Project not found", 404)
        
        # Get analysis
        analysis = analysis_service.get_analysis(analysis_id, org_id)
        
        # Verify analysis belongs to project
        if str(analysis.project_id) != project_id:
            return error_response("Analysis not found in this project", 404)
        
        # Get pagination parameters
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 50))
        
        # List analysis runs
        from models.analysis import AnalysisRun
        runs = AnalysisRun.objects(
            analysis_id=analysis,
            organization_id=org_id,
            is_deleted=False
        ).order_by('-created_at')
        
        total = runs.count()
        runs = runs.skip((page - 1) * page_size).limit(page_size)
        
        # Convert to response format
        run_data = [run.to_dict() for run in runs]
        
        return success_response(data={
            "items": run_data,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size
        })
        
    except Exception as e:
        error_logger.error(f"List analysis runs error: {str(e)}", exc_info=True)
        return error_response("Internal server error", 500)


@analysis_bp.route("/projects/<project_id>/analyses/<analysis_id>/runs/<run_id>", methods=["GET"])
@swag_from({
    "tags": ["Analysis"],
    "summary": "Get analysis run details",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the project"
        },
        {
            "name": "analysis_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the analysis"
        },
        {
            "name": "run_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the run"
        }
    ],
    "responses": {
        "200": {"description": "Analysis run details"},
        "404": {"description": "Analysis run not found"}
    }
})
@jwt_required()
@require_permission("project", "view")
def get_analysis_run(project_id, analysis_id, run_id):
    """Get analysis run details."""
    try:
        user_id = get_jwt_identity()
        org_id = get_jwt().get("org_id")
        
        # Verify project exists
        project = Project.objects(
            id=project_id, 
            organization_id=org_id, 
            is_deleted=False
        ).first()
        
        if not project:
            return error_response("Project not found", 404)
        
        # Get analysis
        analysis = analysis_service.get_analysis(analysis_id, org_id)
        
        # Verify analysis belongs to project
        if str(analysis.project_id) != project_id:
            return error_response("Analysis not found in this project", 404)
        
        # Get analysis run
        from models.analysis import AnalysisRun
        run = AnalysisRun.objects(
            id=run_id,
            analysis_id=analysis,
            organization_id=org_id,
            is_deleted=False
        ).first()
        
        if not run:
            return error_response("Analysis run not found", 404)
        
        # Get results for this run
        results = analysis_service.get_analysis_results(
            analysis_id=analysis_id,
            run_id=run_id,
            organization_id=org_id
        )
        
        return success_response(data={
            "run": run.to_dict(),
            "results": [result.to_dict() for result in results]
        })
        
    except NotFoundError as e:
        return error_response(str(e), 404)
    except Exception as e:
        error_logger.error(f"Get analysis run error: {str(e)}", exc_info=True)
        return error_response("Internal server error", 500)


@analysis_bp.route("/projects/<project_id>/analyses/<analysis_id>/exports", methods=["POST"])
@swag_from({
    "tags": ["Analysis"],
    "summary": "Create analysis export",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the project"
        },
        {
            "name": "analysis_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the analysis"
        },
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["csv", "excel", "pdf"]},
                    "node_ids": {"type": "array", "items": {"type": "string"}},
                    "run_id": {"type": "string"},
                    "filename": {"type": "string"}
                },
                "required": ["format"]
            }
        }
    ],
    "responses": {
        "201": {"description": "Export created successfully"},
        "400": {"description": "Invalid input data"}
    }
})
@jwt_required()
@require_permission("project", "view")
def create_analysis_export(project_id, analysis_id):
    """Create analysis export."""
    try:
        user_id = get_jwt_identity()
        org_id = get_jwt().get("org_id")
        
        # Verify project exists
        project = Project.objects(
            id=project_id, 
            organization_id=org_id, 
            is_deleted=False
        ).first()
        
        if not project:
            return error_response("Project not found", 404)
        
        # Get analysis
        analysis = analysis_service.get_analysis(analysis_id, org_id)
        
        # Verify analysis belongs to project
        if str(analysis.project_id) != project_id:
            return error_response("Analysis not found in this project", 404)
        
        # Validate and parse request data
        data = request.get_json()
        if not data:
            return error_response("No data provided", 400)
        
        # Create export
        export = analysis_service.create_export(
            analysis_id=analysis_id,
            organization_id=org_id,
            format=data.get("format"),
            node_ids=data.get("node_ids"),
            run_id=data.get("run_id"),
            created_by=user_id,
            filename=data.get("filename")
        )
        
        # Queue export generation
        from tasks.analysis_tasks import generate_export
        generate_export.delay(str(export.id))
        
        return success_response(
            data=export.to_dict(),
            message="Export created successfully",
            status_code=201
        )
        
    except ValidationError as e:
        return error_response(str(e), 400)
    except Exception as e:
        error_logger.error(f"Create analysis export error: {str(e)}", exc_info=True)
        return error_response("Internal server error", 500)


@analysis_bp.route("/projects/<project_id>/analyses/<analysis_id>/exports/<export_id>", methods=["GET"])
@swag_from({
    "tags": ["Analysis"],
    "summary": "Get analysis export",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the project"
        },
        {
            "name": "analysis_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the analysis"
        },
        {
            "name": "export_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the export"
        }
    ],
    "responses": {
        "200": {"description": "Export details"},
        "404": {"description": "Export not found"}
    }
})
@jwt_required()
@require_permission("project", "view")
def get_analysis_export(project_id, analysis_id, export_id):
    """Get analysis export."""
    try:
        user_id = get_jwt_identity()
        org_id = get_jwt().get("org_id")
        
        # Verify project exists
        project = Project.objects(
            id=project_id, 
            organization_id=org_id, 
            is_deleted=False
        ).first()
        
        if not project:
            return error_response("Project not found", 404)
        
        # Get analysis
        analysis = analysis_service.get_analysis(analysis_id, org_id)
        
        # Verify analysis belongs to project
        if str(analysis.project_id) != project_id:
            return error_response("Analysis not found in this project", 404)
        
        # Get export
        export = export_service.get_export(export_id, org_id)
        
        return success_response(data=export.to_dict())
        
    except NotFoundError as e:
        return error_response(str(e), 404)
    except Exception as e:
        error_logger.error(f"Get analysis export error: {str(e)}", exc_info=True)
        return error_response("Internal server error", 500)


@analysis_bp.route("/projects/<project_id>/analyses/<analysis_id>/exports/<export_id>/download", methods=["GET"])
@swag_from({
    "tags": ["Analysis"],
    "summary": "Download analysis export",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the project"
        },
        {
            "name": "analysis_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the analysis"
        },
        {
            "name": "export_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the export"
        }
    ],
    "responses": {
        "200": {"description": "Export file"},
        "400": {"description": "Export not ready"},
        "404": {"description": "Export not found"}
    }
})
@jwt_required()
@require_permission("project", "view")
def download_analysis_export(project_id, analysis_id, export_id):
    """Download analysis export."""
    try:
        user_id = get_jwt_identity()
        org_id = get_jwt().get("org_id")
        
        # Verify project exists
        project = Project.objects(
            id=project_id, 
            organization_id=org_id, 
            is_deleted=False
        ).first()
        
        if not project:
            return error_response("Project not found", 404)
        
        # Get analysis
        analysis = analysis_service.get_analysis(analysis_id, org_id)
        
        # Verify analysis belongs to project
        if str(analysis.project_id) != project_id:
            return error_response("Analysis not found in this project", 404)
        
        # Get export file path
        file_path = export_service.download_export(export_id, org_id)
        
        # Send file
        return send_file(
            file_path,
            as_attachment=True,
            download_name=os.path.basename(file_path)
        )
        
    except ValidationError as e:
        return error_response(str(e), 400)
    except NotFoundError as e:
        return error_response(str(e), 404)
    except Exception as e:
        error_logger.error(f"Download analysis export error: {str(e)}", exc_info=True)
        return error_response("Internal server error", 500)


@analysis_bp.route("/projects/<project_id>/analyses/<analysis_id>/stats", methods=["GET"])
@swag_from({
    "tags": ["Analysis"],
    "summary": "Get analysis statistics",
    "parameters": [
        {
            "name": "project_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the project"
        },
        {
            "name": "analysis_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "ID of the analysis"
        }
    ],
    "responses": {
        "200": {"description": "Analysis statistics"},
        "404": {"description": "Analysis not found"}
    }
})
@jwt_required()
@require_permission("project", "view")
def get_analysis_stats(project_id, analysis_id):
    """Get analysis statistics."""
    try:
        user_id = get_jwt_identity()
        org_id = get_jwt().get("org_id")
        
        # Verify project exists
        project = Project.objects(
            id=project_id, 
            organization_id=org_id, 
            is_deleted=False
        ).first()
        
        if not project:
            return error_response("Project not found", 404)
        
        # Get analysis
        analysis = analysis_service.get_analysis(analysis_id, org_id)
        
        # Verify analysis belongs to project
        if str(analysis.project_id) != project_id:
            return error_response("Analysis not found in this project", 404)
        
        # Get analysis stats
        stats = analysis_service.get_analysis_stats(analysis_id, org_id)
        
        return success_response(data=stats)
        
    except NotFoundError as e:
        return error_response(str(e), 404)
    except Exception as e:
        error_logger.error(f"Get analysis stats error: {str(e)}", exc_info=True)
        return error_response("Internal server error", 500)