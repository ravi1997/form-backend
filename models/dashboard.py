"""
models/dashboard.py
Dashboard and visualization models.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument, FloatField
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument


class DashboardWidget(BaseEmbeddedDocument):
    """Individual widget on a dashboard."""

    id = StringField(required=True)
    widget_type = StringField(required=True)  # chart, table, kpi, text, image, etc.
    title = StringField()
    description = StringField()
    position = DictField()  # x, y, width, height
    config = DictField()  # Widget-specific configuration
    data_source = DictField()  # Analysis result, form data, etc.
    refresh_interval = IntField()  # Seconds
    is_visible = BooleanField(default=True)
    meta_data = DictField()


class DashboardFilter(BaseEmbeddedDocument):
    """Filter configuration for dashboard data."""

    id = StringField(required=True)
    name = StringField(required=True)
    filter_type = StringField(required=True)  # date_range, text_select, multi_select, etc.
    field_name = StringField(required=True)
    options = ListField(DictField())
    default_value = StringField()
    is_required = BooleanField(default=False)
    meta_data = DictField()


class Dashboard(BaseDocument, SoftDeleteMixin):
    """Main dashboard configuration."""

    meta = {
        "collection": "dashboards",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            {"fields": ["organization_id", "slug"], "unique": True, "sparse": True},
            "organization_id",
            "created_by",
            "is_public",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    name = StringField(required=True, trim=True)
    slug = StringField(trim=True)
    description = StringField()
    widgets = ListField(EmbeddedDocumentField(DashboardWidget))
    filters = ListField(EmbeddedDocumentField(DashboardFilter))
    layout = DictField()  # Overall layout configuration
    theme = DictField()  # Dashboard theme settings
    created_by = ReferenceField("User", reverse_delete_rule=3)
    owner = ReferenceField("User", reverse_delete_rule=3)
    collaborators = ListField(ReferenceField("User"))
    is_public = BooleanField(default=False)
    public_token = StringField()
    auto_refresh = BooleanField(default=False)
    refresh_interval = IntField(default=300)  # 5 minutes
    status = StringField(choices=("draft", "published", "archived"), default="draft")
    meta_data = DictField()


class DashboardSnapshot(BaseDocument, SoftDeleteMixin):
    """Snapshot of dashboard data at a point in time."""

    meta = {
        "collection": "dashboard_snapshots",
        "indexes": [
            {"fields": ["organization_id", "dashboard_id"]},
            "organization_id",
            "dashboard_id",
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    dashboard_id = ReferenceField("Dashboard", required=True, reverse_delete_rule=2)
    name = StringField(required=True, trim=True)
    description = StringField()
    snapshot_data = DictField()  # Complete snapshot of all widget data
    created_by = ReferenceField("User", reverse_delete_rule=3)
    expires_at = DateTimeField()
    meta_data = DictField()


class UserDashboardSettings(BaseDocument, SoftDeleteMixin):
    """User-specific dashboard preferences."""

    meta = {
        "collection": "user_dashboard_settings",
        "indexes": [
            {"fields": ["organization_id", "user_id", "dashboard_id"], "unique": True},
            "organization_id",
            "user_id",
            "dashboard_id",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    user_id = ReferenceField("User", required=True, reverse_delete_rule=2)
    dashboard_id = ReferenceField("Dashboard", required=True, reverse_delete_rule=2)
    widget_visibility = DictField()  # widget_id -> visible boolean
    widget_positions = DictField()  # widget_id -> position dict
    filter_defaults = DictField()  # filter_id -> default value
    is_favorite = BooleanField(default=False)
    last_accessed_at = DateTimeField()
    meta_data = DictField()