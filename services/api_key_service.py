from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from logger.unified_logger import app_logger
from models.auth import ApiKey
from services.redis_service import redis_service


API_KEY_RATE_LIMIT = 120
API_KEY_RATE_LIMIT_WINDOW_SECONDS = 60


@dataclass(frozen=True)
class ApiKeyResult:
    raw_key: str
    prefix: str
    record: ApiKey


class ApiKeyService:
    """Create, validate, and rate-limit service API keys."""

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @staticmethod
    def _make_raw_key() -> tuple[str, str]:
        secret = secrets.token_urlsafe(32)
        prefix = secret[:8]
        raw_key = f"fbp_{prefix}_{secret}"
        return raw_key, prefix

    @classmethod
    def create_api_key(
        cls,
        organization_id: str,
        name: str,
        created_by,
        scopes: Optional[Iterable[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> ApiKeyResult:
        raw_key, prefix = cls._make_raw_key()
        record = ApiKey(
            organization_id=organization_id,
            name=name.strip(),
            key_prefix=prefix,
            key_hash=cls._hash_key(raw_key),
            scopes=list(scopes or []),
            created_by=created_by,
            expires_at=expires_at,
            is_active=True,
        )
        record.save()
        app_logger.info(
            "Created API key %s for org %s with prefix %s",
            name,
            organization_id,
            prefix,
        )
        return ApiKeyResult(raw_key=raw_key, prefix=prefix, record=record)

    @classmethod
    def get_active_key(cls, raw_key: str, organization_id: Optional[str] = None):
        key_hash = cls._hash_key(raw_key)
        query = ApiKey.objects(key_hash=key_hash, is_active=True, revoked_at=None)
        if organization_id:
            query = query.filter(organization_id=organization_id)
        record = query.first()
        if record and record.expires_at:
            expires_at = record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(timezone.utc):
                return None
        return record

    @classmethod
    def revoke_api_key(cls, api_key: ApiKey, revoked_by=None) -> ApiKey:
        api_key.is_active = False
        api_key.revoked_at = datetime.now(timezone.utc)
        if revoked_by is not None:
            api_key.revoked_by = revoked_by
        api_key.save()
        return api_key

    @classmethod
    def list_api_keys(cls, organization_id: str):
        return ApiKey.objects(organization_id=organization_id).order_by("-created_at")

    @classmethod
    def rate_limit_key(cls, raw_key: str) -> bool:
        """Return True when usage is allowed, False when rate-limited."""
        try:
            redis_client = redis_service.cache
            if redis_client is None:
                return True
            bucket = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
            redis_key = (
                f"api_key_rate:{bucket}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"
            )
            current = redis_client.get(redis_key)
            usage = int(current) if current else 0
            if usage >= API_KEY_RATE_LIMIT:
                return False
            pipe = redis_client.pipeline()
            pipe.set(redis_key, usage + 1, ex=API_KEY_RATE_LIMIT_WINDOW_SECONDS * 2)
            pipe.execute()
            return True
        except Exception:
            return True
