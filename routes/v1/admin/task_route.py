from flask import Blueprint
from flask_jwt_extended import jwt_required
from flasgger import swag_from
from utils.security import require_roles
from utils.response_helper import success_response, error_response
from services.task_service import task_service
from logger.unified_logger import app_logger, error_logger

admin_task_bp = Blueprint("admin_task", __name__)


@admin_task_bp.route("/<task_id>", methods=["GET"])
@swag_from(
    {
        "tags": ["Admin Tasks"],
        "parameters": [
            {
                "name": "task_id",
                "in": "path",
                "type": "string",
                "required": True,
            }
        ],
        "responses": {
            "200": {"description": "Task status retrieved"},
            "401": {"description": "Unauthorized"},
            "403": {"description": "Forbidden"},
            "500": {"description": "Failed to fetch task status"},
        },
    }
)
@require_roles("admin", "superadmin")
def get_admin_task_status(task_id):
    """
    Get the status, progress, and results of any Celery task (admin only).
    """
    app_logger.info(f"Entering admin get_task_status for task_id: {task_id}")
    try:
        status = task_service.get_status(task_id)
        return success_response(data=status)
    except Exception as exc:
        error_logger.error(
            f"Failed to fetch task status in admin route for {task_id}: {exc}",
            exc_info=True,
        )
        return error_response(message="Failed to fetch task status", status_code=500)
