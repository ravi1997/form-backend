from typing import Dict, Any, Optional, List
from mongoengine import QuerySet
from models.Response import FormResponse
from models.Form import Form
from datetime import datetime, timedelta, timezone
from logger.unified_logger import app_logger
from config.redis import RedisConfig
import redis
import json


class AnalyticsCache:
    """
    High-performance caching layer for analytics results using Redis.
    Uses logical DB 0 (separate from Celery result DB 2).
    Supports automatic cache invalidation when new responses are submitted.
    """

    ANALYTICS_PREFIX = "analytics:"
    CACHE_TTL_SECONDS = 300  # 5 minutes

    def __init__(self):
        redis_config = RedisConfig()
        self.redis_client = redis.Redis(
            host=redis_config.host,
            port=redis_config.port,
            db=0,  # Use DB 0 for analytics cache
            password=redis_config.password,
            decode_responses=True,
            socket_timeout=redis_config.socket_timeout,
        )

    def _generate_key(
        self, form_id: str, metric_type: str, params: Dict[str, Any] = None
    ) -> str:
        """Generate a consistent cache key."""
        import hashlib
        from urllib.parse import urlencode

        param_str = urlencode(sorted(params.items())) if params else ""
        key_parts = [form_id, metric_type, param_str]
        key_hash = hashlib.md5("|".join(key_parts).encode()).hexdigest()
        return f"{self.ANALYTICS_PREFIX}{key_hash}"

    def get(
        self, form_id: str, metric_type: str, params: Dict[str, Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cached analytics data."""
        cache_key = self._generate_key(form_id, metric_type, params)
        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                app_logger.debug(f"Analytics cache hit for {cache_key}")
                return json.loads(cached_data)
        except Exception as e:
            app_logger.warning(f"Analytics cache get failed for {cache_key}: {e}")
        return None

    def set(
        self,
        form_id: str,
        metric_type: str,
        data: Dict[str, Any],
        params: Dict[str, Any] = None,
        ttl: Optional[int] = None,
    ) -> None:
        """Store analytics data in cache with TTL."""
        cache_key = self._generate_key(form_id, metric_type, params)
        try:
            self.redis_client.setex(
                cache_key, ttl or self.CACHE_TTL_SECONDS, json.dumps(data)
            )
            app_logger.debug(
                f"Analytics cache set for {cache_key} with TTL {ttl or self.CACHE_TTL_SECONDS}s"
            )
        except Exception as e:
            app_logger.warning(f"Analytics cache set failed for {cache_key}: {e}")

    def invalidate_form(self, form_id: str) -> None:
        """
        Invalidate all cache entries for a specific form.
        Called when a new FormResponse is submitted for that form.
        """
        try:
            pattern = f"{self.ANALYTICS_PREFIX}*"
            keys = self.redis_client.keys(pattern)

            # Find and delete keys that contain the form_id in their hash
            keys_to_delete = []
            for key in keys:
                if self._key_contains_form_id(key, form_id):
                    keys_to_delete.append(key)

            if keys_to_delete:
                self.redis_client.delete(*keys_to_delete)
                app_logger.info(
                    f"Invalidated {len(keys_to_delete)} cache entries for form {form_id}"
                )
        except Exception as e:
            app_logger.warning(
                f"Analytics cache invalidation failed for form {form_id}: {e}"
            )

    def _key_contains_form_id(self, key: str, form_id: str) -> bool:
        """Helper to check if cache key relates to the given form_id."""
        try:
            key_data = json.loads(self.redis_client.get(key) or "{}")
            if isinstance(key_data, dict) and "form_id" in key_data:
                return key_data["form_id"] == form_id
            return False
        except Exception:
            return False


analytics_cache = AnalyticsCache()
