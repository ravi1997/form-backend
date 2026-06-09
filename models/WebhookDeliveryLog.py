from datetime import datetime, timezone

from mongoengine import DateTimeField, DictField, IntField, StringField

from .base import BaseDocument


class WebhookDeliveryLog(BaseDocument):
    """
    Persistent delivery record for webhook attempts, status transitions, and logs.
    """

    meta = {
        "collection": "webhook_delivery_logs",
        "indexes": [
            "delivery_id",
            "webhook_id",
            "form_id",
            "status",
            "organization_id",
            "-created_at",
        ],
        "index_background": True,
    }

    delivery_id = StringField(required=True, unique=True)
    webhook_id = StringField(required=True)
    form_id = StringField(required=True)
    url = StringField(required=True)
    created_by = StringField()
    payload = DictField(default=dict)
    headers = DictField(default=dict)
    timeout = IntField(default=10)
    max_retries = IntField(default=5)
    retry_count = IntField(default=0)
    status = StringField(
        required=True,
        choices=["scheduled", "pending", "pending_delivery", "delivered", "failed", "cancelled"],
        default="pending",
    )
    scheduled_for = DateTimeField()
    last_error = StringField()
    response_status = IntField()
    delivered_at = DateTimeField()
    cancelled_at = DateTimeField()
    log_context = DictField(default=dict)

    @classmethod
    def from_record(cls, record):
        """Build a document payload from an in-memory delivery record."""
        data = dict(record or {})
        return cls(
            delivery_id=data.get("delivery_id"),
            webhook_id=data.get("webhook_id"),
            form_id=data.get("form_id"),
            url=data.get("url"),
            created_by=data.get("created_by"),
            organization_id=data.get("organization_id"),
            payload=data.get("payload", {}),
            headers=data.get("headers", {}),
            timeout=int(data.get("timeout", 10) or 10),
            max_retries=int(data.get("max_retries", 5) or 5),
            retry_count=int(data.get("retry_count", 0) or 0),
            status=data.get("status", "pending"),
            scheduled_for=cls._coerce_datetime(data.get("scheduled_for")),
            last_error=data.get("last_error"),
            response_status=data.get("response_status"),
            delivered_at=cls._coerce_datetime(data.get("delivered_at")),
            cancelled_at=cls._coerce_datetime(data.get("cancelled_at")),
            log_context=data.get("log_context", {}),
        )

    @staticmethod
    def _coerce_datetime(value):
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None
