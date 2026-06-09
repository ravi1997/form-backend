from mongoengine import BooleanField, DictField, IntField, ListField, StringField

from models.base import BaseDocument, SoftDeleteMixin


class NotificationRule(BaseDocument, SoftDeleteMixin):
    """
    Tenant-scoped routing rule that binds an event to a notification template.
    """

    meta = {
        "collection": "notification_rules",
        "indexes": [
            "organization_id",
            "event_type",
            "is_active",
            "priority",
            {"fields": ["organization_id", "name"], "unique": True},
        ],
        "index_background": True,
    }

    name = StringField(required=True)
    description = StringField()
    event_type = StringField(required=True)
    template_id = StringField(required=True)
    channels = ListField(StringField(), default=list)
    conditions = DictField(default=dict)
    priority = IntField(default=0)
    cooldown_seconds = IntField(default=0)
    is_active = BooleanField(default=True)
    metadata = DictField(default=dict)
