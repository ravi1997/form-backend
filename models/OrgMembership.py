from mongoengine import StringField, ReferenceField, DateTimeField, BooleanField

from models.base import BaseDocument, SoftDeleteMixin


class OrgMembership(BaseDocument, SoftDeleteMixin):
    """
    Maps a user to an organization and tracks the user's membership lifecycle.
    """

    meta = {
        "collection": "org_memberships",
        "indexes": [
            {"fields": ["organization_id", "user"], "unique": True},
            "organization_id",
            "user",
            "status",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    user = ReferenceField("User", required=True, reverse_delete_rule=2)
    role = StringField(required=True, default="member")
    status = StringField(
        choices=("pending", "active", "suspended", "removed"),
        default="pending",
    )
    invited_by = ReferenceField("User", reverse_delete_rule=3)
    joined_at = DateTimeField()
    last_active_at = DateTimeField()
    is_primary = BooleanField(default=False)
