"""
models/auth.py
Authentication and authorization models: API keys, sessions, OAuth, and token management.
"""

from datetime import datetime, timezone
from mongoengine import (
    StringField, ReferenceField, DateTimeField, ListField, BooleanField,
    DictField, UUIDField
)
from models.base import BaseDocument, SoftDeleteMixin

# Lazy import User to avoid circular dependency
def _get_user_model():
    from models.identity import User
    return User


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


class OauthClient(BaseDocument, SoftDeleteMixin):
    """
    Registered OAuth client for third-party or internal authorization flows.
    """

    meta = {
        "collection": "oauth_clients",
        "indexes": [
            {"fields": ["organization_id", "client_id"], "unique": True},
            {"fields": ["organization_id", "name"], "unique": True},
            "is_active",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    client_id = StringField(required=True, unique=True)
    client_secret_hash = StringField(required=True)
    redirect_uris = ListField(StringField(), default=list)
    allowed_grant_types = ListField(
        StringField(
            choices=("authorization_code", "refresh_token", "client_credentials", "password")
        ),
        default=list,
    )
    scopes = ListField(StringField(), default=list)
    owner = ReferenceField("User", reverse_delete_rule=2)
    is_confidential = BooleanField(default=True)
    is_active = BooleanField(default=True)


class OidcUserMapping(BaseDocument, SoftDeleteMixin):
    """
    Maps an external OIDC/OAuth2 subject ID to an internal application user ID.
    Enables single sign-on mapping for tenants.
    """

    meta = {
        "collection": "oidc_user_mappings",
        "indexes": [
            "organization_id",
            "provider",
            "subject_id",
            "user_id",
            ("provider", "subject_id"),
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True)
    provider = StringField(required=True)      # e.g., 'google', 'keycloak', 'okta'
    subject_id = StringField(required=True)    # The 'sub' claim from OIDC provider
    user_id = UUIDField(required=True)         # Internal User.id
    email = StringField(required=False)
    claims = DictField(default=dict)           # Storing raw claim payload for audit/debugging


# Invitation model moved to identity.py to avoid circular dependencies