"""
models/TenantSettings.py
Model for tracking tenant settings, resource quotas, and resource usage.
"""

from mongoengine import StringField, IntField, BooleanField
from mongoengine.errors import NotUniqueError
from .base import BaseDocument, SoftDeleteMixin

class TenantSettings(BaseDocument, SoftDeleteMixin):
    """
    Stores tenant settings, configuration, and quotas for form limits, submission limits, etc.
    Usage metrics are updated periodically or in real-time.
    """

    meta = {
        "collection": "tenant_settings",
        "indexes": [
            {"fields": ["organization_id"], "unique": True},
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, unique=True)
    is_active = BooleanField(default=True)

    # ── Tenant Quotas ──
    max_forms = IntField(default=100)
    max_submissions = IntField(default=10000)
    storage_limit_mb = IntField(default=1024)

    # ── Compliance Settings ──
    retention_days = IntField(default=365)  # Auto-expire responses older than this

    # ── Current Resource Usage ──
    usage_forms_count = IntField(default=0)
    usage_submissions_count = IntField(default=0)
    usage_storage_bytes = IntField(default=0)

    @classmethod
    def get_or_create(cls, organization_id: str) -> "TenantSettings":
        """Gets settings for the specified organization_id, or creates a default one if it doesn't exist."""
        doc = cls.objects(organization_id=organization_id).first()
        if doc:
            return doc

        try:
            cls._get_collection().update_one(
                {"organization_id": organization_id},
                {"$setOnInsert": {
                    "organization_id": organization_id,
                    "is_active": True,
                    "max_forms": 100,
                    "max_submissions": 10000,
                    "storage_limit_mb": 1024,
                    "retention_days": 365,
                    "usage_forms_count": 0,
                    "usage_submissions_count": 0,
                    "usage_storage_bytes": 0,
                }},
                upsert=True,
            )
        except NotUniqueError:
            pass

        return cls.objects(organization_id=organization_id).first()
