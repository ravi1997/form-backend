from datetime import datetime, timezone

from mongoengine import DateTimeField, StringField

from models.base import BaseDocument


class Tombstone(BaseDocument):
    """Records a permanently deleted entity so offline clients can reconcile local caches."""

    meta = {
        "collection": "tombstones",
        "indexes": [
            "organization_id",
            "entity_type",
            "entity_id",
            ("organization_id", "entity_type", "-deleted_at"),
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, db_field="org_id")
    entity_type = StringField(required=True)
    entity_id = StringField(required=True)
    deleted_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
