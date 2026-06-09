from mongoengine import DateTimeField, DictField, IntField, StringField

from models.base import BaseDocument


class NotificationLog(BaseDocument):
    """
    Immutable delivery log for notification attempts and outcomes.
    """

    meta = {
        "collection": "notification_logs",
        "indexes": [
            "organization_id",
            "rule_id",
            "template_id",
            "status",
            "-created_at",
        ],
        "index_background": True,
    }

    rule_id = StringField(required=False)
    template_id = StringField(required=False)
    event_type = StringField(required=True)
    channel = StringField(required=True)
    recipient = StringField(required=False)
    status = StringField(
        required=True,
        choices=["pending", "sent", "failed", "skipped"],
        default="pending",
    )
    attempt_count = IntField(default=0)
    payload = DictField(default=dict)
    response = DictField(default=dict)
    error_message = StringField()
    sent_at = DateTimeField()
