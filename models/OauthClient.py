from mongoengine import StringField, ReferenceField, ListField, BooleanField

from models.base import BaseDocument, SoftDeleteMixin


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
