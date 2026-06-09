from mongoengine import StringField, ReferenceField, DateTimeField, BooleanField

from models.base import BaseDocument, SoftDeleteMixin


class GroupMember(BaseDocument, SoftDeleteMixin):
    """
    Explicit membership edge between a user and a group.
    """

    meta = {
        "collection": "group_members",
        "indexes": [
            {"fields": ["group", "user"], "unique": True},
            "organization_id",
            "group",
            "user",
            "status",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    group = ReferenceField("Group", required=True, reverse_delete_rule=2)
    user = ReferenceField("User", required=True, reverse_delete_rule=2)
    role = StringField(default="member")
    status = StringField(
        choices=("pending", "active", "suspended", "removed"),
        default="active",
    )
    invited_by = ReferenceField("User", reverse_delete_rule=3)
    joined_at = DateTimeField()
    is_admin = BooleanField(default=False)
