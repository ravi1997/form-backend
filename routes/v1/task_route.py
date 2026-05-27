from flasgger import swag_from
from flask import Blueprint
from flask_jwt_extended import jwt_required

from services.task_service import task_service
from logger.unified_logger import app_logger, error_logger
from utils.response_helper import success_response, error_response

task_bp = Blueprint("task", __name__)


@task_bp.route("/<task_id>", methods=["GET"])
@swag_from(
    {
        "tags": ["Tasks"],
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
            "500": {"description": "Failed to fetch task status"},
        },
    }
)
@jwt_required()
def get_task_status(task_id):
    app_logger.info(f"Entering public get_task_status for task_id: {task_id}")
    try:
        status = task_service.get_status(task_id)
        return success_response(data=status)
    except Exception as exc:
        error_logger.error(f"Failed to fetch task {task_id}: {exc}", exc_info=True)
        return error_response(message="Failed to fetch task status", status_code=500)
