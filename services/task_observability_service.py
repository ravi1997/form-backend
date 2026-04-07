from typing import Optional, Dict, Any
from config.redis import RedisConfig
import redis
import json
from logger.unified_logger import app_logger


class TaskObservabilityService:
    """
    Service for observing and tracking Celery task execution using Redis.
    Provides task state storage, progress tracking, and result caching.
    """

    TASK_STATUS_PREFIX = "task:status:"
    TASK_RESULT_PREFIX = "task:result:"
    TASK_PROGRESS_PREFIX = "task:progress:"

    def __init__(self):
        redis_config = RedisConfig()
        self.redis_client = redis.Redis(
            host=redis_config.host,
            port=redis_config.port,
            db=0,
            password=redis_config.password,
            decode_responses=True,
            socket_timeout=redis_config.socket_timeout,
        )

    def _get_status_key(self, task_id: str) -> str:
        """Generate Redis key for task status."""
        return f"{self.TASK_STATUS_PREFIX}{task_id}"

    def _get_result_key(self, task_id: str) -> str:
        """Generate Redis key for task result."""
        return f"{self.TASK_RESULT_PREFIX}{task_id}"

    def _get_progress_key(self, task_id: str) -> str:
        """Generate Redis key for task progress."""
        return f"{self.TASK_PROGRESS_PREFIX}{task_id}"

    def update_task_status(
        self,
        task_id: str,
        state: str,
        ttl: int = 86400,  # 24 hours
    ) -> None:
        """
        Update task status in Redis.
        """
        try:
            status_data = {
                "task_id": task_id,
                "state": state,
                "updated_at": json.dumps({"timestamp": self._get_timestamp()}),
            }
            key = self._get_status_key(task_id)
            self.redis_client.setex(key, ttl, json.dumps(status_data))
            app_logger.info(f"Updated task status for {task_id}: {state}")
        except Exception as e:
            app_logger.error(f"Failed to update task status for {task_id}: {e}")

    def update_task_result(
        self,
        task_id: str,
        result: Optional[Dict[str, Any]],
        error: Optional[str] = None,
        ttl: int = 86400,  # 24 hours
    ) -> None:
        """
        Update task result in Redis.
        """
        try:
            result_data = {
                "task_id": task_id,
                "result": result,
                "error": error,
                "updated_at": json.dumps({"timestamp": self._get_timestamp()}),
            }
            key = self._get_result_key(task_id)
            self.redis_client.setex(key, ttl, json.dumps(result_data))
            app_logger.info(
                f"Updated task result for {task_id}: {'success' if result else 'failed'}"
            )
        except Exception as e:
            app_logger.error(f"Failed to update task result for {task_id}: {e}")

    def update_task_progress(
        self,
        task_id: str,
        current: Optional[int] = None,
        total: Optional[int] = None,
        ttl: int = 3600,  # 1 hour
    ) -> None:
        """
        Update task progress in Redis.
        """
        try:
            progress_data = {
                "task_id": task_id,
                "current": current,
                "total": total,
                "percentage": int((current / total * 100)) if total else 0,
                "updated_at": json.dumps({"timestamp": self._get_timestamp()}),
            }
            key = self._get_progress_key(task_id)
            self.redis_client.setex(key, ttl, json.dumps(progress_data))
            app_logger.debug(f"Updated task progress for {task_id}: {current}/{total}")
        except Exception as e:
            app_logger.error(f"Failed to update task progress for {task_id}: {e}")

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve full task status from Redis including state, result, and progress.
        """
        try:
            status_key = self._get_status_key(task_id)
            result_key = self._get_result_key(task_id)
            progress_key = self._get_progress_key(task_id)

            status_data = self.redis_client.get(status_key)
            result_data = self.redis_client.get(result_key)
            progress_data = self.redis_client.get(progress_key)

            combined_data = {
                "task_id": task_id,
            }

            if status_data:
                combined_data.update(json.loads(status_data))
            if result_data:
                combined_data.update(json.loads(result_data))
            if progress_data:
                combined_data.update(json.loads(progress_data))

            return combined_data
        except Exception as e:
            app_logger.error(f"Failed to get task status for {task_id}: {e}")
            return None

    def clear_task_data(self, task_id: str) -> None:
        """
        Clear all task-related data from Redis.
        """
        try:
            keys_to_clear = [
                self._get_status_key(task_id),
                self._get_result_key(task_id),
                self._get_progress_key(task_id),
            ]
            self.redis_client.delete(*keys_to_clear)
            app_logger.info(f"Cleared task data for {task_id}")
        except Exception as e:
            app_logger.error(f"Failed to clear task data for {task_id}: {e}")

    @staticmethod
    def _get_timestamp() -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()


task_observability_service = TaskObservabilityService()
