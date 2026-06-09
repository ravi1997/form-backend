from mongoengine import StringField, ReferenceField, DateTimeField, BooleanField

from models.base import BaseDocument, SoftDeleteMixin


class Invitation(BaseDocument, SoftDeleteMixin):
    """
    Represents a pending or accepted invitation for a user or external email.
    """

    meta = {
        "collection": "invitations",
        "indexes": [
            {"fields": ["organization_id", "token"], "unique": True},
            {"fields": ["organization_id", "email"]},
            {"fields": ["organization_id", "status"]},
            "expires_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    email = StringField(required=True, trim=True)
    token = StringField(required=True, unique=True)
    invited_by = ReferenceField("User", required=True, reverse_delete_rule=3)
    group = ReferenceField("Group", reverse_delete_rule=2)
    role = StringField(default="member")
    status = StringField(
        choices=("pending", "accepted", "declined", "expired", "revoked"),
        default="pending",
    )
    expires_at = DateTimeField(required=True)
    accepted_at = DateTimeField()
    accepted_by = ReferenceField("User", reverse_delete_rule=3)
    message = StringField()
    is_email_verified = BooleanField(default=False)
