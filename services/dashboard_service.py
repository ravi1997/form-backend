from models.Dashboard import Dashboard, UserDashboardSettings
from services.base import BaseService
from schemas.base import InboundPayloadSchema
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from logger.unified_logger import app_logger, error_logger, audit_logger

class WidgetSchema(BaseModel):
    id: Optional[str] = None
    title: str
    type: str
    form_id: Optional[str] = None
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

    def get_by_slug(self, slug: str, organization_id: str) -> DashboardSchema:
        app_logger.debug(f"Entering get_by_slug: {slug} (org: {organization_id})")
        try:
            document = self.model.objects(slug=slug, organization_id=organization_id).first()
            if not document:
                from .exceptions import NotFoundError
                app_logger.warning(f"Dashboard not found by slug: {slug} (org: {organization_id})")
                raise NotFoundError(f"Dashboard {slug} not found")
            
            result = self._to_schema(document)
            app_logger.debug(f"Exiting get_by_slug: {slug} successfully")
            return result
        except Exception as e:
            if not isinstance(e, Exception):
                error_logger.error(f"Error in get_by_slug {slug}: {str(e)}", exc_info=True)
            raise

    # --- User Settings Logic ---
    def get_user_settings(self, user_id: str, organization_id: str) -> UserSettingsSchema:
        app_logger.debug(f"Entering get_user_settings: {user_id} (org: {organization_id})")
        try:
            settings = UserDashboardSettings.objects(user_id=user_id, organization_id=organization_id).first()
            if not settings:
                app_logger.info(f"Creating new user dashboard settings for {user_id}")
                settings = UserDashboardSettings(user_id=user_id, organization_id=organization_id)
                settings.save()
            
            # Simple manual conversion for settings as it's not the primary model of this service
            result = UserSettingsSchema(
                user_id=settings.user_id,
                organization_id=settings.organization_id,
                theme=settings.theme,
                language=settings.language,
                timezone=settings.timezone,
                layout_config=settings.layout_config,
                favorite_dashboards=settings.favorite_dashboards
            )
            app_logger.debug(f"Exiting get_user_settings: {user_id} successfully")
            return result
        except Exception as e:
            error_logger.error(f"Error in get_user_settings for {user_id}: {str(e)}", exc_info=True)
            raise

    def update_user_settings(self, user_id: str, organization_id: str, data: Dict[str, Any]) -> UserSettingsSchema:
        app_logger.info(f"Entering update_user_settings: {user_id} (org: {organization_id})")
        try:
            settings = UserDashboardSettings.objects(user_id=user_id, organization_id=organization_id).first()
            if not settings:
                app_logger.info(f"Creating new user dashboard settings for {user_id} during update")
                settings = UserDashboardSettings(user_id=user_id, organization_id=organization_id)
            
            for key, val in data.items():
                if hasattr(settings, key) and key not in ["user_id", "organization_id"]:
                    setattr(settings, key, val)
            
            settings.save()
            
            audit_logger.info(f"Audit: User dashboard settings updated for {user_id} (org: {organization_id})")
            app_logger.info(f"User dashboard settings updated for {user_id}")
            
            result = self.get_user_settings(user_id, organization_id)
            app_logger.debug(f"Exiting update_user_settings: {user_id} successfully")
            return result
        except Exception as e:
            error_logger.error(f"Error in update_user_settings for {user_id}: {str(e)}", exc_info=True)
            raise

    def get_available_widgets(self) -> List[Dict[str, Any]]:
        app_logger.debug("Entering get_available_widgets")
        widgets = [
            {"type": "chart_bar", "name": "Bar Chart", "description": "Aggregated data in bar format"},
            {"type": "chart_pie", "name": "Pie Chart", "description": "Percentage distribution"},
            {"type": "counter", "name": "Counter", "description": "Simple numeric count"},
            {"type": "table", "name": "Recent Responses", "description": "List of latest submissions"}
        ]
        app_logger.debug(f"Exiting get_available_widgets: {len(widgets)} widgets found")
        return widgets
