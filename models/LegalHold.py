"""
models/LegalHold.py
Model for tracking legal holds placed on forms or specific responses.
"""

from mongoengine import StringField, BooleanField, DateTimeField
from datetime import datetime, timezone
from .base import BaseDocument, SoftDeleteMixin

class LegalHold(BaseDocument, SoftDeleteMixin):
    """
    Legal Hold foundation. Active holds block the deletion (soft or hard)
    of forms and responses.
    """

    meta = {
        "collection": "legal_holds",
        "indexes": [
            "organization_id",
            "target_type",
            "target_id",
            "is_active",
            ("target_type", "target_id", "is_active"),
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True)
    target_type = StringField(required=True, choices=("form", "response"))
    target_id = StringField(required=True)  # UUID of target form or response as string
    is_active = BooleanField(default=True)
    reason = StringField(required=True)
    held_by = StringField(required=True)     # User ID or name of the compliance officer
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
