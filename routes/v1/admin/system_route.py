from flask import Blueprint, jsonify
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.security import require_roles
from services.event_bus import event_bus
from services.analytics_stream_service import analytics_stream_service
from utils.response_helper import success_response, error_response
from logger.unified_logger import app_logger, error_logger, audit_logger
from config.celery import celery_app
from tasks.form_tasks import cleanup_deleted_records

system_bp = Blueprint("system_bp", __name__)


@system_bp.route("/event-health", methods=["GET"])
@swag_from({"tags": ["System"], "responses": {"200": {"description": "Success"}}})
@jwt_required()
@require_roles("superadmin")
def get_event_health():
    """
    Returns metrics about the health of the internal event system.
    Includes consumer lag, DLQ sizes, and stream lengths.
    """
    admin_id = get_jwt_identity()
    app_logger.info(f"Entering get_event_health by admin: {admin_id}")
    try:
        metrics = event_bus.get_metrics()
        app_logger.info("Exiting get_event_health successfully")
        return success_response(data=metrics)
    except Exception as e:
        error_logger.error(f"Failed to fetch event health metrics: {e}", exc_info=True)
        return error_response(
            message="Failed to fetch event health metrics", status_code=500
        )


@system_bp.route("/analytics-trends/<org_id>", methods=["GET"])
@swag_from(
    {
        "tags": ["System"],
        "responses": {"200": {"description": "Success"}},
        "parameters": [
            {"name": "org_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
@require_roles("admin", "superadmin")
def get_analytics_trends(org_id):
    """
    Returns submission trends from the OLAP engine.
    """
    admin_id = get_jwt_identity()
    app_logger.info(
        f"Entering get_analytics_trends for org_id: {org_id} by admin: {admin_id}"
    )
    try:
        trends = analytics_stream_service.get_submission_trends(org_id)
        app_logger.info(
            f"Exiting get_analytics_trends successfully for org_id: {org_id}"
        )
        return success_response(data=trends)
    except Exception as e:
        error_logger.error(
            f"Failed to fetch analytics trends for org {org_id}: {e}", exc_info=True
        )
        return error_response(
            message="Failed to fetch analytics trends", status_code=500
        )


@system_bp.route("/tasks/<task_id>", methods=["GET"])
@swag_from(
    {
        "tags": ["System"],
        "responses": {
            "200": {"description": "Task status retrieved successfully"},
            "404": {"description": "Task not found"},
        },
        "parameters": [
            {
                "name": "task_id",
                "in": "path",
                "type": "string",
                "required": True,
                "description": "Celery task ID",
            }
        ],
    }
)
@jwt_required()
def get_task_status(task_id):
    """
    Get the status of an async Celery task.
    Supports polling for async_publish_form, async_clone_form, async_bulk_export, and async_process_translation_job.
    """
    app_logger.info(f"Entering get_task_status for task_id: {task_id}")
    try:
        task = celery_app.AsyncResult(task_id)

        task_data = {
            "task_id": task_id,
            "state": task.state,
            "result": None,
            "error": None,
            "traceback": None,
            "current_progress": None,
            "total_progress": None,
        }

        if task.ready():
            if task.successful():
                task_data["result"] = task.result
            elif task.failed():
                task_data["error"] = str(task.info)
                task_data["traceback"] = task.traceback
        else:
            if task.state == "STARTED":
                if task.info:
                    if isinstance(task.info, dict):
                        task_data["current_progress"] = task.info.get("current")
                        task_data["total_progress"] = task.info.get("total")

        app_logger.info(f"Task {task_id} status: {task.state}")
        return success_response(data=task_data)
    except Exception as e:
        error_logger.error(
            f"Failed to fetch task status for {task_id}: {e}", exc_info=True
        )
        return error_response(message="Failed to fetch task status", status_code=500)


@system_bp.route("/gdpr-cleanup", methods=["POST"])
@swag_from(
    {
        "tags": ["System"],
        "responses": {
            "200": {"description": "GDPR cleanup initiated"},
            "400": {"description": "Invalid request"},
            "403": {"description": "Unauthorized"},
        },
    }
)
@jwt_required()
@require_roles("admin", "superadmin")
def initiate_gdpr_cleanup():
    """
    Initiate GDPR compliance cleanup of soft-deleted records.
    This is an opt-in operation that permanently deletes records older than the retention period.
    """
    admin_id = get_jwt_identity()
    app_logger.info(f"Entering initiate_gdpr_cleanup by admin: {admin_id}")

    from flask import request

    try:
        data = request.get_json(silent=True) or {}
        retention_days = data.get("retention_days", 30)
        dry_run = data.get("dry_run", False)

        if retention_days < 1:
            return error_response(
                message="retention_days must be at least 1", status_code=400
            )

        if retention_days > 365:
            return error_response(
                message="retention_days cannot exceed 365", status_code=400
            )

        task = cleanup_deleted_records.delay(
            retention_days=retention_days, dry_run=dry_run
        )

        audit_logger.info(
            f"GDPR cleanup initiated by admin {admin_id}. "
            f"retention_days={retention_days}, dry_run={dry_run}, task_id={task.id}"
        )

        app_logger.info(f"GDPR cleanup task {task.id} initiated")

        return success_response(
            data={
                "task_id": task.id,
                "retention_days": retention_days,
                "dry_run": dry_run,
            },
            message="GDPR cleanup task initiated",
        )
    except Exception as e:
        error_logger.error(f"Failed to initiate GDPR cleanup: {e}", exc_info=True)
        return error_response(
            message="Failed to initiate GDPR cleanup", status_code=500
        )
