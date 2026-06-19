"""
models/event.py
Event bus and event processing models.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument, FloatField
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument


class EventType(BaseDocument):
    """Event type definitions and metadata."""

    meta = {
        "collection": "event_types",
        "indexes": [
            {"fields": ["event_type"], "unique": True},
            {"fields": ["organization_id", "category"]},
            "is_active",
        ],
        "index_background": True,
    }

    event_type = StringField(required=True, unique=True)
    name = StringField(required=True)
    description = StringField()
    category = StringField(required=True)  # form, response, user, system, etc.
    version = StringField(default="1.0")
    
    # Event schema
    payload_schema = DictField(default=dict)
    required_fields = ListField(StringField(), default=list)
    
    # Event processing
    is_active = BooleanField(default=True)
    is_internal = BooleanField(default=False)
    
    # Organization scoping
    organization_id = StringField()
    
    created_at = DateTimeField()
    updated_at = DateTimeField()


class EventSubscription(BaseDocument, SoftDeleteMixin):
    """Event subscription for handling specific events."""

    meta = {
        "collection": "event_subscriptions",
        "indexes": [
            {"fields": ["organization_id", "event_type"]},
            {"fields": ["organization_id", "handler_type"]},
            {"fields": ["organization_id", "is_active"]},
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True)
    name = StringField(required=True)
    event_type = StringField(required=True)
    
    # Handler configuration
    handler_type = StringField(required=True)  # webhook, email, sms, function, etc.
    handler_config = DictField(required=True)
    
    # Filtering
    filter_conditions = DictField(default=dict)
    
    # Processing options
    is_active = BooleanField(default=True)
    process_async = BooleanField(default=True)
    max_retries = IntField(default=3)
    retry_delay_seconds = IntField(default=60)
    
    # Rate limiting
    rate_limit_per_minute = IntField(default=60)
    rate_limit_per_hour = IntField(default=1000)
    
    # Tracking
    created_by = ReferenceField("User", reverse_delete_rule=3)
    created_at = DateTimeField()
    last_triggered_at = DateTimeField()
    trigger_count = IntField(default=0)
    failure_count = IntField(default=0)
    
    meta_data = DictField(default=dict)


class Event(BaseDocument):
    """Event instance for processing."""

    meta = {
        "collection": "events",
        "indexes": [
            {"fields": ["organization_id", "event_type"]},
            {"fields": ["organization_id", "aggregate_type", "aggregate_id"]},
            {"fields": ["organization_id", "status"]},
            {"fields": ["created_at"], "expireAfterSeconds": 604800},  # 7 day TTL
            "status",
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True)
    event_type = StringField(required=True)
    event_id = StringField(required=True, unique=True)
    
    # Event data
    aggregate_type = StringField(required=True)  # Form, FormResponse, User, etc.
    aggregate_id = StringField(required=True)
    payload = DictField(required=True)
    metadata = DictField(default=dict)
    
    # Event processing
    status = StringField(choices=["pending", "processing", "delivered", "failed", "expired"], default="pending")
    processing_attempts = IntField(default=0)
    max_processing_attempts = IntField(default=3)
    next_processing_at = DateTimeField()
    
    # Tracking
    triggered_by = ReferenceField("User", reverse_delete_rule=3)
    source_system = StringField(default="form-builder")
    correlation_id = StringField()
    
    created_at = DateTimeField()
    processed_at = DateTimeField()
    expires_at = DateTimeField()


class EventDelivery(BaseDocument):
    """Event delivery tracking to subscribers."""

    meta = {
        "collection": "event_deliveries",
        "indexes": [
            {"fields": ["organization_id", "event_id"]},
            {"fields": ["organization_id", "subscription_id"]},
            {"fields": ["organization_id", "status"]},
            {"fields": ["created_at"], "expireAfterSeconds": 2592000},  # 30 day TTL
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True)
    event_id = StringField(required=True)
    subscription_id = StringField(required=True)
    
    # Delivery information
    delivery_id = StringField(required=True, unique=True)
    handler_type = StringField(required=True)
    handler_config = DictField(required=True)
    
    # Delivery status
    status = StringField(choices=["pending", "delivering", "delivered", "failed", "retrying"], default="pending")
    attempt_count = IntField(default=0)
    max_attempts = IntField(default=3)
    next_attempt_at = DateTimeField()
    
    # Delivery results
    response_status_code = IntField()
    response_body = StringField()
    response_headers = DictField()
    error_message = StringField()
    
    # Timing
    created_at = DateTimeField()
    first_attempt_at = DateTimeField()
    last_attempt_at = DateTimeField()
    delivered_at = DateTimeField()
    delivery_time_ms = FloatField()
    
    meta_data = DictField(default=dict)


class EventLog(BaseDocument):
    """Event processing log for auditing and debugging."""

    meta = {
        "collection": "event_logs",
        "indexes": [
            {"fields": ["organization_id", "event_type"]},
            {"fields": ["organization_id", "event_id"]},
            {"fields": ["organization_id", "log_level"]},
            {"fields": ["created_at"], "expireAfterSeconds": 2592000},  # 30 day TTL
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True)
    event_id = StringField()
    event_type = StringField()
    
    # Log information
    log_level = StringField(choices=["debug", "info", "warn", "error"], default="info")
    message = StringField(required=True)
    details = DictField(default=dict)
    
    # Context
    subscription_id = StringField()
    delivery_id = StringField()
    handler_type = StringField()
    
    # Tracking
    created_at = DateTimeField()
    source_component = StringField(default="event-bus")
    correlation_id = StringField()