from mongoengine import StringField, ReferenceField, ListField, DateTimeField, BooleanField

from models.base import BaseDocument, SoftDeleteMixin


class Group(BaseDocument, SoftDeleteMixin):
    """
    Organization-scoped group used for access control and membership management.
    """

    meta = {
        "collection": "groups",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            {"fields": ["organization_id", "slug"], "unique": True, "sparse": True},
            "organization_id",
            "is_active",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    slug = StringField(trim=True)
    description = StringField()
    owner = ReferenceField("User", reverse_delete_rule=2)
    created_by = ReferenceField("User", reverse_delete_rule=3)
    members = ListField(ReferenceField("User"))
    is_active = BooleanField(default=True)
    created_from_invitation = ReferenceField("Invitation", reverse_delete_rule=3)
    last_used_at = DateTimeField()
