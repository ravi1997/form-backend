import uuid
from datetime import datetime, timezone
from mongoengine import DateTimeField, DictField, StringField, IntField
from .base import BaseDocument


class OutboxEvent(BaseDocument):
    meta = {
        "collection": "outbox_events",
        "indexes": [
            "status",
            "-created_at",
            "organization_id",
        ],
        "index_background": True,
    }

    topic = StringField(required=True)
    payload = DictField(required=True)
    status = StringField(
        required=True,
        choices=["pending", "published", "failed"],
        default="pending",
    )
    retry_count = IntField(default=0)
    error_message = StringField()
    processed_at = DateTimeField()
