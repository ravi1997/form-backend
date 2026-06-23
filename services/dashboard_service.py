from models.dashboard import (
    Dashboard, DashboardWidget, DashboardFilter, DashboardCanvas,
    WidgetPosition, WidgetDataSource, WidgetConfig,
    DashboardSnapshot, UserDashboardSettings, DashboardRefreshSchedule,
    DashboardPublicAccess
)
from services.base import BaseService
from schemas.base import InboundPayloadSchema
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timezone, timedelta
from logger.unified_logger import app_logger, error_logger, audit_logger
import uuid
import secrets
import hashlib


class PositionSchema(BaseModel):
    x: float = 0.0
    y: float = 0.0
    width: float = 200.0
    height: float = 150.0
    z_index: int = 0


class DataSourceSchema(BaseModel):
    analysis_id: Optional[str] = None
    node_id: Optional[str] = None
    form_id: Optional[str] = None
    refresh_mode: str = "with_dashboard"
    refresh_interval: Optional[int] = None
    filters: Dict[str, Any] = Field(default_factory=dict)
    transformations: List[Dict[str, Any]] = Field(default_factory=list)


class WidgetConfigSchema(BaseModel):
    chart_type: Optional[str] = None
    aggregation_type: Optional[str] = None
    group_by_field: Optional[str] = None
    value_field: Optional[str] = None
    color_scheme: Optional[str] = None
    show_legend: bool = True
    show_labels: bool = True
    max_items: int = 10
    sort_by: Optional[str] = None
    sort_order: str = "desc"
    display_columns: List[str] = Field(default_factory=list)
    theme_overrides: Dict[str, Any] = Field(default_factory=dict)
    custom_styling: Dict[str, Any] = Field(default_factory=dict)


class WidgetSchema(BaseModel):
    id: Optional[str] = None
    widget_type: str
    title: Optional[str] = None
    description: Optional[str] = None
    position: PositionSchema
    data_source: Optional[DataSourceSchema] = None
    config: Optional[WidgetConfigSchema] = None
    is_visible: bool = True
    is_locked: bool = False
    meta_data: Dict[str, Any] = Field(default_factory=dict)


class CanvasSchema(BaseModel):
    width: float = 1200.0
    height: float = 800.0
    background_color: str = "#ffffff"
    grid_enabled: bool = True
    grid_size: float = 20.0
    snap_to_grid: bool = True
    theme: Dict[str, Any] = Field(default_factory=dict)


class FilterSchema(BaseModel):
    id: Optional[str] = None
    name: str
    filter_type: str
    field_name: str
    options: List[Dict[str, Any]] = Field(default_factory=list)
    default_value: Optional[str] = None
    is_required: bool = False
    affects_widgets: List[str] = Field(default_factory=list)
    meta_data: Dict[str, Any] = Field(default_factory=dict)


class DashboardSchema(BaseModel):
    id: Optional[str] = None
    title: str
    slug: str
    organization_id: str
    project_id: Optional[str] = None
    description: Optional[str] = None
    canvas: CanvasSchema
    widgets: List[WidgetSchema] = Field(default_factory=list)
    filters: List[FilterSchema] = Field(default_factory=list)
    linked_analysis_ids: List[str] = Field(default_factory=list)
    is_public: bool = False
    auto_refresh: bool = False
    refresh_interval: int = 300
    status: str = "draft"
    meta_data: Dict[str, Any] = Field(default_factory=dict)


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
    canvas: Optional[CanvasSchema] = None
    widgets: Optional[List[WidgetSchema]] = None
    filters: Optional[List[FilterSchema]] = None
    linked_analysis_ids: Optional[List[str]] = None
    is_public: Optional[bool] = None
    auto_refresh: Optional[bool] = None
    refresh_interval: Optional[int] = None
    status: Optional[str] = None


