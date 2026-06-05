"""
models/FeatureFlag.py
Model representing a Feature Flag in the RIDP Platform.
"""

from mongoengine import StringField, BooleanField, DictField, QuerySet
from .base import BaseDocument

class FeatureFlag(BaseDocument):
    """
    FeatureFlag enables/disables specific features globally or on a per-organization basis.
    Bypasses tenant isolation query filtering as flags are system-wide objects.
    """

    meta = {
        "collection": "feature_flags",
        "queryset_class": QuerySet,
        "indexes": [
            {"fields": ["flag_key"], "unique": True},
        ],
        "index_background": True,
    }


    flag_key = StringField(required=True, unique=True)
    description = StringField(required=False)
    is_enabled = BooleanField(default=False)  # Global default
    per_org_overrides = DictField(default=dict)  # org_id -> bool
    scope = StringField(choices=["global", "org"], default="global")
