from typing import Optional, Dict, Any, List
from config.redis import RedisConfig
import redis
import json
from logger.unified_logger import app_logger


class AnalyticsCache:
    """
    Redis caching layer for analytics results.
    Prevents repeated heavy aggregations on static data.
    """

    def __init__(self):
        redis_config = RedisConfig()
        self.redis_client = redis.Redis(
            host=redis_config.host,
            port=redis_config.port,
            db=2,
            password=redis_config.password,
            decode_responses=True,
            socket_timeout=redis_config.socket_timeout,
        )

    def _generate_cache_key(
        self, form_id: str, metric_type: str, params: Dict[str, Any] = None
    ) -> str:
        """Generate a consistent cache key."""
        param_str = json.dumps(params or {}, sort_keys=True)
        return f"analytics:{form_id}:{metric_type}:{param_str}"

    def get(
        self, form_id: str, metric_type: str, params: Dict[str, Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cached analytics data."""
        cache_key = self._generate_cache_key(form_id, metric_type, params)
        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                app_logger.debug(f"Cache hit for {cache_key}")
                return json.loads(cached_data)
        except Exception as e:
            app_logger.warning(f"Cache get failed for {cache_key}: {e}")
        return None

    def set(
        self,
        form_id: str,
        metric_type: str,
        data: Dict[str, Any],
        params: Dict[str, Any] = None,
        ttl: int = 300,
    ) -> None:
        """Store analytics data in cache with TTL."""
        cache_key = self._generate_cache_key(form_id, metric_type, params)
        try:
            self.redis_client.setex(cache_key, ttl, json.dumps(data))
            app_logger.debug(f"Cache set for {cache_key} with TTL {ttl}s")
        except Exception as e:
            app_logger.warning(f"Cache set failed for {cache_key}: {e}")

    def invalidate_form(self, form_id: str) -> None:
        """Invalidate all cache entries for a specific form."""
        try:
            pattern = f"analytics:{form_id}:*"
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
                app_logger.info(
                    f"Invalidated {len(keys)} cache entries for form {form_id}"
                )
        except Exception as e:
            app_logger.warning(f"Cache invalidation failed for form {form_id}: {e}")


analytics_cache = AnalyticsCache()
