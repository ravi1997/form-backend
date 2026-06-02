"""
models/OidcUserMapping.py
Model for mapping external identity provider users (OIDC/OAuth2/SAML) to local users.
"""

from mongoengine import StringField, DictField, UUIDField
from .base import BaseDocument, SoftDeleteMixin

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
