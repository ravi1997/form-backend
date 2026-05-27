from typing import Any, Dict, Optional
from config.celery import celery_app
from logger.unified_logger import app_logger, error_logger
from services.task_observability_service import task_observability_service


class TaskService:
    """
    Service for managing and querying asynchronous tasks in the form backend.
    """

    def get_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get the status, progress, and result of a Celery task.
        First attempts to read tracked status from Redis (via TaskObservabilityService),
        and falls back to Celery AsyncResult.
        """
        app_logger.info(f"Querying status for task_id: {task_id}")
        try:
            # 1. Try to fetch from Redis tracking first
            tracked_status = task_observability_service.get_task_status(task_id)
            if tracked_status and tracked_status.get("state"):
                app_logger.debug(
                    f"Found tracked status in Redis for task_id {task_id}: {tracked_status}"
                )
                return {
                    "task_id": task_id,
                    "state": tracked_status.get("state"),
                    "result": tracked_status.get("result"),
                    "error": tracked_status.get("error"),
                    "traceback": tracked_status.get("traceback"),
                    "current_progress": tracked_status.get("current"),
                    "total_progress": tracked_status.get("total"),
                }

            # 2. Fall back to direct Celery query
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
                    payload["result"] = (
                        task.result
                        if isinstance(task.result, dict)
                        else {"data": task.result}
                    )
                elif task.failed():
                    payload["error"] = str(task.info)
                    payload["traceback"] = task.traceback
            elif task.info and isinstance(task.info, dict):
                payload["current_progress"] = task.info.get("current")
                payload["total_progress"] = task.info.get("total")

            return payload

        except Exception as exc:
            error_logger.error(f"Failed to fetch task {task_id}: {exc}", exc_info=True)
            raise exc


task_service = TaskService()
