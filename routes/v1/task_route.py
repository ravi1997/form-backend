from flasgger import swag_from
from flask import Blueprint
from flask_jwt_extended import jwt_required

from config.celery import celery_app
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
        task = celery_app.AsyncResult(task_id)
        payload = {
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
                payload["result"] = task.result
            elif task.failed():
                payload["error"] = str(task.info)
                payload["traceback"] = task.traceback
        elif task.info and isinstance(task.info, dict):
            payload["current_progress"] = task.info.get("current")
            payload["total_progress"] = task.info.get("total")

        return success_response(data=payload)
    except Exception as exc:
        error_logger.error(f"Failed to fetch task {task_id}: {exc}", exc_info=True)
        return error_response(message="Failed to fetch task status", status_code=500)
