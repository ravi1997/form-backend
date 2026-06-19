"""
models/dashboard.py
Dashboard and visualization models.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument, FloatField,
    ObjectIdField
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument


class WidgetPosition(BaseEmbeddedDocument):
    """Widget position and size on canvas."""

    x = FloatField(required=True, default=0.0)
    y = FloatField(required=True, default=0.0)
    width = FloatField(required=True, default=200.0)
    height = FloatField(required=True, default=150.0)
    z_index = IntField(default=0)  # Layer ordering


class WidgetDataSource(BaseEmbeddedDocument):
    """Data source binding for widget."""

    analysis_id = ObjectIdField()  # Reference to analysis
    node_id = StringField()  # Analysis output node ID
    form_id = ObjectIdField()  # Direct form binding (legacy)
    refresh_mode = StringField(choices=["with_dashboard", "independent", "manual"], default="with_dashboard")
    refresh_interval = IntField()  # Widget-specific refresh interval
    filters = DictField()  # Data filtering configuration
    transformations = ListField(DictField())  # Data transformations


class WidgetConfig(BaseEmbeddedDocument):
    """Widget-specific configuration."""

    chart_type = StringField()  # bar, line, pie, etc.
    aggregation_type = StringField()  # count, sum, average, etc.
    group_by_field = StringField()
    value_field = StringField()
    color_scheme = StringField()
    show_legend = BooleanField(default=True)
    show_labels = BooleanField(default=True)
    max_items = IntField(default=10)
    sort_by = StringField()
    sort_order = StringField(default="desc")
    display_columns = ListField(StringField())
    theme_overrides = DictField()
    custom_styling = DictField()


class DashboardWidget(BaseEmbeddedDocument):
    """Individual widget on a dashboard."""

    id = StringField(required=True)
    widget_type = StringField(required=True)  # kpi_card, bar_chart, line_chart, pie_chart, data_table, text, image, filter
    title = StringField()
    description = StringField()
    position = EmbeddedDocumentField(WidgetPosition, required=True)
    data_source = EmbeddedDocumentField(WidgetDataSource)
    config = EmbeddedDocumentField(WidgetConfig)
    is_visible = BooleanField(default=True)
    is_locked = BooleanField(default=False)
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
    affects_widgets = ListField(StringField())  # Widget IDs affected by this filter
    meta_data = DictField()


class DashboardCanvas(BaseEmbeddedDocument):
    """Canvas configuration for dashboard."""

    width = FloatField(required=True, default=1200.0)
    height = FloatField(required=True, default=800.0)
    background_color = StringField(default="#ffffff")
    grid_enabled = BooleanField(default=True)
    grid_size = FloatField(default=20.0)
    snap_to_grid = BooleanField(default=True)
    theme = DictField()  # Canvas theme settings


class Dashboard(BaseDocument, SoftDeleteMixin):
    """Main dashboard configuration."""

    meta = {
        "collection": "dashboards",
        "indexes": [
            {"fields": ["organization_id", "name"], "unique": True},
            {"fields": ["organization_id", "slug"], "unique": True, "sparse": True},
            {"fields": ["organization_id", "project_id"]},
            "organization_id",
            "project_id",
            "created_by",
            "is_public",
            "public_token",
            {"fields": ["linked_analysis_ids"]},
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    project_id = StringField()  # Project this dashboard belongs to
    name = StringField(required=True, trim=True)
    slug = StringField(trim=True)
    description = StringField()
    canvas = EmbeddedDocumentField(DashboardCanvas, required=True)
    widgets = ListField(EmbeddedDocumentField(DashboardWidget))
    filters = ListField(EmbeddedDocumentField(DashboardFilter))
    linked_analysis_ids = ListField(ObjectIdField())  # Analyses this dashboard uses
    created_by = ReferenceField("User", reverse_delete_rule=3)
    owner = ReferenceField("User", reverse_delete_rule=3)
    collaborators = ListField(ReferenceField("User"))
    is_public = BooleanField(default=False)
    public_token = StringField(unique=True, sparse=True)
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
            {"fields": ["dashboard_id", "created_at"]},
            "organization_id",
            "dashboard_id",
            "created_at",
            {"fields": ["expires_at"], "expireAfterSeconds": 0},  # TTL index
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    dashboard_id = ReferenceField("Dashboard", required=True, reverse_delete_rule=2)
    name = StringField(required=True, trim=True)
    description = StringField()
    snapshot_data = DictField()  # Complete snapshot of all widget data
    widget_states = DictField()  # Individual widget data states
    filter_states = DictField()  # Filter states at snapshot time
    created_by = ReferenceField("User", reverse_delete_rule=3)
    expires_at = DateTimeField()
    is_public_snapshot = BooleanField(default=False)
    snapshot_token = StringField(unique=True, sparse=True)
    meta_data = DictField()


class UserDashboardSettings(BaseDocument, SoftDeleteMixin):
    """User-specific dashboard preferences."""

    meta = {
        "collection": "user_dashboard_settings",
        "indexes": [
            {"fields": ["organization_id", "user_id", "dashboard_id"], "unique": True},
            {"fields": ["user_id", "is_favorite"]},
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
    widget_collapsed = DictField()  # widget_id -> collapsed boolean
    is_favorite = BooleanField(default=False)
    last_accessed_at = DateTimeField()
    view_preferences = DictField()  # User's view preferences
    meta_data = DictField()


class DashboardRefreshSchedule(BaseDocument, SoftDeleteMixin):
    """Dashboard refresh schedule configuration."""

    meta = {
        "collection": "dashboard_refresh_schedules",
        "indexes": [
            {"fields": ["dashboard_id", "is_active"]},
            {"fields": ["next_run_at"]},
            "organization_id",
            "dashboard_id",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    dashboard_id = ReferenceField("Dashboard", required=True, reverse_delete_rule=2)
    schedule_type = StringField(choices=["interval", "cron", "manual"], default="interval")
    interval_seconds = IntField()  # For interval-based scheduling
    cron_expression = StringField()  # For cron-based scheduling
    is_active = BooleanField(default=True)
    next_run_at = DateTimeField()
    last_run_at = DateTimeField()
    run_count = IntField(default=0)
    created_by = ReferenceField("User", reverse_delete_rule=3)
    meta_data = DictField()


class DashboardPublicAccess(BaseDocument, SoftDeleteMixin):
    """Public access tracking for dashboards."""

    meta = {
        "collection": "dashboard_public_access",
        "indexes": [
            {"fields": ["dashboard_id", "access_token"]},
            {"fields": ["access_token"], "unique": True},
            {"fields": ["expires_at"], "expireAfterSeconds": 0},  # TTL index
            "dashboard_id",
            "created_at",
        ],
        "index_background": True,
    }

    organization_id = StringField(required=True, trim=True)
    dashboard_id = ReferenceField("Dashboard", required=True, reverse_delete_rule=2)
    access_token = StringField(required=True, unique=True)
    expires_at = DateTimeField()
    access_count = IntField(default=0)
    last_accessed_at = DateTimeField()
    ip_restrictions = ListField(StringField())  # Allowed IP addresses
    password_protected = BooleanField(default=False)
    access_password = StringField()  # Hashed password
    created_by = ReferenceField("User", reverse_delete_rule=3)
    meta_data = DictField()