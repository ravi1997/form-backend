from datetime import datetime, timezone

from mongoengine import DateTimeField, DictField, StringField

from .base import BaseDocument


class IdempotencyRecord(BaseDocument):
    meta = {
        "collection": "idempotency_records",
        "indexes": [
            {
                "fields": ["organization_id", "user_id", "key", "route"],
                "unique": True,
            },
            "-created_at",
            "expires_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True)
    user_id = StringField(required=True)
    key = StringField(required=True)
    route = StringField(required=True)
    request_hash = StringField(required=True)
    status = StringField(default="completed")
    response_body = DictField(default=dict)
    response_status = StringField(default="200")
    expires_at = DateTimeField(
        default=lambda: datetime.now(timezone.utc).replace(microsecond=0)
    )
