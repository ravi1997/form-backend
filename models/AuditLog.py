"""
models/AuditLog.py
Model for storing audit log entries with soft-delete support.
"""
from mongoengine import StringField, DictField, DateTimeField
from datetime import datetime, timezone
from .base import BaseDocument, SoftDeleteMixin

class AuditLog(BaseDocument, SoftDeleteMixin):
    """
    Persistent store for all administrative and data-altering actions.
    Provides a tamper-evident record of WHO changed WHAT and WHEN.
    """

    meta = {
        "collection": "audit_logs",
        "indexes": ["organization_id", "resource_type", "resource_id", "actor_id", "-timestamp"],
        "index_background": True,
    }

    organization_id = StringField(required=True)

    actor_id = StringField(required=True)  # User ID who performed action
    action = StringField(required=True)  # create, update, delete, login, publish
    resource_type = StringField()  # form, project, user, response
    resource_id = StringField()  # the UUID of the target resource

    # State snapshots
    previous_state = DictField()
    new_state = DictField()

    timestamp = DateTimeField(default=lambda: datetime.now(timezone.utc))
    ip_address = StringField()
    metadata = DictField()
