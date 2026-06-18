from models.dashboard import Dashboard, UserDashboardSettings
from services.base import BaseService
from schemas.base import InboundPayloadSchema
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from logger.unified_logger import app_logger, error_logger, audit_logger


class WidgetSchema(BaseModel):
    id: Optional[str] = None
    title: str
    type: str
    form_id: Optional[str] = Field(default=None, validation_alias="form_ref")
    group_by_field: Optional[str] = None
    aggregate_field: Optional[str] = None
    calculation_type: str = "count"
    filters: Dict[str, Any] = Field(default_factory=dict)
    size: str = "medium"
    color_scheme: Optional[str] = None
    position_x: int = 0
    position_y: int = 0
    width: int = 2
    height: int = 2
    display_columns: List[str] = Field(default_factory=list)
    config: Dict[str, Any] = Field(default_factory=dict)


class DashboardSchema(BaseModel):
    id: Optional[str] = None
    title: str
    slug: str
    organization_id: str
    description: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    layout: str = "grid"
    widgets: List[WidgetSchema] = Field(default_factory=list)
    created_by: str


class UserSettingsSchema(BaseModel):
    user_id: str
    organization_id: str
    theme: str = "system"
    language: str = "en"
    timezone: str = "UTC"
    layout_config: Dict[str, Any] = Field(default_factory=dict)
    favorite_dashboards: List[str] = Field(default_factory=list)


class DashboardCreateSchema(DashboardSchema, InboundPayloadSchema):
    pass


class DashboardUpdateSchema(BaseModel, InboundPayloadSchema):
    title: Optional[str] = None
    description: Optional[str] = None
    roles: Optional[List[str]] = None
    layout: Optional[str] = None
    widgets: Optional[List[WidgetSchema]] = None


