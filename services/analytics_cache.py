from typing import Optional, Dict, Any
from config.redis import RedisConfig
from config.settings import settings
import redis
import json
from logger.unified_logger import app_logger


# Shared connection pool for all AnalyticsCache instances (thread-safe).
# Uses the canonical analytics cache DB from settings (DB 2).
_analytics_pool = redis.ConnectionPool(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB_ANALYTICS_CACHE,
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
    max_connections=20,
)


class AnalyticsCache:
    """
    Redis caching layer for analytics results.
    Prevents repeated heavy aggregations on static data.

    Uses Redis DB defined by settings.REDIS_DB_ANALYTICS_CACHE (default: 2)
    to avoid key-space collisions with other Redis consumers:
      - DB 0: application cache / idempotency
      - DB 1: Celery results
      - DB 2: analytics cache  ← this class
      - DB 3: rate limiter
      - DB 4: Celery broker
    """

    def __init__(self):
        # Reuse the shared pool — no new TCP connections per instantiation.
        self.redis_client = redis.Redis(connection_pool=_analytics_pool)

    def _generate_cache_key(
        self, form_id: str, metric_type: str, params: Dict[str, Any] = None, organization_id: str = None
    ) -> str:
        """Generate a consistent cache key scoped by tenant organization."""
        org_id = organization_id
        if not org_id:
            from flask import has_request_context
            from flask_jwt_extended import current_user
            if has_request_context() and current_user:
                org_id = getattr(current_user, "organization_id", None)
            if not org_id:
                from models.Form import Form
                try:
                    form = Form.objects(id=form_id).first()
                    if form:
                        org_id = form.organization_id
                except Exception:
                    pass

        param_str = json.dumps(params or {}, sort_keys=True)
        prefix = f"org:{org_id}:" if org_id else ""
        return f"{prefix}analytics:{form_id}:{metric_type}:{param_str}"

    def get(
        self, form_id: str, metric_type: str, params: Dict[str, Any] = None, organization_id: str = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cached analytics data."""
        cache_key = self._generate_cache_key(form_id, metric_type, params, organization_id)
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
        organization_id: str = None,
    ) -> None:
        """Store analytics data in cache with TTL."""
        cache_key = self._generate_cache_key(form_id, metric_type, params, organization_id)
        try:
            self.redis_client.setex(cache_key, ttl, json.dumps(data))
            app_logger.debug(f"Cache set for {cache_key} with TTL {ttl}s")
        except Exception as e:
            app_logger.warning(f"Cache set failed for {cache_key}: {e}")

    def invalidate_form(self, form_id: str) -> None:
        """Invalidate all cache entries for a specific form."""
        try:
            pattern = f"*analytics:{form_id}:*"
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
                app_logger.info(
                    f"Invalidated {len(keys)} cache entries for form {form_id}"
                )
        except Exception as e:
            app_logger.warning(f"Cache invalidation failed for form {form_id}: {e}")


analytics_cache = AnalyticsCache()
