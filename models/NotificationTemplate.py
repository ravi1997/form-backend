from mongoengine import BooleanField, DictField, ListField, StringField

from models.base import BaseDocument, SoftDeleteMixin


class NotificationTemplate(BaseDocument, SoftDeleteMixin):
    """
    Tenant-scoped reusable notification template.
    Stores message content and metadata for downstream delivery engines.
    """

    meta = {
        "collection": "notification_templates",
        "indexes": [
            "organization_id",
            "name",
            "channel",
            "is_active",
            {"fields": ["organization_id", "name"], "unique": True},
        ],
        "index_background": True,
    }

    name = StringField(required=True)
    description = StringField()
    channel = StringField(required=True)  # email, sms, webhook, in_app
    subject = StringField()
    body = StringField(required=True)
    html_body = StringField()
    locale = StringField(default="en")
    variables = ListField(StringField(), default=list)
    metadata = DictField(default=dict)
    is_active = BooleanField(default=True)
    is_default = BooleanField(default=False)
