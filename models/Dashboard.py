from mongoengine import (
    StringField,
    ListField,
    ReferenceField,
    DictField,
    IntField,
    EmbeddedDocument,
    EmbeddedDocumentField,
    UUIDField,
    DateTimeField,
)
import uuid
from datetime import datetime, timezone
from models.base import BaseDocument, SoftDeleteMixin


class DashboardWidget(EmbeddedDocument):
    id = UUIDField(primary_key=True, default=uuid.uuid4, binary=False)
    title = StringField()
    type = StringField()
    form_ref = ReferenceField("Form")
    group_by_field = StringField()
    aggregate_field = StringField()
    calculation_type = StringField(default="count")
    filters = DictField()
    size = StringField(default="medium")
    color_scheme = StringField()
    position_x = IntField(default=0)
    position_y = IntField(default=0)
    width = IntField(default=2)
    height = IntField(default=2)
    display_columns = ListField(StringField())
    config = DictField()


class Dashboard(BaseDocument, SoftDeleteMixin):
    meta = {
        "collection": "dashboards",
        "indexes": ["slug", "organization_id"],
        "index_background": True,
    }
    title = StringField(required=True)
    slug = StringField(required=True, unique=True)
    organization_id = StringField(required=True)
    description = StringField()
    roles = ListField(StringField())
    layout = StringField(default="grid")
    widgets = ListField(EmbeddedDocumentField(DashboardWidget))
    created_by = StringField(required=True)


class UserDashboardSettings(BaseDocument):
    meta = {
        "collection": "user_dashboard_settings",
        "indexes": ["user_id", "organization_id"],
        "index_background": True,
    }
    user_id = StringField(required=True, unique=True)
    organization_id = StringField(required=True)
    theme = StringField(default="system")
    language = StringField(default="en")
    timezone = StringField(default="UTC")
    layout_config = DictField(default=dict)
    favorite_dashboards = ListField(StringField())
