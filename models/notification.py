"""
models/notification.py
Notification system models.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument


class NotificationTemplate(BaseDocument, SoftDeleteMixin):
    """Template for notification content."""

    meta = {
        "collection": "notification_templates",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            {"fields": ["organization_id", "event_type"]},
            "organization_id",
            "is_system",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    description = StringField()
    event_type = StringField(required=True)
    channels = DictField()  # email, sms, in_app, push configurations
    variables = ListField(DictField())  # Template variables with descriptions
    is_system = BooleanField(default=False)
    is_active = BooleanField(default=True)
    created_by = ReferenceField("User", reverse_delete_rule=3)
    meta_data = DictField()


class NotificationRule(BaseDocument, SoftDeleteMixin):
    """Rule for when and how to send notifications."""

    meta = {
        "collection": "notification_rules",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            {"fields": ["organization_id", "event_type"]},
            "organization_id",
            "form_id",
            "is_active",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    description = StringField()
    event_type = StringField(required=True)
    trigger_conditions = ListField(DictField())
    channels = ListField(StringField(choices=["email", "sms", "in_app", "push", "webhook"]))
    recipient_type = StringField(choices=["form_owner", "specific_users", "role", "group", "respondent"])
    recipient_ids = ListField(ReferenceField("User", reverse_delete_rule=3))
    template_id = ReferenceField("NotificationTemplate", reverse_delete_rule=3)
    form_id = ReferenceField("Form", reverse_delete_rule=3)
    is_active = BooleanField(default=True)
    created_by = ReferenceField("User", reverse_delete_rule=3)
    meta_data = DictField()


class Notification(BaseDocument, SoftDeleteMixin):
    """Individual notification message."""

    meta = {
        "collection": "notifications",
        "indexes": [
            {"fields": ["organization_id", "recipient_id"]},
            {"fields": ["organization_id", "rule_id"]},
            "organization_id",
            "recipient_id",
            "status",
            "channel",
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    rule_id = ReferenceField("NotificationRule", reverse_delete_rule=3)
    recipient_id = ReferenceField("User", required=True, reverse_delete_rule=2)
    channel = StringField(choices=["email", "sms", "in_app", "push", "webhook"])
    status = StringField(choices=["queued", "sent", "failed", "retrying"], default="queued")
    title = StringField()
    message = StringField()
    data = DictField()  # Notification-specific data
    attempt_count = IntField(default=0)
    max_attempts = IntField(default=3)
    next_retry_at = DateTimeField()
    provider_response = DictField()
    created_at = DateTimeField()
    sent_at = DateTimeField()
    read_at = DateTimeField()
    meta_data = DictField()


class NotificationPreference(BaseDocument, SoftDeleteMixin):
    """User notification preferences."""

    meta = {
        "collection": "notification_preferences",
        "indexes": [
            {"fields": ["organization_id", "user_id"], "unique": True},
            "organization_id",
            "user_id",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    user_id = ReferenceField("User", required=True, reverse_delete_rule=2)
    email_notifications = BooleanField(default=True)
    sms_notifications = BooleanField(default=True)
    in_app_notifications = BooleanField(default=True)
    push_notifications = BooleanField(default=True)
    event_preferences = DictField()  # event_type -> enabled boolean
    quiet_hours = DictField()  # start_time, end_time, timezone
    meta_data = DictField()


class NotificationLog(BaseDocument):
    """Log of all notification attempts."""

    meta = {
        "collection": "notification_logs",
        "indexes": [
            {"fields": ["organization_id", "notification_id"]},
            {"fields": ["organization_id", "rule_id"]},
            "organization_id",
            "status",
            "channel",
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    notification_id = ReferenceField("Notification", reverse_delete_rule=2)
    rule_id = ReferenceField("NotificationRule", reverse_delete_rule=3)
    recipient_id = ReferenceField("User", reverse_delete_rule=3)
    channel = StringField()
    status = StringField()
    attempt_number = IntField()
    provider = StringField()
    provider_response = DictField()
    error_message = StringField()
    created_at = DateTimeField()
    meta_data = DictField()