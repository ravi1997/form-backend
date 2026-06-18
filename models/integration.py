"""
models/integration.py
Integration and webhook models.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument


class WebhookConfig(BaseDocument, SoftDeleteMixin):
    """Webhook configuration for external integrations."""

    meta = {
        "collection": "webhook_configs",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            {"fields": ["organization_id", "url"]},
            "organization_id",
            "form_id",
            "is_active",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    description = StringField()
    url = StringField(required=True)
    secret = StringField()  # HMAC secret for payload verification
    events = ListField(StringField())  # form.submitted, response.created, etc.
    form_id = ReferenceField("Form", reverse_delete_rule=3)
    headers = DictField()  # Custom headers to send
    method = StringField(default="POST", choices=["GET", "POST", "PUT", "DELETE"])
    timeout_seconds = IntField(default=30)
    retry_count = IntField(default=3)
    is_active = BooleanField(default=True)
    created_by = ReferenceField("User", reverse_delete_rule=3)
    last_used_at = DateTimeField()
    meta_data = DictField()


class WebhookDelivery(BaseDocument, SoftDeleteMixin):
    """Log of webhook delivery attempts."""

    meta = {
        "collection": "webhook_deliveries",
        "indexes": [
            {"fields": ["organization_id", "webhook_config_id"]},
            {"fields": ["organization_id", "event_type"]},
            "organization_id",
            "status",
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    webhook_config_id = ReferenceField("WebhookConfig", required=True, reverse_delete_rule=2)
    event_type = StringField(required=True)
    payload = DictField()
    status = StringField(choices=["queued", "delivered", "failed", "retrying"], default="queued")
    http_status_code = IntField()
    response_body = StringField()
    response_headers = DictField()
    attempt_count = IntField(default=0)
    max_attempts = IntField(default=3)
    next_retry_at = DateTimeField()
    delivered_at = DateTimeField()
    created_at = DateTimeField()
    meta_data = DictField()


class ExternalHook(BaseDocument, SoftDeleteMixin):
    """External service hook configuration."""

    meta = {
        "collection": "external_hooks",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            {"fields": ["organization_id", "service_type"]},
            "organization_id",
            "service_type",
            "is_active",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    description = StringField()
    service_type = StringField(required=True)  # slack, teams, email, etc.
    config = DictField()  # Service-specific configuration
    events = ListField(StringField())  # Events that trigger this hook
    is_active = BooleanField(default=True)
    created_by = ReferenceField("User", reverse_delete_rule=3)
    last_used_at = DateTimeField()
    meta_data = DictField()


class OutboxEvent(BaseDocument):
    """Outbox pattern event for reliable message delivery."""

    meta = {
        "collection": "outbox_events",
        "indexes": [
            {"fields": ["organization_id", "event_type"]},
            {"fields": ["organization_id", "aggregate_id"]},
            {"fields": ["organization_id", "status"]},
            {"fields": ["created_at"], "expireAfterSeconds": 86400},  # 24 hour TTL
            "organization_id",
            "status",
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    event_type = StringField(required=True)
    aggregate_type = StringField(required=True)  # Form, FormResponse, etc.
    aggregate_id = StringField(required=True)
    payload = DictField()
    metadata = DictField()
    status = StringField(choices=["pending", "published", "failed"], default="pending")
    published_at = DateTimeField()
    error_message = StringField()
    retry_count = IntField(default=0)
    created_at = DateTimeField()
    meta_data = DictField()