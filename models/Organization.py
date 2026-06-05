"""
models/Organization.py
Model representing an Enterprise Organization in the RIDP Platform.
"""

from mongoengine import StringField, DictField
from .base import BaseDocument, SoftDeleteMixin

class Organization(BaseDocument, SoftDeleteMixin):
    """
    Represents an Enterprise Organization (tenant).
    Contains basic identity, status (active/suspended), administrative mappings, and metadata.
    """

    meta = {
        "collection": "organizations",
        "indexes": [
            {"fields": ["organization_id"], "unique": True},
            {"fields": ["status"]},
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, unique=True)
    name = StringField(required=True)
    display_name = StringField(required=True)
    status = StringField(choices=["active", "suspended"], default="active")
    admin_user_id = StringField(required=False)  # Maps to User.id (as UUID string or user_id)
    contact_email = StringField(required=False)
    description = StringField(required=False)
    metadata = DictField(default=dict)

    @classmethod
    def get_or_create(cls, organization_id: str, name: str = None, display_name: str = None) -> "Organization":
        """Gets settings for the specified organization_id, or creates a default one if it doesn't exist."""
        doc = cls.objects(organization_id=organization_id).first()
        if doc:
            return doc

        import uuid
        name = name or organization_id
        display_name = display_name or name

        try:
            cls._get_collection().update_one(
                {"organization_id": organization_id},
                {"$setOnInsert": {
                    "_id": str(uuid.uuid4()),
                    "organization_id": organization_id,
                    "name": name,
                    "display_name": display_name,
                    "status": "active",
                    "admin_user_id": None,
                    "contact_email": None,
                    "description": None,
                    "metadata": {},
                    "is_deleted": False,
                }},
                upsert=True,
            )
        except Exception:
            pass

        return cls.objects(organization_id=organization_id).first()
