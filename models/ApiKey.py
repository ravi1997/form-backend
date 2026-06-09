from mongoengine import StringField, ReferenceField, DateTimeField, ListField, BooleanField

from models.base import BaseDocument, SoftDeleteMixin


class ApiKey(BaseDocument, SoftDeleteMixin):
    """
    Stores hashed API keys and their metadata for service-to-service access.
    """

    meta = {
        "collection": "api_keys",
        "indexes": [
            {"fields": ["organization_id", "key_prefix"]},
            {"fields": ["key_hash"], "unique": True},
            {"fields": ["organization_id", "name"], "unique": True},
            "revoked_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    key_prefix = StringField(required=True, trim=True, max_length=16)
    key_hash = StringField(required=True, unique=True)
    scopes = ListField(StringField(), default=list)
    created_by = ReferenceField("User", required=True, reverse_delete_rule=3)
    last_used_at = DateTimeField()
    expires_at = DateTimeField()
    revoked_at = DateTimeField()
    revoked_by = ReferenceField("User", reverse_delete_rule=3)
    is_active = BooleanField(default=True)
