"""
models/oauth.py
OAuth 2.0 models for public API access.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument


class OAuthClient(BaseDocument, SoftDeleteMixin):
    """OAuth 2.0 client application."""

    meta = {
        "collection": "oauth_clients",
        "indexes": [
            {"fields": ["client_id"], "unique": True},
            {"fields": ["organization_id"]},
            {"fields": ["user_id"]},
            {"fields": ["is_active"]},
        ],
        "index_background": True,
    }

    client_id = StringField(required=True, unique=True)
    client_secret = StringField(required=True)
    client_name = StringField(required=True)
    client_type = StringField(choices=["confidential", "public"], default="confidential")
    redirect_uris = ListField(StringField())
    scopes = ListField(StringField())  # OAuth scopes
    grant_types = ListField(StringField(default="authorization_code"))
    response_types = ListField(StringField(default="code"))
    organization_id = StringField(required=True, trim=True)
    user_id = ReferenceField("User", required=True, reverse_delete_rule=3)
    is_active = BooleanField(default=True)
    is_trusted = BooleanField(default=False)
    website = StringField()
    description = StringField()
    logo_url = StringField()
    terms_of_service_url = StringField()
    privacy_policy_url = StringField()
    contact_email = StringField()
    created_at = DateTimeField()
    updated_at = DateTimeField()


class OAuthAuthorizationCode(BaseDocument):
    """OAuth 2.0 authorization code."""

    meta = {
        "collection": "oauth_authorization_codes",
        "indexes": [
            {"fields": ["code"], "unique": True},
            {"fields": ["client_id"]},
            {"fields": ["user_id"]},
            {"fields": ["expires_at"]},
        ],
        "index_background": True,
    }

    code = StringField(required=True, unique=True)
    client_id = StringField(required=True)
    user_id = ReferenceField("User", required=True, reverse_delete_rule=3)
    redirect_uri = StringField()
    scopes = ListField(StringField())
    state = StringField()
    code_challenge = StringField()  # PKCE
    code_challenge_method = StringField(choices=["plain", "S256"])
    nonce = StringField()  # OpenID Connect
    expires_at = DateTimeField(required=True)
    created_at = DateTimeField()


class OAuthAccessToken(BaseDocument):
    """OAuth 2.0 access token."""

    meta = {
        "collection": "oauth_access_tokens",
        "indexes": [
            {"fields": ["access_token"], "unique": True},
            {"fields": ["refresh_token"]},
            {"fields": ["client_id"]},
            {"fields": ["user_id"]},
            {"fields": ["expires_at"]},
        ],
        "index_background": True,
    }

    access_token = StringField(required=True, unique=True)
    refresh_token = StringField(unique=True)
    token_type = StringField(default="Bearer")
    expires_in = IntField(default=3600)  # 1 hour
    scopes = ListField(StringField())
    client_id = StringField(required=True)
    user_id = ReferenceField("User", required=True, reverse_delete_rule=3)
    organization_id = StringField(required=True, trim=True)
    created_at = DateTimeField()
    expires_at = DateTimeField()
    last_used_at = DateTimeField()
    is_revoked = BooleanField(default=False)
    device_info = DictField()  # User agent, IP address, etc.


class OAuthRefreshToken(BaseDocument):
    """OAuth 2.0 refresh token."""

    meta = {
        "collection": "oauth_refresh_tokens",
        "indexes": [
            {"fields": ["refresh_token"], "unique": True},
            {"fields": ["access_token"]},
            {"fields": ["client_id"]},
            {"fields": ["user_id"]},
            {"fields": ["expires_at"]},
        ],
        "index_background": True,
    }

    refresh_token = StringField(required=True, unique=True)
    access_token = StringField()
    client_id = StringField(required=True)
    user_id = ReferenceField("User", required=True, reverse_delete_rule=3)
    organization_id = StringField(required=True, trim=True)
    scopes = ListField(StringField())
    created_at = DateTimeField()
    expires_at = DateTimeField()
    is_revoked = BooleanField(default=False)
    last_used_at = DateTimeField()


class ApiKeyScope(BaseEmbeddedDocument):
    """API key scope definition."""

    resource = StringField(required=True)  # forms, responses, etc.
    actions = ListField(StringField(required=True))  # read, write, delete, etc.
    conditions = DictField()  # Additional conditions


class ApiKeyRateLimit(BaseEmbeddedDocument):
    """API key rate limit configuration."""

    requests_per_hour = IntField(default=1000)
    requests_per_day = IntField(default=10000)
    burst_limit = IntField(default=100)
    burst_window_seconds = IntField(default=60)


class EnhancedApiKey(BaseDocument, SoftDeleteMixin):
    """Enhanced API key with scopes and rate limits."""

    meta = {
        "collection": "api_keys",
        "indexes": [
            {"fields": ["key_hash"], "unique": True},
            {"fields": ["key_prefix"]},
            {"fields": ["organization_id"]},
            {"fields": ["user_id"]},
            {"fields": ["is_active"]},
            {"fields": ["expires_at"]},
        ],
        "index_background": True,
    }

    key_prefix = StringField(required=True)  # First 8 characters for display
    key_hash = StringField(required=True, unique=True)  # SHA-256 hash of the full key
    name = StringField(required=True)
    description = StringField()
    organization_id = StringField(required=True, trim=True)
    user_id = ReferenceField("User", required=True, reverse_delete_rule=3)
    scopes = ListField(EmbeddedDocumentField(ApiKeyScope))
    rate_limit = EmbeddedDocumentField(ApiKeyRateLimit)
    is_active = BooleanField(default=True)
    expires_at = DateTimeField()
    last_used_at = DateTimeField()
    usage_count = IntField(default=0)
    usage_last_hour = IntField(default=0)
    usage_last_day = IntField(default=0)
    ip_whitelist = ListField(StringField())
    allowed_origins = ListField(StringField())
    webhooks = ListField(DictField())  # Webhook URLs for API events
    created_by = ReferenceField("User", reverse_delete_rule=3)
    created_at = DateTimeField()
    updated_at = DateTimeField()
    revoked_at = DateTimeField()
    revoked_by = ReferenceField("User", reverse_delete_rule=3)


class ApiKeyUsageLog(BaseDocument):
    """API key usage logging."""

    meta = {
        "collection": "api_key_usage_logs",
        "indexes": [
            {"fields": ["api_key_id"]},
            {"fields": ["organization_id"]},
            {"fields": ["user_id"]},
            {"fields": ["endpoint"]},
            {"fields": ["method"]},
            {"fields": ["status_code"]},
            {"fields": ["timestamp"]},
        ],
        "index_background": True,
    }

    api_key_id = ReferenceField("EnhancedApiKey", required=True, reverse_delete_rule=3)
    organization_id = StringField(required=True, trim=True)
    user_id = ReferenceField("User", reverse_delete_rule=3)
    endpoint = StringField(required=True)
    method = StringField(required=True)
    status_code = IntField()
    response_time_ms = IntField()
    request_size_bytes = IntField()
    response_size_bytes = IntField()
    ip_address = StringField()
    user_agent = StringField()
    timestamp = DateTimeField()
    rate_limited = BooleanField(default=False)
    error_message = StringField()


class PublicApiEndpoint(BaseDocument):
    """Public API endpoint configuration."""

    meta = {
        "collection": "public_api_endpoints",
        "indexes": [
            {"fields": ["path"]},
            {"fields": ["method"]},
            {"fields": ["version"]},
            {"fields": ["is_active"]},
        ],
        "index_background": True,
    }

    path = StringField(required=True)
    method = StringField(required=True)
    version = StringField(default="v1")
    name = StringField(required=True)
    description = StringField()
    category = StringField()  # forms, responses, analytics, etc.
    required_scopes = ListField(StringField())
    authentication_required = BooleanField(default=True)
    rate_limit_enabled = BooleanField(default=True)
    custom_rate_limit = EmbeddedDocumentField(ApiKeyRateLimit)
    is_active = BooleanField(default=True)
    is_deprecated = BooleanField(default=False)
    deprecation_date = DateTimeField()
    sunset_date = DateTimeField()
    replacement_endpoint = StringField()
    created_at = DateTimeField()
    updated_at = DateTimeField()


class PublicApiDocumentation(BaseDocument):
    """Public API documentation."""

    meta = {
        "collection": "public_api_documentation",
        "indexes": [
            {"fields": ["endpoint_id"]},
            {"fields": ["version"]},
            {"fields": ["language"]},
        ],
        "index_background": True,
    }

    endpoint_id = ReferenceField("PublicApiEndpoint", required=True, reverse_delete_rule=3)
    version = StringField(required=True)
    language = StringField(default="en")
    title = StringField(required=True)
    description = StringField()
    parameters = ListField(DictField())
    request_body_schema = DictField()
    response_body_schema = DictField()
    examples = ListField(DictField())
    error_codes = ListField(DictField())
    created_at = DateTimeField()
    updated_at = DateTimeField()