from typing import Dict, Any, Optional
from services.task_observability_service import task_observability_service
from logger.unified_logger import app_logger
from config.celery import celery_app


class TaskStatusTracker:
    """
    Decorator class to automatically track Celery task status in Redis.
    Wraps Celery task functions to update their state, progress, and results.
    """

    def __init__(self, task_type: str):
        """
        Initialize tracker for a specific task type.

        Args:
            task_type: Human-readable task type (e.g., "publish_form", "clone_form")
        """
        self.task_type = task_type

    def __call__(self, func):
        """
        Wrap the Celery task function to add automatic status tracking.
        """

        def wrapper(*args, **kwargs):
            from config.celery import celery_app

            # Get task ID if available
            task_id = None
            if hasattr(celery_app, "current_task"):
                task_id = celery_app.current_task.request.id

            if task_id:
                # Update initial status
                task_observability_service.update_task_status(
                    task_id=task_id, state="PENDING"
                )

            try:
                # Update to PROCESSING state
                if task_id:
                    task_observability_service.update_task_status(
                        task_id=task_id, state="PROCESSING"
                    )

                # Execute the actual task
                result = func(*args, **kwargs)

                # Update result or error
                if task_id:
                    if isinstance(result, dict) and "status" in result:
                        # Task returned a dict with status
                        if result["status"] == "success":
                            task_observability_service.update_task_result(
                                task_id=task_id, result=result
                            )
                        elif result["status"] == "error":
                            task_observability_service.update_task_result(
                                task_id=task_id,
                                error=result.get("message", "Unknown error"),
                            )
                        elif result["status"] == "failed":
                            task_observability_service.update_task_status(
                                task_id=task_id, state="FAILED"
                            )
                    elif isinstance(result, dict):
                        # Task returned a dict (assume success)
                        task_observability_service.update_task_result(
                            task_id=task_id, result=result
                        )
                    else:
                        # Task raised exception
                        raise result

            except Exception as e:
                # Handle task failure
                if task_id:
                    task_observability_service.update_task_status(
                        task_id=task_id, state="FAILED"
                    )
                    task_observability_service.update_task_result(
                        task_id=task_id, error=str(e)
                    )
                raise e

        return wrapper


def track_task(task_type: str):
    """
    Decorator factory for automatic task status tracking.

    Usage:
        @celery_app.task(bind=True)
        @track_task("publish_form")
        def my_task(self, ...):
            ...

    Args:
        task_type: Human-readable task type identifier

    Returns:
        Decorated function with automatic status tracking
    """
    return lambda func: TaskStatusTracker(task_type)(func)
