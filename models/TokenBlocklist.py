from mongoengine import StringField, DateTimeField
from models.base import BaseDocument


class TokenBlocklist(BaseDocument):
    """
    Stores revoked JWT tokens by their JTI with expiry.
    """

    meta = {
        "collection": "token_blocklist",
        "indexes": [
            "jti",
            {"fields": ["expires_at"], "expireAfterSeconds": 0},  # TTL index
        ],
        "index_background": True,
    }

    jti = StringField(required=True, unique=True, max_length=36)
    expires_at = DateTimeField(required=True)  # TTL support
