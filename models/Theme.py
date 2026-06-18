from mongoengine import StringField, DateTimeField, DictField
from models.base import BaseDocument, SoftDeleteMixin


class Theme(BaseDocument, SoftDeleteMixin):
    """Form theme configuration."""

    meta = {
        "collection": "themes",
        "indexes": ["organization_id", "name"],
        "index_background": True,
    }

    organization_id = StringField()
    name = StringField()
    primary_color = StringField()
    secondary_color = StringField()
    font_family = StringField()
    theme_data = DictField()
    created_at = DateTimeField()
    meta_data = DictField()
