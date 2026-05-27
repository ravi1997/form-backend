"""
Reusable organization themes for form branding.
"""

from mongoengine import StringField, DictField, BooleanField, ListField

from .base import BaseDocument, SoftDeleteMixin


class Theme(BaseDocument, SoftDeleteMixin):
    meta = {
        "collection": "themes",
        "indexes": ["organization_id", "created_by", "is_global", "name"],
        "index_background": True,
    }

    name = StringField(required=True, max_length=255)
    description = StringField()
    organization_id = StringField(required=True)
    created_by = StringField(required=True)
    tokens = DictField(default=dict)
    branding = DictField(default=dict)
    tags = ListField(StringField())
    is_global = BooleanField(default=False)
    is_default = BooleanField(default=False)
