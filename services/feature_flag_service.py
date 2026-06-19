"""
services/feature_flag_service.py
Service layer for Feature Flag management and consumption.
"""

from typing import List, Dict, Optional, Any
from logger.unified_logger import app_logger, audit_logger
from services.base import BaseService
from services.redis_service import redis_service
from models.system import FeatureFlag
from schemas.feature_flag import FeatureFlagCreateSchema, FeatureFlagSchema
from utils.exceptions import ValidationError, NotFoundError

class FeatureFlagService(BaseService):
    def __init__(self):
        super().__init__(model=FeatureFlag, schema=FeatureFlagSchema)
        self.cache_ttl = 60
        self.default_flags = [
            ("ai_classification", "AI-based taxonomy classification of forms", False),
            ("ai_summarization", "AI-powered summary generation for responses", False),
            ("oidc_login", "Enterprise SSO OIDC Identity Provider integration", False),
            ("analytics_stream", "Real-time SSE event analytics stream", False),
            ("nlp_search", "Semantic search for forms using natural language", False),
            ("anomaly_detection", "Auto-detect submission anomalies and spam", False),
            ("git_versioning", "Track form revisions in git repository history", False),
            ("webhooks", "Outbound webhooks for form submission events", False),
            ("export_csv", "Export form responses as CSV file reports", True),  # export_csv is enabled by default
        ]

    def get_all_flags(self) -> List[FeatureFlagSchema]:
        """Returns all feature flags."""
        flags = FeatureFlag.objects()
        return [self._to_schema(flag) for flag in flags]

    def seed_default_flags(self) -> None:
        """Seeds the 9 enterprise feature flags into the database if they don't already exist."""
        for flag_key, description, default_val in self.default_flags:
            flag = FeatureFlag.objects(key=flag_key).first()
            if not flag:
                app_logger.info(f"Seeding feature flag: {flag_key}")
                flag = FeatureFlag(
                    organization_id="system",  # System-level flags
                    key=flag_key,
                    description=description,
                    is_enabled=default_val,
                    per_org_overrides={},
                    scope="org" if flag_key != "export_csv" else "global"
                )
                flag.save()

    def update_global_flag(self, flag_key: str, is_enabled: bool) -> FeatureFlagSchema:
        """Updates the global default status of a feature flag."""
        flag = FeatureFlag.objects(flag_key=flag_key).first()
        if not flag:
            raise NotFoundError(f"Feature flag {flag_key} not found.")

        old_val = flag.is_enabled
        flag.is_enabled = is_enabled
        flag.save()

        # Invalidate the cache for this flag key across organizations
        self._invalidate_cache(flag_key)

        audit_logger.info(
            f"AUDIT: Feature flag {flag_key} global setting updated from {old_val} to {is_enabled}."
        )
        return self._to_schema(flag)

    def set_org_override(self, flag_key: str, organization_id: str, is_enabled: bool) -> FeatureFlagSchema:
        """Sets an organization-specific override for a feature flag."""
        flag = FeatureFlag.objects(flag_key=flag_key).first()
        if not flag:
            raise NotFoundError(f"Feature flag {flag_key} not found.")

        old_overrides = dict(flag.per_org_overrides)
        flag.per_org_overrides[organization_id] = is_enabled
        flag.save()

        # Invalidate the cache for this specific flag and org
        self._invalidate_cache(flag_key, organization_id)

        audit_logger.info(
            f"AUDIT: Feature flag {flag_key} override for org {organization_id} set to {is_enabled}."
        )
        return self._to_schema(flag)

    def is_feature_enabled(self, flag_key: str, organization_id: Optional[str]) -> bool:
        """
        Determines if a feature flag is enabled for a given organization.
        Checks Redis Cache first (60s TTL), falling back to MongoDB on a cache miss.
        """
        if not organization_id:
            # If no org ID, default to checking global configuration directly
            return self._check_global_flag_directly(flag_key)

        cache_key = f"feature_flag:{flag_key}:{organization_id}"
        
        # 1. Try Redis cache
        try:
            cached_val = redis_service.cache.get(cache_key)
            if cached_val is not None:
                try:
                    redis_service.cache.client.incr("metrics:feature_flag:hits")
                except Exception:
                    pass
                app_logger.info(f"Feature flag cache HIT for {flag_key}:{organization_id}")
                # If cached_val is a string representing a bool, convert it
                if isinstance(cached_val, str):
                    if cached_val.lower() == "true":
                        return True
                    elif cached_val.lower() == "false":
                        return False
                return bool(cached_val)
        except Exception as e:
            app_logger.warning(f"Failed to read feature flag cache: {e}")

        # 2. Query MongoDB
        try:
            redis_service.cache.client.incr("metrics:feature_flag:misses")
        except Exception:
            pass
        app_logger.info(f"Feature flag cache MISS for {flag_key}:{organization_id}")

        flag = FeatureFlag.objects(flag_key=flag_key).first()
        if not flag:
            # If flag not registered, default to False
            return False

        # Determine enabled state
        enabled = flag.is_enabled
        if organization_id in flag.per_org_overrides:
            enabled = flag.per_org_overrides[organization_id]

        # 3. Write back to Redis cache
        try:
            redis_service.cache.set(cache_key, enabled, ttl=self.cache_ttl)
        except Exception as e:
            app_logger.warning(f"Failed to write feature flag cache: {e}")

        return enabled

    def get_cache_metrics(self) -> Dict[str, Any]:
        """Returns the hit/miss metrics for the feature flag cache."""
        try:
            client = redis_service.cache.client
            hits_val = client.get("metrics:feature_flag:hits")
            misses_val = client.get("metrics:feature_flag:misses")
            hits = int(hits_val) if hits_val is not None else 0
            misses = int(misses_val) if misses_val is not None else 0
            total = hits + misses
            hit_rate = (hits / total * 100) if total > 0 else 0.0
            return {
                "hits": hits,
                "misses": misses,
                "total": total,
                "hit_rate_percent": round(hit_rate, 2)
            }
        except Exception as e:
            app_logger.warning(f"Failed to fetch cache metrics: {e}")
            return {"hits": 0, "misses": 0, "total": 0, "hit_rate_percent": 0.0}

    def _check_global_flag_directly(self, flag_key: str) -> bool:
        flag = FeatureFlag.objects(flag_key=flag_key).first()
        return flag.is_enabled if flag else False

    def _invalidate_cache(self, flag_key: str, organization_id: Optional[str] = None) -> None:
        """Cleans up Redis cache entries to keep them consistent with MongoDB."""
        try:
            if organization_id:
                cache_key = f"feature_flag:{flag_key}:{organization_id}"
                redis_service.cache.delete(cache_key)
            else:
                # If updating globally, ideally we invalidate all orgs. 
                # Since we don't have list of all orgs in Redis, we could just delete for all existing orgs
                # in our DB or scan keys. For simplicity, we can delete the general key and scan pattern.
                # In Python redis, we can do a pattern delete or just let them expire in 60s, 
                # but let's try to delete keys matching `feature_flag:{flag_key}:*`.
                client = redis_service.cache.client
                pattern = f"feature_flag:{flag_key}:*"
                keys = client.keys(pattern)
                if keys:
                    client.delete(*keys)
        except Exception as e:
            app_logger.warning(f"Failed to invalidate feature flag cache: {e}")
