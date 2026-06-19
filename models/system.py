"""
models/system.py
System configuration and settings models.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument


class SystemSettings(BaseDocument):
    """Global system configuration."""

    meta = {
        "collection": "system_settings",
        "indexes": [
            {"fields": ["key"], "unique": True},
        ],
        "index_background": True,
    }

    key = StringField(required=True, unique=True)
    value = DictField()
    description = StringField()
    is_sensitive = BooleanField(default=False)
    updated_by = ReferenceField("User", reverse_delete_rule=3)
    updated_at = DateTimeField()


class FeatureFlag(BaseDocument, SoftDeleteMixin):
    """Feature flag for enabling/disabling features."""

    meta = {
        "collection": "feature_flags",
        "indexes": [
            {"fields": ["organization_id", "key"], "unique": True},
            {"fields": ["key"]},
            {"fields": ["organization_id"]},
            {"fields": ["is_enabled"]},
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    key = StringField(required=True, unique=True)
    description = StringField()
    is_enabled = BooleanField(default=False)
    is_global = BooleanField(default=False)
    per_org_overrides = DictField()  # org_id -> enabled boolean
    scope = StringField(choices=["global", "org"], default="org")
    created_by = ReferenceField("User", reverse_delete_rule=3)
    meta_data = DictField()


class AuditLog(BaseDocument):
    """Audit trail for all system actions."""

    meta = {
        "collection": "audit_logs",
        "indexes": [
            {"fields": ["organization_id", "entity_type", "entity_id"]},
            {"fields": ["organization_id", "actor_id"]},
            {"fields": ["organization_id", "action"]},
            {"fields": ["organization_id", "timestamp"]},
            "organization_id",
            "entity_type",
            "timestamp",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    entity_type = StringField(required=True)
    entity_id = StringField(required=True)
    action = StringField(required=True)
    actor_id = ReferenceField("User", reverse_delete_rule=3)
    actor_role = StringField()
    ip_address = StringField()
    user_agent = StringField()
    before_data = DictField()
    after_data = DictField()
    metadata = DictField()
    timestamp = DateTimeField()
    archived = BooleanField(default=False)


class LegalHold(BaseDocument, SoftDeleteMixin):
    """Legal hold configuration for data retention."""

    meta = {
        "collection": "legal_holds",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            {"fields": ["organization_id", "status"]},
            "organization_id",
            "status",
            "expires_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    description = StringField()
    status = StringField(choices=["active", "expired", "released"], default="active")
    entity_types = ListField(StringField())  # FormResponse, AuditLog, etc.
    entity_ids = ListField(StringField())  # Specific entity IDs under hold
    reason = StringField()
    requested_by = ReferenceField("User", reverse_delete_rule=3)
    approved_by = ReferenceField("User", reverse_delete_rule=3)
    expires_at = DateTimeField()
    released_at = DateTimeField()
    created_at = DateTimeField()
    meta_data = DictField()


class ComplianceRecord(BaseDocument, SoftDeleteMixin):
    """Compliance tracking and certification."""

    meta = {
        "collection": "compliance_records",
        "indexes": [
            {"fields": ["organization_id", "standard"]},
            {"fields": ["organization_id", "status"]},
            {"fields": ["organization_id", "expires_at"]},
            "organization_id",
            "standard",
            "status",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    standard = StringField(required=True)  # GDPR, HIPAA, ISO27001, etc.
    version = StringField()
    status = StringField(choices=["pending", "compliant", "non_compliant", "expired"], default="pending")
    certification_date = DateTimeField()
    expires_at = DateTimeField()
    auditor = StringField()
    report_url = StringField()
    findings = ListField(DictField())
    remediation_plan = DictField()
    created_by = ReferenceField("User", reverse_delete_rule=3)
    meta_data = DictField()