class DashboardService(BaseService):
    def __init__(self):
        super().__init__(model=Dashboard, schema=DashboardSchema)

    def _generate_public_token(self) -> str:
        """Generate a secure public token for dashboard sharing."""
        return secrets.token_urlsafe(32)

    def _generate_slug(self, title: str, organization_id: str) -> str:
        """Generate a URL-friendly slug from title."""
        import re
        base_slug = re.sub(r'[^\w\s-]', '', title.lower())
        base_slug = re.sub(r'[-\s]+', '-', base_slug).strip('-')
        
        # Check for uniqueness
        counter = 1
        slug = base_slug
        while self.model.objects(organization_id=organization_id, slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        return slug

    def _create_canvas(self, canvas_data: CanvasSchema) -> DashboardCanvas:
        """Create canvas object from schema data."""
        return DashboardCanvas(
            width=canvas_data.width,
            height=canvas_data.height,
            background_color=canvas_data.background_color,
            grid_enabled=canvas_data.grid_enabled,
            grid_size=canvas_data.grid_size,
            snap_to_grid=canvas_data.snap_to_grid,
            theme=canvas_data.theme
        )

    def _create_widget_position(self, position_data: PositionSchema) -> WidgetPosition:
        """Create widget position object from schema data."""
        return WidgetPosition(
            x=position_data.x,
            y=position_data.y,
            width=position_data.width,
            height=position_data.height,
            z_index=position_data.z_index
        )

    def _create_widget_data_source(self, data_source_data: Optional[DataSourceSchema]) -> Optional[WidgetDataSource]:
        """Create widget data source object from schema data."""
        if not data_source_data:
            return None
        
        return WidgetDataSource(
            analysis_id=data_source_data.analysis_id,
            node_id=data_source_data.node_id,
            form_id=data_source_data.form_id,
            refresh_mode=data_source_data.refresh_mode,
            refresh_interval=data_source_data.refresh_interval,
            filters=data_source_data.filters,
            transformations=data_source_data.transformations
        )

    def _create_widget_config(self, config_data: Optional[WidgetConfigSchema]) -> Optional[WidgetConfig]:
        """Create widget config object from schema data."""
        if not config_data:
            return None
        
        return WidgetConfig(
            chart_type=config_data.chart_type,
            aggregation_type=config_data.aggregation_type,
            group_by_field=config_data.group_by_field,
            value_field=config_data.value_field,
            color_scheme=config_data.color_scheme,
            show_legend=config_data.show_legend,
            show_labels=config_data.show_labels,
            max_items=config_data.max_items,
            sort_by=config_data.sort_by,
            sort_order=config_data.sort_order,
            display_columns=config_data.display_columns,
            theme_overrides=config_data.theme_overrides,
            custom_styling=config_data.custom_styling
        )

    def _create_widget(self, widget_data: WidgetSchema) -> DashboardWidget:
        """Create widget object from schema data."""
        return DashboardWidget(
            id=widget_data.id or str(uuid.uuid4()),
            widget_type=widget_data.widget_type,
            title=widget_data.title,
            description=widget_data.description,
            position=self._create_widget_position(widget_data.position),
            data_source=self._create_widget_data_source(widget_data.data_source),
            config=self._create_widget_config(widget_data.config),
            is_visible=widget_data.is_visible,
            is_locked=widget_data.is_locked,
            meta_data=widget_data.meta_data
        )

    def _create_filter(self, filter_data: FilterSchema) -> DashboardFilter:
        """Create filter object from schema data."""
        return DashboardFilter(
            id=filter_data.id or str(uuid.uuid4()),
            name=filter_data.name,
            filter_type=filter_data.filter_type,
            field_name=filter_data.field_name,
            options=filter_data.options,
            default_value=filter_data.default_value,
            is_required=filter_data.is_required,
            affects_widgets=filter_data.affects_widgets,
            meta_data=filter_data.meta_data
        )

    def _widget_to_schema(self, widget: DashboardWidget) -> WidgetSchema:
        """Convert widget object to schema."""
        position_schema = PositionSchema(
            x=widget.position.x,
            y=widget.position.y,
            width=widget.position.width,
            height=widget.position.height,
            z_index=widget.position.z_index
        )
        
        data_source_schema = None
        if widget.data_source:
            data_source_schema = DataSourceSchema(
                analysis_id=widget.data_source.analysis_id,
                node_id=widget.data_source.node_id,
                form_id=widget.data_source.form_id,
                refresh_mode=widget.data_source.refresh_mode,
                refresh_interval=widget.data_source.refresh_interval,
                filters=widget.data_source.filters,
                transformations=widget.data_source.transformations
            )
        
        config_schema = None
        if widget.config:
            config_schema = WidgetConfigSchema(
                chart_type=widget.config.chart_type,
                aggregation_type=widget.config.aggregation_type,
                group_by_field=widget.config.group_by_field,
                value_field=widget.config.value_field,
                color_scheme=widget.config.color_scheme,
                show_legend=widget.config.show_legend,
                show_labels=widget.config.show_labels,
                max_items=widget.config.max_items,
                sort_by=widget.config.sort_by,
                sort_order=widget.config.sort_order,
                display_columns=widget.config.display_columns,
                theme_overrides=widget.config.theme_overrides,
                custom_styling=widget.config.custom_styling
            )
        
        return WidgetSchema(
            id=widget.id,
            widget_type=widget.widget_type,
            title=widget.title,
            description=widget.description,
            position=position_schema,
            data_source=data_source_schema,
            config=config_schema,
            is_visible=widget.is_visible,
            is_locked=widget.is_locked,
            meta_data=widget.meta_data
        )

    def _filter_to_schema(self, filter_obj: DashboardFilter) -> FilterSchema:
        """Convert filter object to schema."""
        return FilterSchema(
            id=filter_obj.id,
            name=filter_obj.name,
            filter_type=filter_obj.filter_type,
            field_name=filter_obj.field_name,
            options=filter_obj.options,
            default_value=filter_obj.default_value,
            is_required=filter_obj.is_required,
            affects_widgets=filter_obj.affects_widgets,
            meta_data=filter_obj.meta_data
        )

    def _canvas_to_schema(self, canvas: DashboardCanvas) -> CanvasSchema:
        """Convert canvas object to schema."""
        return CanvasSchema(
            width=canvas.width,
            height=canvas.height,
            background_color=canvas.background_color,
            grid_enabled=canvas.grid_enabled,
            grid_size=canvas.grid_size,
            snap_to_grid=canvas.snap_to_grid,
            theme=canvas.theme
        )

    def _dashboard_to_schema(self, dashboard: Dashboard) -> DashboardSchema:
        """Convert dashboard object to schema."""
        canvas_schema = self._canvas_to_schema(dashboard.canvas)
        widget_schemas = [self._widget_to_schema(widget) for widget in (dashboard.widgets or [])]
        filter_schemas = [self._filter_to_schema(filter_obj) for filter_obj in (dashboard.filters or [])]
        
        return DashboardSchema(
            id=str(dashboard.id),
            title=dashboard.title,
            slug=dashboard.slug,
            organization_id=dashboard.organization_id,
            project_id=dashboard.project_id,
            description=dashboard.description,
            canvas=canvas_schema,
            widgets=widget_schemas,
            filters=filter_schemas,
            linked_analysis_ids=[str(analysis_id) for analysis_id in (dashboard.linked_analysis_ids or [])],
            is_public=dashboard.is_public,
            auto_refresh=dashboard.auto_refresh,
            refresh_interval=dashboard.refresh_interval,
            status=dashboard.status,
            meta_data=dashboard.meta_data
        )

    def _dashboard_snapshot(self, dashboard: Dashboard) -> Dict[str, Any]:
        """Create a snapshot of dashboard data."""
        widgets = [
            self._widget_to_schema(widget).model_dump()
            for widget in (dashboard.widgets or [])
        ]
        filters = [
            self._filter_to_schema(filter_obj).model_dump()
            for filter_obj in (dashboard.filters or [])
        ]
        
        return {
            "snapshot_id": str(dashboard.id),
            "captured_at": (dashboard.updated_at or datetime.now(timezone.utc)).isoformat(),
            "dashboard_id": str(dashboard.id),
            "title": dashboard.title,
            "slug": dashboard.slug,
            "organization_id": dashboard.organization_id,
            "project_id": dashboard.project_id,
            "description": dashboard.description,
            "canvas": self._canvas_to_schema(dashboard.canvas).model_dump(),
            "widgets": widgets,
            "filters": filters,
            "linked_analysis_ids": [str(analysis_id) for analysis_id in (dashboard.linked_analysis_ids or [])],
            "is_public": dashboard.is_public,
            "auto_refresh": dashboard.auto_refresh,
            "refresh_interval": dashboard.refresh_interval,
            "status": dashboard.status,
            "widget_count": len(widgets),
            "filter_count": len(filters),
        }

    def create_dashboard(self, dashboard_data: DashboardCreateSchema, user_id: str) -> DashboardSchema:
        """Create a new dashboard."""
        app_logger.debug(f"Entering create_dashboard: {dashboard_data.title} (org: {dashboard_data.organization_id})")
        
        try:
            # Generate slug if not provided
            if not dashboard_data.slug:
                dashboard_data.slug = self._generate_slug(dashboard_data.title, dashboard_data.organization_id)
            
            # Create dashboard
            dashboard = Dashboard(
                organization_id=dashboard_data.organization_id,
                project_id=dashboard_data.project_id,
                name=dashboard_data.title,
                slug=dashboard_data.slug,
                description=dashboard_data.description,
                canvas=self._create_canvas(dashboard_data.canvas),
                widgets=[self._create_widget(widget) for widget in dashboard_data.widgets],
                filters=[self._create_filter(filter_obj) for filter_obj in dashboard_data.filters],
                linked_analysis_ids=dashboard_data.linked_analysis_ids,
                created_by=user_id,
                is_public=dashboard_data.is_public,
                auto_refresh=dashboard_data.auto_refresh,
                refresh_interval=dashboard_data.refresh_interval,
                status=dashboard_data.status,
                meta_data=dashboard_data.meta_data
            )
            
            dashboard.save()
            
            audit_logger.info(
                f"Audit: dashboard created {dashboard.id} (org: {dashboard_data.organization_id}) by user {user_id}"
            )
            
            result = self._dashboard_to_schema(dashboard)
            app_logger.debug(f"Exiting create_dashboard: {dashboard_data.title} successfully")
            return result
            
        except Exception as e:
            error_logger.error(
                f"Error in create_dashboard {dashboard_data.title}: {str(e)}", exc_info=True
            )
            raise

    def get_dashboard(self, dashboard_id: str, organization_id: str) -> DashboardSchema:
        """Get dashboard by ID."""
        app_logger.debug(f"Entering get_dashboard: {dashboard_id} (org: {organization_id})")
        
        try:
            dashboard = self.model.objects(
                id=dashboard_id, organization_id=organization_id, is_deleted=False
            ).first()
            
            if not dashboard:
                from .exceptions import NotFoundError
                app_logger.warning(f"Dashboard not found: {dashboard_id} (org: {organization_id})")
                raise NotFoundError(f"Dashboard {dashboard_id} not found")
            
            result = self._dashboard_to_schema(dashboard)
            app_logger.debug(f"Exiting get_dashboard: {dashboard_id} successfully")
            return result
            
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(
                    f"Error in get_dashboard {dashboard_id}: {str(e)}", exc_info=True
                )
            raise

    def get_by_slug(self, slug: str, organization_id: str) -> DashboardSchema:
        """Get dashboard by slug."""
        app_logger.debug(f"Entering get_by_slug: {slug} (org: {organization_id})")
        
        try:
            dashboard = self.model.objects(
                slug=slug, organization_id=organization_id, is_deleted=False
            ).first()
            
            if not dashboard:
                from .exceptions import NotFoundError
                app_logger.warning(f"Dashboard not found by slug: {slug} (org: {organization_id})")
                raise NotFoundError(f"Dashboard {slug} not found")

            result = self._dashboard_to_schema(dashboard)
            app_logger.debug(f"Exiting get_by_slug: {slug} successfully")
            return result
            
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(
                    f"Error in get_by_slug {slug}: {str(e)}", exc_info=True
                )
            raise

    def update_dashboard(self, dashboard_id: str, organization_id: str, update_data: DashboardUpdateSchema, user_id: str) -> DashboardSchema:
        """Update dashboard."""
        app_logger.debug(f"Entering update_dashboard: {dashboard_id} (org: {organization_id})")
        
        try:
            dashboard = self.model.objects(
                id=dashboard_id, organization_id=organization_id, is_deleted=False
            ).first()
            
            if not dashboard:
                from .exceptions import NotFoundError
                app_logger.warning(f"Dashboard not found for update: {dashboard_id} (org: {organization_id})")
                raise NotFoundError(f"Dashboard {dashboard_id} not found")
            
            # Update fields
            if update_data.title is not None:
                dashboard.name = update_data.title
                # Update slug if title changed
                dashboard.slug = self._generate_slug(update_data.title, organization_id)
            
            if update_data.description is not None:
                dashboard.description = update_data.description
            
            if update_data.canvas is not None:
                dashboard.canvas = self._create_canvas(update_data.canvas)
            
            if update_data.widgets is not None:
                dashboard.widgets = [self._create_widget(widget) for widget in update_data.widgets]
            
            if update_data.filters is not None:
                dashboard.filters = [self._create_filter(filter_obj) for filter_obj in update_data.filters]
            
            if update_data.linked_analysis_ids is not None:
                dashboard.linked_analysis_ids = update_data.linked_analysis_ids
            
            if update_data.is_public is not None:
                dashboard.is_public = update_data.is_public
                # Generate public token if making public
                if update_data.is_public and not dashboard.public_token:
                    dashboard.public_token = self._generate_public_token()
            
            if update_data.auto_refresh is not None:
                dashboard.auto_refresh = update_data.auto_refresh
            
            if update_data.refresh_interval is not None:
                dashboard.refresh_interval = update_data.refresh_interval
            
            if update_data.status is not None:
                dashboard.status = update_data.status
            
            dashboard.save()
            
            audit_logger.info(
                f"Audit: dashboard updated {dashboard_id} (org: {organization_id}) by user {user_id}"
            )
            
            result = self._dashboard_to_schema(dashboard)
            app_logger.debug(f"Exiting update_dashboard: {dashboard_id} successfully")
            return result
            
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(
                    f"Error in update_dashboard {dashboard_id}: {str(e)}", exc_info=True
                )
            raise

    def delete_dashboard(self, dashboard_id: str, organization_id: str, user_id: str) -> bool:
        """Soft delete dashboard."""
        app_logger.debug(f"Entering delete_dashboard: {dashboard_id} (org: {organization_id})")
        
        try:
            dashboard = self.model.objects(
                id=dashboard_id, organization_id=organization_id, is_deleted=False
            ).first()
            
            if not dashboard:
                from .exceptions import NotFoundError
                app_logger.warning(f"Dashboard not found for deletion: {dashboard_id} (org: {organization_id})")
                raise NotFoundError(f"Dashboard {dashboard_id} not found")
            
            dashboard.is_deleted = True
            dashboard.deleted_at = datetime.now(timezone.utc)
            dashboard.save()
            
            audit_logger.info(
                f"Audit: dashboard deleted {dashboard_id} (org: {organization_id}) by user {user_id}"
            )
            
            app_logger.debug(f"Exiting delete_dashboard: {dashboard_id} successfully")
            return True
            
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(
                    f"Error in delete_dashboard {dashboard_id}: {str(e)}", exc_info=True
                )
            raise

    def list_dashboards(self, organization_id: str, project_id: Optional[str] = None, user_id: Optional[str] = None) -> List[DashboardSchema]:
        """List dashboards for organization or project."""
        app_logger.debug(f"Entering list_dashboards: org {organization_id}, project {project_id}")
        
        try:
            query = self.model.objects(organization_id=organization_id, is_deleted=False)
            
            if project_id:
                query = query.filter(project_id=project_id)
            
            dashboards = query.order_by("-created_at")
            
            # Convert to schemas
            result = [self._dashboard_to_schema(dashboard) for dashboard in dashboards]
            
            app_logger.debug(f"Exiting list_dashboards: found {len(result)} dashboards")
            return result
            
        except Exception as e:
            error_logger.error(
                f"Error in list_dashboards: {str(e)}", exc_info=True
            )
            raise

    def get_canvas(self, dashboard_id: str, organization_id: str) -> Dict[str, Any]:
        """Get dashboard canvas data."""
        app_logger.debug(f"Entering get_canvas: {dashboard_id} (org: {organization_id})")
        
        try:
            dashboard = self.model.objects(
                id=dashboard_id, organization_id=organization_id, is_deleted=False
            ).first()
            
            if not dashboard:
                from .exceptions import NotFoundError
                app_logger.warning(f"Dashboard not found for canvas: {dashboard_id} (org: {organization_id})")
                raise NotFoundError("Dashboard not found")
            
            return self._dashboard_snapshot(dashboard)
            
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(
                    f"Error in get_canvas {dashboard_id}: {str(e)}", exc_info=True
                )
            raise

    def update_canvas(
        self, dashboard_id: str, organization_id: str, canvas_data: Dict[str, Any], user_id: str
    ) -> Dict[str, Any]:
        """Update dashboard canvas data."""
        app_logger.info(f"Entering update_canvas: {dashboard_id} (org: {organization_id})")
        
        try:
            dashboard = self.model.objects(
                id=dashboard_id, organization_id=organization_id, is_deleted=False
            ).first()
            
            if not dashboard:
                from .exceptions import NotFoundError
                app_logger.warning(f"Dashboard not found for canvas update: {dashboard_id} (org: {organization_id})")
                raise NotFoundError("Dashboard not found")
            
            # Update canvas properties
            if "width" in canvas_data:
                dashboard.canvas.width = canvas_data["width"]
            if "height" in canvas_data:
                dashboard.canvas.height = canvas_data["height"]
            if "background_color" in canvas_data:
                dashboard.canvas.background_color = canvas_data["background_color"]
            if "grid_enabled" in canvas_data:
                dashboard.canvas.grid_enabled = canvas_data["grid_enabled"]
            if "grid_size" in canvas_data:
                dashboard.canvas.grid_size = canvas_data["grid_size"]
            if "snap_to_grid" in canvas_data:
                dashboard.canvas.snap_to_grid = canvas_data["snap_to_grid"]
            if "theme" in canvas_data:
                dashboard.canvas.theme = canvas_data["theme"]
            
            # Update widgets if provided
            if "widgets" in canvas_data:
                widgets = []
                for widget_data in canvas_data["widgets"]:
                    widget = self._create_widget(WidgetSchema(**widget_data))
                    widgets.append(widget)
                dashboard.widgets = widgets
            
            # Update filters if provided
            if "filters" in canvas_data:
                filters = []
                for filter_data in canvas_data["filters"]:
                    filter_obj = self._create_filter(FilterSchema(**filter_data))
                    filters.append(filter_obj)
                dashboard.filters = filters
            
            # Recompute linked_analysis_ids from all widget data_source.analysis_id values
            analysis_ids = set()
            import bson
            for widget in dashboard.widgets:
                if widget.data_source and widget.data_source.analysis_id:
                    analysis_ids.add(bson.ObjectId(widget.data_source.analysis_id))
            dashboard.linked_analysis_ids = list(analysis_ids)
            
            dashboard.save()
            
            audit_logger.info(
                f"Audit: dashboard canvas updated for {dashboard_id} (org: {organization_id}) by user {user_id}"
            )
            
            return self._dashboard_snapshot(dashboard)
            
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(
                    f"Error in update_canvas {dashboard_id}: {str(e)}", exc_info=True
                )
            raise

    def list_snapshots(self, dashboard_id: str, organization_id: str) -> List[Dict[str, Any]]:
        """List dashboard snapshots."""
        app_logger.debug(f"Entering list_snapshots: {dashboard_id} (org: {organization_id})")
        
        try:
            from services.dashboard_snapshot_service import DashboardSnapshotService
            snapshot_service = DashboardSnapshotService()
            snapshots = snapshot_service.list_snapshots(dashboard_id, organization_id)
            return [s.model_dump() for s in snapshots]
            
        except Exception as e:
            from .exceptions import NotFoundError
            if not isinstance(e, NotFoundError):
                error_logger.error(
                    f"Error in list_snapshots {dashboard_id}: {str(e)}", exc_info=True
                )
            raise

    # --- Public Sharing Logic ---
    def enable_public_sharing(self, dashboard_id: str, organization_id: str, user_id: str) -> Dict[str, Any]:
        """Enable public sharing for dashboard."""
        app_logger.debug(f"Entering enable_public_sharing: {dashboard_id} (org: {organization_id})")
        
        try:
            dashboard = self.model.objects(
                id=dashboard_id, organization_id=organization_id, is_deleted=False
            ).first()
            
            if not dashboard:
                from .exceptions import NotFoundError
                app_logger.warning(f"Dashboard not found for public sharing: {dashboard_id} (org: {organization_id})")
                raise NotFoundError("Dashboard not found")
            
            dashboard.is_public = True
            if not dashboard.public_token:
                dashboard.public_token = self._generate_public_token()
            
            dashboard.save()
            
            # Create public access record
            public_access = DashboardPublicAccess(
                organization_id=organization_id,
                dashboard_id=dashboard,
                access_token=dashboard.public_token,
                created_by=user_id
            )
            public_access.save()
            
            audit_logger.info(
                f"Audit: public sharing enabled for dashboard {dashboard_id} (org: {organization_id}) by user {user_id}"
            )
            
            result = {
                "dashboard_id": str(dashboard.id),
                "public_token": dashboard.public_token,
                "public_url": f"/public/dashboard/{dashboard.public_token}",
                "is_public": True
            }
            
            app_logger.debug(f"Exiting enable_public_sharing: {dashboard_id} successfully")
            return result
            
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(
                    f"Error in enable_public_sharing {dashboard_id}: {str(e)}", exc_info=True
                )
            raise

    def disable_public_sharing(self, dashboard_id: str, organization_id: str, user_id: str) -> bool:
        """Disable public sharing for dashboard."""
        app_logger.debug(f"Entering disable_public_sharing: {dashboard_id} (org: {organization_id})")
        
        try:
            dashboard = self.model.objects(
                id=dashboard_id, organization_id=organization_id, is_deleted=False
            ).first()
            
            if not dashboard:
                from .exceptions import NotFoundError
                app_logger.warning(f"Dashboard not found for disabling public sharing: {dashboard_id} (org: {organization_id})")
                raise NotFoundError("Dashboard not found")
            
            dashboard.is_public = False
            dashboard.public_token = None
            dashboard.save()
            
            # Remove public access records
            DashboardPublicAccess.objects(dashboard_id=dashboard).delete()
            
            audit_logger.info(
                f"Audit: public sharing disabled for dashboard {dashboard_id} (org: {organization_id}) by user {user_id}"
            )
            
            app_logger.debug(f"Exiting disable_public_sharing: {dashboard_id} successfully")
            return True
            
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(
                    f"Error in disable_public_sharing {dashboard_id}: {str(e)}", exc_info=True
                )
            raise

    def get_public_dashboard(self, public_token: str) -> Dict[str, Any]:
        """Get public dashboard by token."""
        app_logger.debug(f"Entering get_public_dashboard: token {public_token[:8]}...")
        
        try:
            dashboard = self.model.objects(
                public_token=public_token, is_public=True, is_deleted=False
            ).first()
            
            if not dashboard:
                from .exceptions import NotFoundError
                app_logger.warning(f"Public dashboard not found: token {public_token[:8]}...")
                raise NotFoundError("Public dashboard not found")
            
            # Update access count
            public_access = DashboardPublicAccess.objects(
                dashboard_id=dashboard, access_token=public_token
            ).first()
            
            if public_access:
                public_access.access_count += 1
                public_access.last_accessed_at = datetime.now(timezone.utc)
                public_access.save()
            
            result = self._dashboard_snapshot(dashboard)
            app_logger.debug(f"Exiting get_public_dashboard: token {public_token[:8]}... successfully")
            return result
            
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(
                    f"Error in get_public_dashboard {public_token[:8]}...: {str(e)}", exc_info=True
                )
            raise

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
                "type": "kpi_card",
                "name": "KPI Card",
                "description": "Key Performance Indicator card",
            },
            {
                "type": "bar_chart",
                "name": "Bar Chart",
                "description": "Aggregated data in bar format",
            },
            {
                "type": "line_chart",
                "name": "Line Chart",
                "description": "Trend data over time",
            },
            {
                "type": "pie_chart",
                "name": "Pie Chart",
                "description": "Percentage distribution",
            },
            {
                "type": "data_table",
                "name": "Data Table",
                "description": "Tabular data display",
            },
            {
                "type": "text",
                "name": "Text/Label",
                "description": "Static text or label",
            },
            {
                "type": "image",
                "name": "Image",
                "description": "Image display widget",
            },
            {
                "type": "filter",
                "name": "Filter Widget",
                "description": "Interactive filter for dashboard",
            },
        ]
        app_logger.debug(f"Exiting get_available_widgets: {len(widgets)} widgets found")
        return widgets
