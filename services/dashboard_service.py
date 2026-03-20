from models.Dashboard import Dashboard, UserDashboardSettings
from services.base import BaseService
from schemas.base import InboundPayloadSchema
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

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
        document = self.model.objects(slug=slug, organization_id=organization_id).first()
        if not document:
            from .exceptions import NotFoundError
            raise NotFoundError(f"Dashboard {slug} not found")
        return self._to_schema(document)

    # --- User Settings Logic ---
    def get_user_settings(self, user_id: str, organization_id: str) -> UserSettingsSchema:
        settings = UserDashboardSettings.objects(user_id=user_id, organization_id=organization_id).first()
        if not settings:
            settings = UserDashboardSettings(user_id=user_id, organization_id=organization_id)
            settings.save()
        
        # Simple manual conversion for settings as it's not the primary model of this service
        return UserSettingsSchema(
            user_id=settings.user_id,
            organization_id=settings.organization_id,
            theme=settings.theme,
            language=settings.language,
            timezone=settings.timezone,
            layout_config=settings.layout_config,
            favorite_dashboards=settings.favorite_dashboards
        )

    def update_user_settings(self, user_id: str, organization_id: str, data: Dict[str, Any]) -> UserSettingsSchema:
        settings = UserDashboardSettings.objects(user_id=user_id, organization_id=organization_id).first()
        if not settings:
            settings = UserDashboardSettings(user_id=user_id, organization_id=organization_id)
        
        for key, val in data.items():
            if hasattr(settings, key) and key not in ["user_id", "organization_id"]:
                setattr(settings, key, val)
        
        settings.save()
        return self.get_user_settings(user_id, organization_id)

    def get_available_widgets(self) -> List[Dict[str, Any]]:
        return [
            {"type": "chart_bar", "name": "Bar Chart", "description": "Aggregated data in bar format"},
            {"type": "chart_pie", "name": "Pie Chart", "description": "Percentage distribution"},
            {"type": "counter", "name": "Counter", "description": "Simple numeric count"},
            {"type": "table", "name": "Recent Responses", "description": "List of latest submissions"}
        ]
