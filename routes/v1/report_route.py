from flask import Blueprint, request
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
import uuid
from datetime import datetime, timezone

from models.Form import Project, ReportConfig
from models.ReportJobLog import ReportJobLog
from schemas.report_config import ReportConfigCreateSchema, ReportConfigUpdateSchema
from utils.response_helper import success_response, error_response
from utils.security_helpers import require_permission
from utils.exceptions import NotFoundError, ValidationError
from logger.unified_logger import app_logger, error_logger, audit_logger

report_bp = Blueprint("report", __name__)

@report_bp.route("/", methods=["POST"])
@jwt_required()
@require_permission("project", "edit")
def create_report_config(project_id):
    """Create a new embedded Report Configuration inside the Project."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(f"User {user_id} creating report configuration in project {project_id}")

    try:
        project = Project.objects(id=project_id, organization_id=org_id, is_deleted=False).first()
        if not project:
            raise NotFoundError(f"Project {project_id} not found")

        data = request.get_json() or {}
        schema = ReportConfigCreateSchema(**data)

        # Build embedded model
        config = ReportConfig(
            id=uuid.uuid4(),
            name=schema.name,
            trigger_type=schema.trigger_type,
            cron_expression=schema.cron_expression,
            threshold_limit=schema.threshold_limit,
            blocks=[b.model_dump() for b in schema.blocks],
            recipients=schema.recipients,
            channels=schema.channels,
        )

        project.report_configs.append(config)
        project.save()

        audit_logger.info(
            f"Report Config created: ID={config.id}, Name='{config.name}', ProjectID={project_id}, OrgID={org_id}"
        )
        return success_response(
            data={"id": str(config.id), "name": config.name},
            message="Report configuration created successfully",
            status_code=201,
        )
    except Exception as e:
        error_logger.error(f"Create report config error: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@report_bp.route("/", methods=["GET"])
@jwt_required()
@require_permission("project", "view")
def list_report_configs(project_id):
    """List all active Report Configurations in a Project."""
    org_id = get_jwt().get("org_id")
    try:
        project = Project.objects(id=project_id, organization_id=org_id, is_deleted=False).first()
        if not project:
            raise NotFoundError(f"Project {project_id} not found")

        configs = [
            {
                "id": str(c.id),
                "name": c.name,
                "trigger_type": c.trigger_type,
                "cron_expression": c.cron_expression,
                "threshold_limit": c.threshold_limit,
                "current_threshold_counter": c.current_threshold_counter,
                "blocks": c.blocks,
                "recipients": c.recipients,
                "channels": c.channels,
            }
            for c in project.report_configs
        ]
        return success_response(data=configs)
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@report_bp.route("/<config_id>", methods=["DELETE"])
@jwt_required()
@require_permission("project", "edit")
def delete_report_config(project_id, config_id):
    """Delete a Report Configuration from Project."""
    org_id = get_jwt().get("org_id")
    try:
        project = Project.objects(id=project_id, organization_id=org_id, is_deleted=False).first()
        if not project:
            raise NotFoundError(f"Project {project_id} not found")

        original_len = len(project.report_configs)
        project.report_configs = [c for c in project.report_configs if str(c.id) != config_id]

        if len(project.report_configs) == original_len:
            raise NotFoundError(f"Report Config {config_id} not found")

        project.save()
        return success_response(message="Report configuration deleted")
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@report_bp.route("/<config_id>/logs", methods=["GET"])
@jwt_required()
@require_permission("project", "view")
def list_report_job_logs(project_id, config_id):
    """List all compiled job run logs for a specific Report Configuration."""
    org_id = get_jwt().get("org_id")
    try:
        # Check permissions & project membership
        project = Project.objects(id=project_id, organization_id=org_id, is_deleted=False).first()
        if not project:
            raise NotFoundError(f"Project {project_id} not found")

        logs = ReportJobLog.objects(project_id=project_id, config_id=config_id).order_by("-executed_at")
        data = [
            {
                "id": str(l.id),
                "status": l.status,
                "trigger_reason": l.trigger_reason,
                "executed_at": l.executed_at.isoformat(),
                "duration_ms": l.duration_ms,
                "file_url": l.file_url,
                "error_message": l.error_message,
            }
            for l in logs
        ]
        return success_response(data=data)
    except Exception as e:
        return error_response(message=str(e), status_code=400)
