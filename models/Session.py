from mongoengine import StringField, ReferenceField, DateTimeField, BooleanField

from models.base import BaseDocument


class Session(BaseDocument):
    """
    Tracks a login session or refresh-token session for a user.
    """

    meta = {
        "collection": "sessions",
        "indexes": [
            {"fields": ["organization_id", "user"]},
            {"fields": ["session_id"], "unique": True},
            {"fields": ["refresh_token_jti"], "unique": True, "sparse": True},
            {"fields": ["expires_at"], "expireAfterSeconds": 0},
            "revoked_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    user = ReferenceField("User", required=True, reverse_delete_rule=2)
    session_id = StringField(required=True, unique=True)
    refresh_token_jti = StringField()
    ip_address = StringField()
    user_agent = StringField()
    device_fingerprint = StringField()
    is_active = BooleanField(default=True)
    created_from = StringField(default="web")
    last_seen_at = DateTimeField()
    expires_at = DateTimeField(required=True)
    revoked_at = DateTimeField()
    revoked_reason = StringField()