class DashboardService(BaseService):
    def __init__(self):
        super().__init__(model=Dashboard, schema=DashboardSchema)

    def _widget_to_schema(self, widget: Any) -> WidgetSchema:
        form_ref = None
        if hasattr(widget, "_data"):
            raw_form_ref = widget._data.get("form_ref") or widget._data.get("form_id")
            if raw_form_ref is not None:
                form_ref = getattr(raw_form_ref, "id", raw_form_ref)

        return WidgetSchema(
            id=str(getattr(widget, "id", "")) or None,
            title=getattr(widget, "title", ""),
            type=getattr(widget, "type", ""),
            form_id=str(form_ref) if form_ref is not None else None,
            group_by_field=getattr(widget, "group_by_field", None),
            aggregate_field=getattr(widget, "aggregate_field", None),
            calculation_type=getattr(widget, "calculation_type", "count"),
            filters=getattr(widget, "filters", {}) or {},
            size=getattr(widget, "size", "medium"),
            color_scheme=getattr(widget, "color_scheme", None),
            position_x=getattr(widget, "position_x", 0),
            position_y=getattr(widget, "position_y", 0),
            width=getattr(widget, "width", 2),
            height=getattr(widget, "height", 2),
            display_columns=getattr(widget, "display_columns", []) or [],
            config=getattr(widget, "config", {}) or {},
        )

    def _dashboard_snapshot(self, dashboard: Dashboard) -> Dict[str, Any]:
        widgets = [
            self._widget_to_schema(widget).model_dump()
            for widget in (dashboard.widgets or [])
        ]
        return {
            "snapshot_id": str(dashboard.id),
            "captured_at": (dashboard.updated_at or datetime.now(timezone.utc)).isoformat(),
            "dashboard_id": str(dashboard.id),
            "title": dashboard.title,
            "slug": dashboard.slug,
            "organization_id": dashboard.organization_id,
            "description": dashboard.description,
            "roles": dashboard.roles or [],
            "layout": dashboard.layout,
            "widgets": widgets,
            "widget_count": len(widgets),
        }

    def get_by_slug(self, slug: str, organization_id: str) -> DashboardSchema:
        app_logger.debug(f"Entering get_by_slug: {slug} (org: {organization_id})")
        try:
            document = self.model.objects(
                slug=slug, organization_id=organization_id
            ).first()
            if not document:
                from .exceptions import NotFoundError

                app_logger.warning(
                    f"Dashboard not found by slug: {slug} (org: {organization_id})"
                )
                raise NotFoundError(f"Dashboard {slug} not found")

            result = self._to_schema(document)
            app_logger.info(f"Dashboard Schema Result: {result.model_dump()}")
            app_logger.debug(f"Exiting get_by_slug: {slug} successfully")
            return result
        except Exception as e:
            if not isinstance(e, Exception):
                error_logger.error(
                    f"Error in get_by_slug {slug}: {str(e)}", exc_info=True
                )
            raise

    def get_canvas(self, dashboard_id: str, organization_id: str) -> Dict[str, Any]:
        app_logger.debug(
            f"Entering get_canvas: {dashboard_id} (org: {organization_id})"
        )
        from .exceptions import NotFoundError

        dashboard = self.model.objects(
            id=dashboard_id, organization_id=organization_id, is_deleted=False
        ).first()
        if not dashboard:
            raise NotFoundError("Dashboard not found")
        return self._dashboard_snapshot(dashboard)

    def update_canvas(
        self, dashboard_id: str, organization_id: str, canvas_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        app_logger.info(
            f"Entering update_canvas: {dashboard_id} (org: {organization_id})"
        )
        from .exceptions import NotFoundError

        dashboard = self.model.objects(
            id=dashboard_id, organization_id=organization_id, is_deleted=False
        ).first()
        if not dashboard:
            raise NotFoundError("Dashboard not found")

        allowed_fields = ("title", "description", "roles", "layout")
        for field in allowed_fields:
            if field in canvas_data:
                setattr(dashboard, field, canvas_data[field])

        widgets_payload = canvas_data.get("widgets")
        if widgets_payload is not None:
            normalized_widgets = []
            for item in widgets_payload:
                if isinstance(item, dict):
                    widget_item = dict(item)
                    widget_item.setdefault("form_ref", widget_item.get("form_id"))
                    normalized_widgets.append(WidgetSchema(**widget_item))
                else:
                    normalized_widgets.append(WidgetSchema(**item))
            dashboard.widgets = normalized_widgets

        dashboard.save()
        audit_logger.info(
            f"Audit: dashboard canvas updated for {dashboard_id} (org: {organization_id})"
        )
        return self._dashboard_snapshot(dashboard)

    def list_snapshots(
        self, dashboard_id: str, organization_id: str
    ) -> List[Dict[str, Any]]:
        snapshot = self.get_canvas(dashboard_id, organization_id)
        return [snapshot]

    # --- User Settings Logic ---
    def get_user_settings(
        self, user_id: str, organization_id: str
    ) -> UserSettingsSchema:
        app_logger.debug(
            f"Entering get_user_settings: {user_id} (org: {organization_id})"
        )
        try:
            settings = UserDashboardSettings.objects(
                user_id=user_id, organization_id=organization_id
            ).first()
            if not settings:
                app_logger.info(f"Creating new user dashboard settings for {user_id}")
                settings = UserDashboardSettings(
                    user_id=user_id, organization_id=organization_id
                )
                settings.save()

            # Simple manual conversion for settings as it's not the primary model of this service
            result = UserSettingsSchema(
                user_id=settings.user_id,
                organization_id=settings.organization_id,
                theme=settings.theme,
                language=settings.language,
                timezone=settings.timezone,
                layout_config=settings.layout_config,
                favorite_dashboards=settings.favorite_dashboards,
            )
            app_logger.debug(f"Exiting get_user_settings: {user_id} successfully")
            return result
        except Exception as e:
            error_logger.error(
                f"Error in get_user_settings for {user_id}: {str(e)}", exc_info=True
            )
            raise

    def update_user_settings(
        self, user_id: str, organization_id: str, data: Dict[str, Any]
    ) -> UserSettingsSchema:
        app_logger.info(
            f"Entering update_user_settings: {user_id} (org: {organization_id})"
        )
        try:
            settings = UserDashboardSettings.objects(
                user_id=user_id, organization_id=organization_id
            ).first()
            if not settings:
                app_logger.info(
                    f"Creating new user dashboard settings for {user_id} during update"
                )
                settings = UserDashboardSettings(
                    user_id=user_id, organization_id=organization_id
                )

            for key, val in data.items():
                if hasattr(settings, key) and key not in ["user_id", "organization_id"]:
                    setattr(settings, key, val)

            settings.save()

            audit_logger.info(
                f"Audit: User dashboard settings updated for {user_id} (org: {organization_id})"
            )
            app_logger.info(f"User dashboard settings updated for {user_id}")

            result = self.get_user_settings(user_id, organization_id)
            app_logger.debug(f"Exiting update_user_settings: {user_id} successfully")
            return result
        except Exception as e:
            error_logger.error(
                f"Error in update_user_settings for {user_id}: {str(e)}", exc_info=True
            )
            raise

    def get_available_widgets(self) -> List[Dict[str, Any]]:
        app_logger.debug("Entering get_available_widgets")
        widgets = [
            {
                "type": "chart_bar",
                "name": "Bar Chart",
                "description": "Aggregated data in bar format",
            },
            {
                "type": "chart_pie",
                "name": "Pie Chart",
                "description": "Percentage distribution",
            },
            {
                "type": "counter",
                "name": "Counter",
                "description": "Simple numeric count",
            },
            {
                "type": "table",
                "name": "Recent Responses",
                "description": "List of latest submissions",
            },
        ]
        app_logger.debug(f"Exiting get_available_widgets: {len(widgets)} widgets found")
        return widgets
